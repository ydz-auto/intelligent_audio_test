# -*- coding: utf-8 -*-
"""原始报文对象（raw payload）的搬运：导出读对象 / 导入回写 + 1.0 旧包现场物化
（INT-1811 / A1）

口径（唯一实现在 shared/utils/raw_payload.py，禁止在此另立一套）：

- key `raw/{resp|req}/{sha[:2]}/{sha}.json.gz`，类别 `case_result`，gzip，
  content_type `application/json+gzip`，sha256 对**规范化未压缩字节**计算；
- 内容寻址 → 包内同对象只出现一次，导入侧**免 id_remapper 改写**
  （key 与 test_result_id 无关）；
- 读写一律 `allow_fallback=False`：raw 类别不允许静默落本地盘（D1 / INT-1805），
  本地副本随容器重建即丢。

失败方向：

- 导出读不到对象 → 抛 RawObjectUnavailableError（整包失败）。**不得跳过**：
  包里缺对象、行里又有 uri，搬过去就是对端一库悬空指针；
- 导入写不进对象 → 抛 RawObjectUnavailableError，由编排层按段失败回滚；
- 导入包内对象解压后 sha 与 key 不符 → 抛 RawObjectPackageError（坏包拒绝）。
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from shared.infrastructure.storage import (
    StorageUnavailableError,
    storage,
)
from shared.utils.log_handler import log_not_emit
from shared.utils.raw_payload import (
    RAW_CATEGORY,
    RAW_CONTENT_TYPE,
    RAW_PAYLOAD_SPECS,
    canonical_bytes,
    compress,
    decompress,
    object_key,
    parse_object_key,
    sha256_hex,
    sha256_of_bytes,
)
from task_service.domain.services.data_transfer.raw_objects import (
    RawObjectRef,
    raw_pointer_columns,
    row_object_key,
    strip_raw_pointer_columns,
)

logger = logging.getLogger(__name__)

_MODULE_NAME = 'transfer_raw_payload'


class RawObjectError(RuntimeError):
    """原始报文对象搬运失败（导出 / 导入都按段失败处理，不静默降级）"""


class RawObjectUnavailableError(RawObjectError):
    """对象不可达（读不到 / 写不进）"""


class RawObjectPackageError(RawObjectError):
    """包内对象缺失或校验失败（坏包）"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _load_object(ref: RawObjectRef) -> bytes:
    uri = ref.uri
    if uri.startswith('local://'):
        raise RawObjectUnavailableError(
            f'原始报文对象是本地降级路径（禁止搬运）{ref.key}: {uri}')
    try:
        return storage.load_bytes(uri, allow_fallback=False)
    except Exception as e:
        raise RawObjectUnavailableError(
            f'原始报文对象读取失败（{ref.key}）: {e}') from e


def iter_raw_object_entries(refs: Iterable[RawObjectRef]) -> Iterator[Tuple[str, bytes]]:
    """按去重后的引用产出 (包内相对路径 = 存储 key, 压缩字节)。

    任一对象读不到即抛错（导出侧整包失败，理由见模块头）。
    """
    for ref in refs or []:
        yield ref.key, _load_object(ref)


class RawObjectCollector:
    """导出侧边写边统计（manifest 的对象清单与实际包内条目一一对应的来源）。

    只包原始报文对象，不与结果文件 / 参考参数 / 音频的 fileCount 混算。
    """

    def __init__(self, entries: Iterator[Tuple[str, bytes]]):
        self._entries = entries
        self.count = 0
        self.total_bytes = 0
        self.files: List[dict] = []

    def __iter__(self):
        for key, data in self._entries:
            parsed = parse_object_key(key)
            if parsed is None:
                raise RawObjectPackageError(f'非法的原始报文对象 key: {key!r}')
            self.count += 1
            self.total_bytes += len(data)
            self.files.append({'key': key, 'sha256': parsed[1], 'bytes': len(data)})
            yield key, data

    def summary(self) -> dict:
        """manifest.rawObjects 段"""
        return {
            'count': self.count,
            'totalBytes': self.total_bytes,
            'contentType': RAW_CONTENT_TYPE,
            'category': RAW_CATEGORY,
            'files': list(self.files),
        }


def _write_object(key: str, sha256: str, data: bytes) -> str:
    """写对象（内容寻址，重复写幂等）；先校验包内字节与 key 的 sha 一致。"""
    parsed = parse_object_key(key)
    if parsed is None:
        raise RawObjectPackageError(f'非法的原始报文对象 key: {key!r}')
    try:
        raw = decompress(data)
    except Exception as e:
        raise RawObjectPackageError(f'原始报文对象解压失败 {key}: {e}') from e
    actual = sha256_of_bytes(raw)
    if actual != sha256 or actual != parsed[1]:
        raise RawObjectPackageError(
            f'原始报文对象内容与 key 不符（包被改动或损坏）{key}: sha256={actual}')
    try:
        return storage.save_bytes(data, RAW_CATEGORY, key,
                                  content_type=RAW_CONTENT_TYPE,
                                  allow_fallback=False)
    except StorageUnavailableError as e:
        raise RawObjectUnavailableError(
            f'原始报文对象写入失败（不允许本地降级）{key}: {e}') from e
    except Exception as e:
        raise RawObjectUnavailableError(f'原始报文对象写入失败 {key}: {e}') from e


