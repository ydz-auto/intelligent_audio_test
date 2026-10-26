# -*- coding: utf-8 -*-
"""报告用例配置快照外置的读写口径（INT-1994 / 档4 R1）

把 ``report_cases`` 的九字段用例配置 payload 按 ``sha256(规范化 JSON)``
内容寻址外置到 ``report_case_snapshots``，行上只留 4 个指针列：

    snapshot_uri          db://report_case_snapshots/{sha256}
    snapshot_sha256       内容主键（解引用 / 回填判据 / 门禁 / sweep 的一等键）
    snapshot_bytes        压缩后字节数（gzip）
    snapshot_created_at   该快照对应内容的生成时间（在线=写入时刻；回填=源行 created_at）

九字段边界（设计文档 10_报告用例快照外置.md §2）：``name`` / ``description`` /
``category`` / ``tags`` / ``metrics`` / ``results`` / ``audios`` /
``reference_params`` / ``algorithm_results``。**行上留** ``id`` / ``report_id`` /
``test_case_id`` / ``algorithm_type`` / ``logs``。分数 / 轮次 / 执行结果不是列，
它们分别在 ``metrics`` / ``algorithm_results`` / ``results`` 里随 payload 进快照。

口径 100% 复用 ``shared/utils/raw_payload.py`` 的 ``canonical_bytes`` /
``sha256_of_bytes`` / ``compress`` / ``decompress``（**不另写第二套**：两份实现
一旦漂移，在线写入与回填写入会算出不同 sha，A→B→A 往返膨胀）。

明确**不用** ``object_key`` / ``parse_object_key``（kind 白名单只认 resp / req，
表载体没有 key 形态，档3 一行不改），也**不复用**
``shared/infrastructure/raw_payload_store.py``（绑死 api 两张表的列），但照抄它的
读侧纪律：**解压后校验 sha256，不符抛显式错误，绝不静默回退内容列、绝不返回空**。

回滚开关 ``REPORT_CASE_SNAPSHOT_SOURCE=column|snapshot``（默认 ``snapshot``）：
切 ``column`` 时读侧照旧读行上的内容列（R1 双写期间二者等价）。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from shared.models.database import utc8now
from shared.utils.raw_payload import (
    canonical_bytes,
    compress,
    decompress,
    sha256_of_bytes,
)

#: 快照 payload 的九字段（顺序固定，仅用于构造 dict；规范化靠 sort_keys）
PAYLOAD_FIELDS = (
    'name', 'description', 'category', 'tags', 'metrics', 'results',
    'audios', 'reference_params', 'algorithm_results',
)

#: 行上 4 个指针列（顺序与迁移脚本 / ORM 一致）
POINTER_COLUMNS = (
    'snapshot_uri', 'snapshot_sha256', 'snapshot_bytes', 'snapshot_created_at',
)

URI_SCHEME = 'db://report_case_snapshots/'

#: 读源开关：snapshot（默认，解引用）| column（R1 回滚：读行上内容列）
SOURCE_ENV = 'REPORT_CASE_SNAPSHOT_SOURCE'
SOURCE_SNAPSHOT = 'snapshot'
SOURCE_COLUMN = 'column'


class ReportCaseSnapshotError(RuntimeError):
    """快照外置读写错误基类。"""


class ReportCaseSnapshotMissingError(ReportCaseSnapshotError):
    """行上有指针/或者指针为空，但快照行不存在（门禁未归零 / 指针悬空）。"""


class ReportCaseSnapshotCorruptError(ReportCaseSnapshotError):
    """快照行在，但解压失败 / sha256 与指针不符 / JSON 解析失败。"""


@dataclass(frozen=True)
class SnapshotPointer:
    """一份 payload 对应的快照指针（写入侧构造、回写行上 4 列）"""

    sha256: str
    size_bytes: int
    created_at: datetime

    @property
    def uri(self) -> str:
        return f'{URI_SCHEME}{self.sha256}'


# ------------------------------------------------------------------ 读源开关

def read_source() -> str:
    """当前读源：``snapshot``（默认）或 ``column``。

    开关是回滚通道，取值非法时按默认 ``snapshot`` 处理（宁可按新口径读并在
    数据缺失时显式报错，也不静默退回旧口径掩盖回填缺口）。
    """
    raw = (os.environ.get(SOURCE_ENV) or '').strip().lower()
    return SOURCE_COLUMN if raw == SOURCE_COLUMN else SOURCE_SNAPSHOT


# ------------------------------------------------------------------ payload 构造

def build_payload(values: Dict[str, Any]) -> Dict[str, Any]:
    """从**原始列值**构造九字段 payload。

    ``values`` 可以是 ``add_case`` 的入参 dict，也可以是导入 / 替换链路里的一行
    dict —— 一律直接取值，**不做任何 falsy 归一**。

    为什么强调原值：``report_aggregation/cases_mixin.py`` 的 ``rs.get('metrics')
    or {}`` 与 ``report_compare_helpers.py`` 的 ``case_record.metrics or {}`` 会把
    ``[]`` 折成 ``{}``（库里 ``metrics`` 为 ``[]`` 的有 2,095 行），折了就不是逐字节
    冻结。快照必须与行上列值同源同值。
    """
    return {field: values.get(field) for field in PAYLOAD_FIELDS}


def payload_sha(payload: Dict[str, Any]) -> str:
    return sha256_of_bytes(canonical_bytes(payload))


# ------------------------------------------------------------------ 写

def _insert_statement(session, values: Dict[str, Any]):
    """按方言生成 ``INSERT … ON CONFLICT (sha256) DO NOTHING``。

    PG / SQLite 都支持 ON CONFLICT；其它方言退化为「先查存在再插入」（仅测试
    兜底，生产是 PG）。
    """
    from report_service.infrastructure.persistence.models import ReportCaseSnapshot

    dialect = session.bind.dialect.name if session.bind is not None else ''
    if dialect == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert as _insert
    elif dialect == 'sqlite':
        from sqlalchemy.dialects.sqlite import insert as _insert
    else:  # 兜底方言
        return None
    return _insert(ReportCaseSnapshot).values(**values).on_conflict_do_nothing(
        index_elements=['sha256'])


def put(session, payload: Dict[str, Any], *, created_at: Optional[datetime] = None
        ) -> SnapshotPointer:
    """写入一份快照（幂等：同 sha 并发插入天然收敛，不需要分布式锁）。

    Args:
        session: 当前事务的 session（与用例行同一事务，保证「先快照后行」）
        payload: 九字段 payload（见 :func:`build_payload`）
        created_at: 快照写入时间；默认当前时刻（在线写入路径）

    Returns:
        指针（sha256 / 压缩后字节数 / 写入时间）
    """
    from report_service.infrastructure.persistence.models import ReportCaseSnapshot

    raw = canonical_bytes(payload)
    sha = sha256_of_bytes(raw)
    data = compress(raw)
    created = created_at or utc8now()
    stmt = _insert_statement(session, {
        'sha256': sha,
        'payload_gz': data,
        'payload_bytes': len(data),
        'created_at': created,
    })
    if stmt is not None:
        session.execute(stmt)
    else:  # pragma: no cover - 仅无 ON CONFLICT 的方言
        exists = session.query(ReportCaseSnapshot.sha256).filter(
            ReportCaseSnapshot.sha256 == sha).first()
        if exists is None:
            session.add(ReportCaseSnapshot(
                sha256=sha, payload_gz=data, payload_bytes=len(data),
                created_at=created))
    return SnapshotPointer(sha256=sha, size_bytes=len(data), created_at=created)


def apply_pointer(target, pointer: Optional[SnapshotPointer]) -> None:
    """把指针写到目标行（ORM 对象或属性容器）的 4 列；None 时 4 列一并置空。"""
    values = (None, None, None, None) if pointer is None else (
        pointer.uri, pointer.sha256, pointer.size_bytes, pointer.created_at)
    for column, value in zip(POINTER_COLUMNS, values):
        setattr(target, column, value)


def apply_to_row(session, row: Dict[str, Any]) -> Dict[str, Any]:
    """导入 / 搬运 / 替换链路：按行上的内容列重算快照并覆盖指针列。

    ``report_transfer_repository`` / ``report_replacement_repository`` 是通用整表
    拷贝：加了指针列之后，导出会把 ``snapshot_sha256`` 一起带走，而
    ``report_case_snapshots`` 并不同行迁移 → 导进目标库就是**悬空指针**。

    口径：**内容列与指针同时存在时以内容列为准重算并覆盖指针**（避免导入了别的
    环境的 sha）。纯指针行（九字段内容列一个都没有，M1 之后才会出现）原样保留。
    ``snapshot_created_at`` 优先沿用源行的值 / 源行 ``created_at``，保持「内容生成
    时间」语义，不回退成导入时刻。
    """
    if not any(field in row for field in PAYLOAD_FIELDS):
        return row
    pointer = put(session, build_payload(row))
    prepared = dict(row)
    prepared['snapshot_uri'] = pointer.uri
    prepared['snapshot_sha256'] = pointer.sha256
    prepared['snapshot_bytes'] = pointer.size_bytes
    prepared['snapshot_created_at'] = (
        row.get('snapshot_created_at') or row.get('created_at') or pointer.created_at)
    return prepared


# ------------------------------------------------------------------ 读

def _to_bytes(value) -> bytes:
    """bytea 列 → bytes（psycopg2 给 memoryview，sqlite 给 bytes）。"""
    if isinstance(value, memoryview):
        return value.tobytes()
    return bytes(value or b'')


def fetch_batch(session, shas: Sequence[str], report_id: Optional[int] = None
                ) -> Dict[str, Dict[str, Any]]:
    """一次批量取回多份 payload：``{sha256: payload}``。

    解压后校验 sha256，不符即抛 :class:`ReportCaseSnapshotCorruptError`
    （message 带 report_id / sha256）；快照行不存在同样由调用方据此显式报错。
    """
    from report_service.infrastructure.persistence.models import ReportCaseSnapshot

    wanted = sorted({str(sha or '').strip() for sha in shas if sha})
    if not wanted:
        return {}
    rows = (session.query(ReportCaseSnapshot.sha256, ReportCaseSnapshot.payload_gz)
            .filter(ReportCaseSnapshot.sha256.in_(wanted))
            .all())
    payloads: Dict[str, Dict[str, Any]] = {}
    for sha, gz in rows:
        key = str(sha or '').strip()
        try:
            raw = decompress(_to_bytes(gz))
        except OSError as exc:
            raise ReportCaseSnapshotCorruptError(
                f'报告 {report_id} 的快照 {key} 解压失败: {exc}') from exc
        actual = sha256_of_bytes(raw)
        if actual != key:
            raise ReportCaseSnapshotCorruptError(
                f'报告 {report_id} 的快照 {key} sha256 校验失败：实际 {actual}')
        try:
            value = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ReportCaseSnapshotCorruptError(
                f'报告 {report_id} 的快照 {key} JSON 解析失败: {exc}') from exc
        payloads[key] = value
    return payloads


class ResolvedReportCase:
    """解引用后的用例行：**属性名与 ``ReportCase`` PO 完全一致**。

    上层（``_case_po_to_entity`` / ``report_compare_helpers``）按属性名读，一行
    不用改。这里刻意不用 dict，避免下层改动扩散到所有消费方。
    """

    __slots__ = ('id', 'report_id', 'test_case_id', 'algorithm_type', 'logs',
                 'snapshot_uri', 'snapshot_sha256', 'snapshot_bytes',
                 'snapshot_created_at') + PAYLOAD_FIELDS

    def __init__(self, row, payload: Dict[str, Any]):
        self.id = row.id
        self.report_id = row.report_id
        self.test_case_id = row.test_case_id
        self.algorithm_type = row.algorithm_type
        self.logs = row.logs
        self.snapshot_uri = getattr(row, 'snapshot_uri', None)
        self.snapshot_sha256 = getattr(row, 'snapshot_sha256', None)
        self.snapshot_bytes = getattr(row, 'snapshot_bytes', None)
        self.snapshot_created_at = getattr(row, 'snapshot_created_at', None)
        for field in PAYLOAD_FIELDS:
            setattr(self, field, payload.get(field))

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return (f'<ResolvedReportCase id={self.id} report_id={self.report_id} '
                f'sha256={self.snapshot_sha256}>')


def resolve_rows(session, rows: Iterable, report_id: Optional[int] = None) -> List:
    """按读源开关解引用一批 ``report_cases`` 行。

    - ``REPORT_CASE_SNAPSHOT_SOURCE=column``：原样返回行（R1 回滚通道）。
    - 默认 ``snapshot``：一次批量取回 ``payload_gz``，解压 + 校验后返回
      :class:`ResolvedReportCase`（属性名不变）。

    失败语义（硬约束）：行上没有指针、或指针指向的快照行不存在、或 sha 不符，
    一律**显式抛错**——禁止返回空 ``cases``，禁止回退内容列（否则兼容层会一直
    活到 M1 之后）。R1 期间列还在，更要守住这一条。
    """
    rows = list(rows or [])
    if not rows or read_source() == SOURCE_COLUMN:
        return rows

    shas = []
    for row in rows:
        sha = str(getattr(row, 'snapshot_sha256', None) or '').strip()
        if not sha:
            raise ReportCaseSnapshotMissingError(
                f'报告 {report_id} 的用例行 id={getattr(row, "id", None)} 没有快照指针'
                f'（snapshot_sha256 IS NULL）：回填门禁未归零，不能切快照读源；'
                f'确认 `--gate` 为 0 或临时设 {SOURCE_ENV}={SOURCE_COLUMN}')
        shas.append(sha)

    payloads = fetch_batch(session, shas, report_id=report_id)
    resolved: List[ResolvedReportCase] = []
    for row, sha in zip(rows, shas):
        payload = payloads.get(sha)
        if payload is None:
            raise ReportCaseSnapshotMissingError(
                f'报告 {report_id} 的快照行不存在：sha256={sha} '
                f'（report_cases.id={getattr(row, "id", None)}）——指针悬空')
        resolved.append(ResolvedReportCase(row, payload))
    return resolved
