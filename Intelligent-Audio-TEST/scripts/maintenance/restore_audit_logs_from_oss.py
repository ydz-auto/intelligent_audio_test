# -*- coding: utf-8 -*-
"""按日期区间从 rustfs 回灌审计日志（INT-1877 / INT-1793 契约 §Q5.3）。

30 天到期归档 → 删除本地后，误删的恢复路径就是本脚本：把
`archives/audit/{date}/` 的归档件按日期区间**原样**回灌到本地日志根，
读侧（`audit_reader`）无需任何改动即可重新看到这些日期。

契约（§Q5.3）逐条落地：

- 源：`storage.list_objects('archives', prefix='audit/{date}/')` 逐日枚举，
  `storage.load_bytes('oss://archives/audit/{date}/{name}')` 下载——**必须走
  `shared/infrastructure/storage` 的 category 机制**（由它拼 `OSS_BUCKET_NAME` /
  `OSS_KEY_PREFIX`）。宿主脚本手拼 key 或直连 bucket 会落到别的前缀，读侧看不见。
- 落点：`{LOG_ROOT_DIR}/audit/{date}/{原文件名}`，与写侧模板
  （`AuditLogPathBuilder.build_rel_path`）一字不差；不重命名、不合并多日。
- OSS 可达性：启动先探活，存储层为归档 category 解析出的 path 必须是 `oss://`；
  出现 `local://`（OSS 不可达 / 未配置时存储层会静默降级）即判不可用 → 非零退出，
  不允许「成功回灌 0 个文件」。
- 幂等：默认**不覆盖**已存在的本地文件（重跑字节级不变）；只有显式 `--overwrite`
  才覆盖。本地已存在且字节数与源一致时计入「跳过」，不算失败。
- 校验：①逐文件比对字节数与源对象元数据（`list_objects_with_meta` 的 size）；
  ②落盘后回读重算 sha256 与下载内容比对；③逐行 `json.loads` 必须成功，且每行
  `cursor`/`event`/`time` 非空；④汇总打印「期望对象数 / 下载数 / 跳过数 /
  校验失败数 / 落盘数」，任一失败 → 非零退出并列出文件。
- 边界：只读 rustfs + 只写本地目录，**不写 DB、不触碰 `logs` 表**；区间内没有
  对象的日子打印 0 并继续（不报错）。
- 授权：同「提前删除」——需负责人 yy dd 批准，执行记录留在卡面。

用法（宿主运行，项目环境 python）：
    # 桶模式必须与 compose 一致（主 compose 是单桶模式），否则探活/列举会落到别的桶
    $env:OSS_ENDPOINT='http://localhost:9000'
    $env:OSS_ACCESS_KEY/SECRET_KEY 与 docker compose 一致
    $env:OSS_BUCKET_NAME='intelligent-audio-test'
    $env:OSS_KEY_PREFIX='intelligent_audio_test'
    $env:LOG_ROOT_DIR='D:\\...\\logs'
    python scripts/maintenance/restore_audit_logs_from_oss.py --from 2026-09-01 --to 2026-09-07

    python scripts/maintenance/restore_audit_logs_from_oss.py \
        --from 2026-09-01 --to 2026-09-07 --categories auth,benchmark
    python scripts/maintenance/restore_audit_logs_from_oss.py \
        --from 2026-09-01 --to 2026-09-07 --target-root <dir> --dry-run

退出码：0 = 全部成功（含区间内无对象）；1 = 有校验失败 / 下载失败 / 未覆盖冲突；
3 = OSS 不可达（探活失败）；2 = 参数错误（argparse）。
"""
import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# 本脚本不碰 DB（只经存储抽象读对象 + 写本地目录），但 shared.infrastructure.config
# 在导入期强校验 DATABASE_URL；未设置时给占位串，脚本全程不会建立数据库连接。
os.environ.setdefault('DATABASE_URL',
                      'sqlite:///restore_audit_logs_placeholder.db')

try:
    from shared.infrastructure.storage import storage  # noqa: E402
    from shared.logging.config import get_log_settings  # noqa: E402
    from shared.logging.enums import AUDIT_DIR, AUDIT_FILE_SUFFIX  # noqa: E402
    from shared.logging.retention import (  # noqa: E402
        AUDIT_ARCHIVE_CATEGORY,
        AUDIT_ARCHIVE_PREFIX,
    )
    from shared.models.common_enums import AUDIT_LOG_CATEGORIES  # noqa: E402