def _object_readable(uri: str) -> bool:
    """同端往返时判断 uri 指向的对象是否还在（内容寻址 → 不做二次上传）"""
    if str(uri).startswith('local://'):
        return False
    try:
        storage.load_bytes(uri, allow_fallback=False)
        return True
    except Exception:
        return False


def import_raw_objects(package_entries: Iterable[Tuple[str, bytes]],
                       rows: List[dict],
                       require_objects: bool = True,
                       created_at: Optional[str] = None) -> dict:
    """把包内 raw 对象回写到本端存储，并把维度行的指针改写到本端路径。

    Args:
        package_entries: (包内相对路径, 压缩字节)——来自 zip 的 files/raw/ 条目
        rows: test_result_dimensions 行（就地修改）
        require_objects: True（manifest >= 1.2）时，行引用的对象必须都能在包里
            找到，否则按坏包拒绝；False（1.0 / 1.1 历史包）时按行降级：
            有内联 JSON → 现场物化；只有不可达 uri → 清空指针并在 warnings 里列出
        created_at: 指针列的 created_at（缺省取当前 UTC 时间）

    Returns:
        {'packageObjects', 'written', 'materialized', 'kept', 'stripped',
         'objectRows', 'warnings'}

    Raises: RawObjectUnavailableError（对象写不进）/ RawObjectPackageError（坏包）
    """
    created_at = created_at or _now_iso()
    package: Dict[str, bytes] = {}
    for key, data in package_entries or []:
        if parse_object_key(key) is None:
            raise RawObjectPackageError(f'包内出现非法的原始报文对象路径: {key!r}')
        package[key] = data

    stats = {
        'packageObjects': len(package),
        'written': 0,
        'materialized': 0,
        'kept': 0,
        'stripped': 0,
        'objectRows': 0,
        'warnings': [],
    }
    written: Dict[str, str] = {}

    def _ensure(key: str, sha256: str, data: bytes) -> str:
        stored = written.get(key)
        if stored is not None:
            return stored
        stored = _write_object(key, sha256, data)
        written[key] = stored
        stats['written'] += 1
        return stored

    pointer_rows = 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for spec in RAW_PAYLOAD_SPECS:
            uri = row.get(spec.uri_column)
            inline = row.get(spec.json_column)
            key, sha = row_object_key(row, spec)

            if key and key in package:
                data = package[key]
                stored = _ensure(key, sha, data)
                row.update(raw_pointer_columns(spec, stored, sha, len(data), created_at))
                row[spec.json_column] = None
                pointer_rows += 1
                continue

            if inline is not None and uri is None:
                # 1.0 旧包 / 未回填的行：现场物化（规范化 + sha256 + gzip + 上传 + 写 uri）
                sha = sha256_hex(inline)
                key = object_key(spec.kind, sha)
                data = compress(canonical_bytes(inline))
                stored = _ensure(key, sha, data)
                row.update(raw_pointer_columns(spec, stored, sha, len(data), created_at))
                row[spec.json_column] = None
                stats['materialized'] += 1
                pointer_rows += 1
                continue

            if inline is not None and uri is not None:
                # 指针与内联并存（未回填的行却带了 uri）：以对象为准，优先包内对象，
                # 其次本端存储里的对象，最后才回落到内联 JSON 现场物化
                if _object_readable(str(uri)):
                    row[spec.json_column] = None
                    stats['kept'] += 1
                    continue
                sha = sha256_hex(inline)
                key = object_key(spec.kind, sha)
                data = compress(canonical_bytes(inline))
                stored = _ensure(key, sha, data)
                row.update(raw_pointer_columns(spec, stored, sha, len(data), created_at))
                row[spec.json_column] = None
                stats['materialized'] += 1
                pointer_rows += 1
                continue

            if not uri:
                # 本来就没有报文：两列都保持 NULL
                continue

            # 有 uri、包里没有对象、也没有内联 JSON
            if require_objects:
                # 1.2 起导出侧保证对象齐全 → 缺对象即坏包；不因「本端恰好也有
                # 同 key 对象」放行（那会让包损坏一直查不出来）
                raise RawObjectPackageError(
                    f'包内缺少原始报文对象 {key or uri}（维度行 id={row.get("id")!r}）；'
                    f'包版本声明携带对象，缺对象按坏包拒绝')
            if _object_readable(str(uri)):
                row[spec.json_column] = None
                stats['kept'] += 1
                pointer_rows += 1
                continue
            row.update(strip_raw_pointer_columns(spec))
            row[spec.json_column] = None
            stats['stripped'] += 1
            stats['warnings'].append(
                f'维度行 id={row.get("id")!r} 的 {spec.kind} 原始报文对象不在包内且本端不可达，'
                f'已清空指针（原始报文不可用）')

    stats['objectRows'] = pointer_rows
    if stats['materialized'] or stats['stripped'] or stats['kept']:
        log_not_emit('INFO', _MODULE_NAME,
                     f'原始报文对象搬运：包内 {stats["packageObjects"]} / 写入 '
                     f'{stats["written"]} / 旧包物化 {stats["materialized"]} / '
                     f'复用 {stats["kept"]} / 清空 {stats["stripped"]}', category='system')
    if stats['warnings']:
        log_not_emit('WARNING', _MODULE_NAME,
                     f'原始报文对象降级 {len(stats["warnings"])} 行: '
                     f'{stats["warnings"][:5]}', category='system')
    return stats