except Exception as e:  # BaseConfig 导入期强校验（OSS 凭据 / endpoint 缺失）
    raise SystemExit('[restore] ERROR - 存储或日志配置导入失败'
                     f'（检查 OSS_ACCESS_KEY / OSS_SECRET_KEY / OSS_ENDPOINT）：{e}')

# 退出码（与 INT-1785 维护脚本同风格：非零即「未完成」）
EXIT_OK = 0
EXIT_VALIDATION_FAILED = 1
EXIT_OSS_UNAVAILABLE = 3

_DATE_FORMAT = '%Y-%m-%d'
_SCHEME_OSS = 'oss://'
_SCHEME_LOCAL = 'local://'   # 存储层降级写本地时的 scheme（探活判失败）
# 探活用的逻辑 key（不下载、不写对象，只让存储层解析出 scheme）
_PROBE_KEY = f'{AUDIT_ARCHIVE_PREFIX}/.probe'
# 审计 JSONL 每行必备且必须非空的字段（契约 §Q5.3 校验 ③）
_REQUIRED_LINE_FIELDS = ('cursor', 'event', 'time')
_LOG_PREFIX = '[restore]'


@dataclass
class RestoreStats:
    """回灌汇总计数（契约 §Q5.3 校验 ④ 的五项 + 未覆盖冲突）。"""

    expected: int = 0
    downloaded: int = 0
    skipped: int = 0
    conflicts: int = 0
    failed: int = 0
    written: int = 0
    failures: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.failed == 0 and self.conflicts == 0


def _log(message: str) -> None:
    """脚本输出（stdout 可能是受限编码管道，失败静默）。"""
    try:
        print(f'{_LOG_PREFIX} {message}', flush=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 参数
# ---------------------------------------------------------------------------

def _parse_date(raw: str) -> date:
    """解析 YYYY-MM-DD；非法抛 argparse 参数错误。"""
    try:
        return datetime.strptime(raw, _DATE_FORMAT).date()
    except ValueError:
        raise argparse.ArgumentTypeError(
            f'日期必须是 YYYY-MM-DD：{raw!r}')


def _parse_categories(raw: str) -> tuple:
    """`auth,benchmark` → ('auth', 'benchmark')；空串 = 全部。"""
    values = tuple(
        item.strip().lower() for item in (raw or '').split(',') if item.strip())
    unknown = [item for item in values if item not in AUDIT_LOG_CATEGORIES]
    if unknown:
        _log(f'WARN - 未知 category（{",".join(unknown)}），'
             f'已知值：{",".join(sorted(AUDIT_LOG_CATEGORIES))}')
    return values


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='按日期区间从 rustfs 回灌审计日志（INT-1793 契约 §Q5.3）')
    parser.add_argument('--from', dest='date_from', required=True,
                        type=_parse_date, help='起始日期（含），YYYY-MM-DD')
    parser.add_argument('--to', dest='date_to', required=True,
                        type=_parse_date, help='结束日期（含），YYYY-MM-DD')
    parser.add_argument('--categories', default='',
                        help='参与回灌的 category（逗号分隔），默认全部')
    parser.add_argument('--target-root', default=None,
                        help='本地日志根目录，默认取 LOG_ROOT_DIR 配置')
    parser.add_argument('--dry-run', action='store_true',
                        help='只枚举区间内对象数，不下载不落盘')
    parser.add_argument('--overwrite', action='store_true',
                        help='覆盖本地已存在的文件（默认不覆盖，重跑幂等）')
    args = parser.parse_args(argv)
    if args.date_from > args.date_to:
        parser.error(f'--from（{args.date_from}）不能晚于 --to（{args.date_to}）')
    return args


# ---------------------------------------------------------------------------
# 存储探活
# ---------------------------------------------------------------------------

def probe_object_storage(store=None) -> str:
    """探活：返回存储层为归档 category 解析出的路径（必须 `oss://`）。

    存储层在 OSS 不可达 / 未配置时会静默降级到容器本地并返回 `local://`
    （`Storage.save_*` / `list_objects` 的 fallback 语义）。这里只读地问一次
    存储层「本次会走后端还是本地降级」，再把结果翻成带 scheme 的路径——
    出现 `local://` 即判 OSS 不可用（契约 §Q5.3「OSS 可达性」）。
    """
    target = store if store is not None else storage
    prefer_oss = True
    use_oss = getattr(target, '_use_oss', None)
    if callable(use_oss):
        try:
            prefer_oss = bool(use_oss())
        except Exception:
            prefer_oss = False
    return target.build_path(AUDIT_ARCHIVE_CATEGORY, _PROBE_KEY,
                             prefer_oss=prefer_oss)


# ---------------------------------------------------------------------------
# 区间枚举
# ---------------------------------------------------------------------------

def iter_date_range(start: date, end: date):
    """按目录日期逐日产出（含两端）。"""
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _object_day_prefix(day_seg: str) -> str:
    """归档对象前缀：`audit/{date}/`（与写侧归档 key 同模板）。"""
    return f'{AUDIT_ARCHIVE_PREFIX}/{day_seg}/'


def _object_name(key: str) -> str:
    return (key or '').rsplit('/', 1)[-1]


def _matches_categories(name: str, categories: tuple) -> bool:
    """文件名首段即 category（`{category}.{service}.{identity}.jsonl`）。"""
    if not categories:
        return True
    return name.split('.', 1)[0].lower() in categories


def list_day_objects(store, day_seg: str, categories: tuple) -> list:
    """枚举某日归档件：[(key, sizeBytes)]，按 key 稳定排序。"""
    entries = store.list_objects_with_meta(
        AUDIT_ARCHIVE_CATEGORY, _object_day_prefix(day_seg))
    result = []
    for entry in entries or []:
        key = (entry or {}).get('key') or ''
        name = _object_name(key)
        # 目录占位对象 / 非审计件一律跳过（只回灌 .jsonl，不重命名）
        if not name.endswith(AUDIT_FILE_SUFFIX):
            continue
        if not key.startswith(_object_day_prefix(day_seg)):
            continue
        if not _matches_categories(name, categories):
            continue
        result.append((key, entry.get('sizeBytes')))
    return sorted(result, key=lambda item: item[0])


# ---------------------------------------------------------------------------
# 校验与落盘
# ---------------------------------------------------------------------------

def validate_jsonl(data: bytes) -> list:
    """逐行校验审计 JSONL：解析成功 + `cursor`/`event`/`time` 非空。"""
    problems = []
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError as e:
        return [f'UTF-8 解码失败: {e}']
    lines = text.split('\n')
    if lines and lines[-1] == '':
        # 文件以换行结尾：末段是空串，不是空行
        lines.pop()
    for index, line in enumerate(lines, 1):
        if not line.strip():
            problems.append(f'第 {index} 行为空行')
            continue
        try:
            record = json.loads(line)
        except ValueError as e:
            problems.append(f'第 {index} 行 JSON 解析失败: {e}')
            continue
        if not isinstance(record, dict):
            problems.append(f'第 {index} 行不是 JSON 对象')
            continue
        for field_name in _REQUIRED_LINE_FIELDS:
            value = record.get(field_name)
            if value is None or (isinstance(value, str) and not value.strip()):
                problems.append(f'第 {index} 行缺字段 {field_name}')
    return problems


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def target_path(target_root: str, day_seg: str, name: str) -> str:
    """回灌落点：{LOG_ROOT_DIR}/audit/{date}/{原文件名}（与写侧模板一致）。"""
    return os.path.join(target_root, AUDIT_DIR, day_seg, name)


def _write_atomic(path: str, data: bytes) -> None:
    """原子落盘：先写 .part 再 replace，避免半截文件被读侧看到。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    part_path = f'{path}.part'
    with open(part_path, 'wb') as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(part_path, path)


def _restore_one(store, key: str, source_size, day_seg: str, target_root: str,
                 overwrite: bool, stats: RestoreStats) -> None:
    """回灌单个归档件：默认不覆盖 → 下载 → 校验 → 原子落盘 → 回读复核。"""
    name = _object_name(key)
    dst = target_path(target_root, day_seg, name)
    expected_size = None
    if source_size is not None:
        try:
            expected_size = int(source_size)
        except (TypeError, ValueError):
            expected_size = None

    if os.path.exists(dst) and not overwrite:
        local_size = os.path.getsize(dst)
        if expected_size is not None and local_size == expected_size:
            stats.skipped += 1
            _log(f'skip（本地已存在且字节数一致）: {dst}')
            return
        # 本地有同名字节数不同的文件：默认不动，交给执行者决定（--overwrite）
        stats.conflicts += 1
        stats.failures.append(
            f'{key}: 本地已存在且大小与源不一致（本地 {local_size} / 源 '
            f'{expected_size}），未覆盖——确认后加 --overwrite')
        return

    try:
        data = store.load_bytes(f'{_SCHEME_OSS}{AUDIT_ARCHIVE_CATEGORY}/{key}')
    except Exception as e:
        stats.failed += 1
        stats.failures.append(f'{key}: 下载失败 {e}')
        return
    stats.downloaded += 1

    if expected_size is not None and len(data) != expected_size:
        stats.failed += 1
        stats.failures.append(
            f'{key}: 字节数校验失败（下载 {len(data)} / 元数据 {expected_size}）')
        return

    problems = validate_jsonl(data)
    if problems:
        stats.failed += 1
        stats.failures.append(f'{key}: 内容校验失败 -> ' + '；'.join(problems[:5]))
        return

    try:
        _write_atomic(dst, data)
    except OSError as e:
        stats.failed += 1
        stats.failures.append(f'{key}: 落盘失败 {e}')
        return

    # ② 落盘后回读：字节数与 sha256 必须与下载内容一致
    try:
        with open(dst, 'rb') as fh:
            written = fh.read()
    except OSError as e:
        stats.failed += 1
        stats.failures.append(f'{key}: 回读失败 {e}')
        return
    if len(written) != len(data) or _sha256(written) != _sha256(data):
        stats.failed += 1
        stats.failures.append(f'{key}: sha256 校验失败（落盘内容与下载内容不一致）')
        try:
            os.remove(dst)
        except OSError:
            pass
        return
    stats.written += 1
    _log(f'写入 {dst}（{len(data)} 字节，sha256 {_sha256(data)[:16]}…）')


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def restore_range(start: date, end: date, target_root: str, categories: tuple,
                  overwrite: bool, dry_run: bool, store=None) -> RestoreStats:
    """按日期区间回灌；返回汇总（任一失败由调用方转成非零退出）。"""
    target = store if store is not None else storage
    stats = RestoreStats()
    for current in iter_date_range(start, end):
        day_seg = current.isoformat()
        try:
            objects = list_day_objects(target, day_seg, categories)
        except Exception as e:
            stats.failed += 1
            stats.failures.append(f'{day_seg}: 列举归档对象失败 {e}')
            continue
        _log(f'{day_seg}: {len(objects)} 个归档对象')
        stats.expected += len(objects)
        for key, size in objects:
            if dry_run:
                continue
            _restore_one(target, key, size, day_seg, target_root, overwrite, stats)
    return stats


def _report(stats: RestoreStats, dry_run: bool, target_root: str) -> int:
    """打印汇总并给出退出码（契约 §Q5.3 校验 ④ / 失败处理）。"""
    if dry_run:
        _log(f'[dry-run] 区间内共 {stats.expected} 个归档对象，未下载未落盘；'
             f'目标根 {target_root}')
        return EXIT_OK if stats.failed == 0 else EXIT_VALIDATION_FAILED
    _log(f'汇总：期望对象数={stats.expected} 下载数={stats.downloaded} '
         f'跳过数={stats.skipped} 冲突数={stats.conflicts} '
         f'校验失败数={stats.failed} 落盘数={stats.written}')
    _log(f'本地日志根：{target_root}')
    if stats.failures:
        _log(f'失败清单（{len(stats.failures)}）：')
        for item in stats.failures:
            _log(f'  - {item}')
    return EXIT_OK if stats.ok else EXIT_VALIDATION_FAILED


def main(argv=None) -> int:
    args = parse_args(argv)
    target_root = args.target_root or get_log_settings().root_dir
    _log('授权提示：本脚本属「误删恢复」维护操作，需负责人 yy dd 批准，'
         '执行记录留在卡面（契约 §Q5.3）')

    probe_path = probe_object_storage()
    if not probe_path.startswith(_SCHEME_OSS):
        _log(f'ERROR - 对象存储不可用（探活路径 {probe_path}，需 {_SCHEME_OSS}；'
             f'{_SCHEME_LOCAL} 表示存储层已降级写本地副本，副本不持久）；'
             '不回灌，非零退出。请确认 OSS_ENDPOINT / OSS_BUCKET_NAME / '
             'OSS_KEY_PREFIX 与部署一致后重试')
        return EXIT_OSS_UNAVAILABLE
    _log(f'对象存储探活通过：{probe_path}')

    stats = restore_range(
        args.date_from, args.date_to, target_root,
        categories=_parse_categories(args.categories),
        overwrite=args.overwrite, dry_run=args.dry_run,
    )
    return _report(stats, args.dry_run, target_root)


if __name__ == '__main__':
    sys.exit(main())
