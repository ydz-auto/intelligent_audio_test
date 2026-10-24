# -*- coding: utf-8 -*-
"""logs 表流式归档清理（INT-1785）。

背景：业务日志已去库化（INT-81，落 `logs/{service}/` 与 `logs/business/`），
DB 里 `logs` 只剩两类数据——**历史存量**与**仍在落库的审计事件**
（auth / device / benchmark 经 `log_not_emit` 旁路写入）。存量 30 万行 / 249MB
且无保留策略。

既有 `LogRepository.archive()` 把全部冷日志一次性 `order_by().all()` 读进内存、
按组整包经 gRPC 返回给网关再写 OSS，这个量级会撑爆内存与 gRPC 报文上限。
本模块提供「分批读 → 分批归档 → 分批删」的流式实现，供：

1. 一次性历史清理脚本 `scripts/maintenance/purge_legacy_logs_int1785.py`；
2. task_service 每日保留清扫 `log_retention_cleaner.py`。

归档格式与 `api_gateway/.../log_command_service.py` 写出的文件完全一致，
否则归档数据在日志页读不到：

- key：`archives/{group}.json`，group 分组规则照 `LogRepository.archive()`——
  task+case → `tasks/{task_id}/{case_id}/{date}`；仅 task → `tasks/{task_id}/{date}`；
  仅 case → `cases/{case_id}/{date}`；其余 → `other/{date}`；
- value：JSON 数组，元素字段照 `_log_po_to_dict`，按 `time` 升序。

安全不变量（本模块的唯一硬约束）：**归档写成功之后才删该批**。
某批归档写失败时该批一行不删，由调用方决定是否重试（重跑幂等）。
合并同名文件时按 `id` 去重——上一轮「已归档未删成」的行重跑不会重复入库。
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import func as _func
from sqlalchemy import or_ as _or

from shared.models.database import get_db_session
from task_service.infrastructure.persistence.models.system_models import Log

logger = logging.getLogger(__name__)

# 归档在统一存储层的类目名（与网关 archive_logs / 读侧 get_archived_logs 同口径）
ARCHIVE_STORAGE_CATEGORY = 'archives'
ARCHIVE_FILE_SUFFIX = '.json'

# 审计类日志分类（大小写不敏感）：仍在落库，按合规要求保留在库里，
# 默认不参与历史清理与每日清扫。`System`/`system` 这类历史脏值不算审计类。
AUDIT_LOG_CATEGORIES = frozenset({'auth', 'device', 'benchmark'})


class ArchiveFormatError(RuntimeError):
    """已有归档文件内容不是 JSON 数组（宁可整批中止也不覆盖既有归档）。"""


def is_audit_category(category: Any) -> bool:
    """分类是否属于仍在落库的审计类（大小写不敏感）。"""
    return str(category or '').strip().lower() in AUDIT_LOG_CATEGORIES


def build_group_key(task_id: Any, test_case_id: Any, log_date: str) -> str:
    """按 `LogRepository.archive()` 的分组规则生成归档逻辑 key（不含 category 前缀）。

    - task + case → `tasks/{task_id}/{test_case_id}/{date}`
    - 仅 task     → `tasks/{task_id}/{date}`
    - 仅 case     → `cases/{test_case_id}/{date}`
    - 其余        → `other/{date}`
    """
    if task_id and test_case_id:
        return f'tasks/{task_id}/{test_case_id}/{log_date}'
    if task_id:
        return f'tasks/{task_id}/{log_date}'
    if test_case_id:
        return f'cases/{test_case_id}/{log_date}'
    return f'other/{log_date}'


def log_po_to_archive_entry(po: Log) -> Dict[str, Any]:
    """Log PO → 归档条目 dict（字段与 `_log_po_to_dict` 保持一致）。"""
    return {
        'id': po.id,
        'time': po.time.isoformat() if po.time else None,
        'level': po.level,
        'category': po.category,
        'module': po.module,
        'source': po.source,
        'content': po.content,
        'mark': po.mark,
        'device_id': po.device_id,
        'task_id': po.task_id,
        'api_id': po.api_id,
        'test_case_id': po.test_case_id,
        'thread_id': po.thread_id,
        'algorithm_type': po.algorithm_type,
        'created_by_user_id': po.created_by_user_id,
        'created_at': po.created_at.isoformat() if po.created_at else None,
    }


def _entry_identity(entry: Dict[str, Any]):
    """归档条目的去重身份：id 唯一；无 id 的条目（历史脏数据）不去重。"""
    if not isinstance(entry, dict):
        return None
    log_id = entry.get('id')
    if log_id in (None, ''):
        return None
    return str(log_id)


def merge_archive_entries(existing: Sequence[Dict[str, Any]],
                          incoming: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """合并已有条目与新条目：按 id 去重（已有优先），按 time 升序排列。

    重跑语义：上一轮归档写成功但删除失败时，下一轮会再次读到同一批行；
    去掉重复 id 后合并结果与首轮一致（幂等）。
    """
    merged: List[Dict[str, Any]] = list(existing)
    seen = set()
    for entry in merged:
        identity = _entry_identity(entry)
        if identity is not None:
            seen.add(identity)
    for entry in incoming:
        identity = _entry_identity(entry)
        if identity is not None:
            if identity in seen:
                continue
            seen.add(identity)
        merged.append(entry)
    # 稳定排序：time 相同的条目保持「已有在前、新增在后」的相对顺序
    merged.sort(key=lambda item: (item.get('time') or '') if isinstance(item, dict) else '')
    return merged


def load_archive_entries(storage, group_key: str) -> List[Dict[str, Any]]:
    """读取已有归档文件条目；文件不存在返回空列表。

    文件存在但内容不是 JSON 数组时抛 `ArchiveFormatError`：调用方会中止该批
    （不删除），避免像既有网关实现那样把读不出来的旧归档直接覆盖掉。
    """
    path = f'{ARCHIVE_STORAGE_CATEGORY}/{group_key}{ARCHIVE_FILE_SUFFIX}'
    if not storage.exists(path):
        return []
    data = storage.load_bytes(path)
    if not data:
        return []
    try:
        parsed = json.loads(data)
    except ValueError as e:
        raise ArchiveFormatError(f'归档文件不是合法 JSON: {path}: {e}') from e
    if not isinstance(parsed, list):
        raise ArchiveFormatError(f'归档文件顶层不是数组: {path}')
    return parsed


def write_archive_entries(storage, group_key: str,
                          entries: Sequence[Dict[str, Any]]) -> str:
    """写出归档文件（整体覆盖），返回带 category 前缀的存储路径。"""
    key = f'{group_key}{ARCHIVE_FILE_SUFFIX}'
    payload = json.dumps(list(entries), ensure_ascii=False, indent=2).encode('utf-8')
    storage.save_bytes(payload, ARCHIVE_STORAGE_CATEGORY, key,
                       content_type='application/json')
    return f'{ARCHIVE_STORAGE_CATEGORY}/{key}'


@dataclass
class PurgeResult:
    """一次清理的结果（脚本打印 / 每日清扫日志共用）。"""

    archived_count: int = 0
    deleted_count: int = 0
    batch_count: int = 0
    # 去重后的归档文件数（同一文件可能被多批追加，写次数另计）
    archived_file_count: int = 0
    archive_write_count: int = 0
    remaining_count: Optional[int] = None
    failed: bool = False
    failure_reason: str = ''
    elapsed_seconds: float = 0.0
    # 每批完成后的进度快照（失败时用于打印「已完成批次」）
    completed_batches: List[Dict[str, int]] = field(default_factory=list)


class LogArchivePurger:
    """按截止时间分批归档并删除 logs 行（流式，内存上界 = batch_size）。

    参数：
      storage: 统一存储层（`shared.infrastructure.storage.storage`），测试可注入；
      batch_size: 单批行数（同时是内存上界）；
      categories: 显式指定参与清理的分类；None = 全部非审计类；
      exclude_audit: categories 为 None 时是否排除审计类（默认 True）；
      dry_run: 只统计不写不删；
      on_batch: 进度回调 `(batch_index, archived, deleted) -> None`。
    """

    def __init__(self, storage=None, batch_size: int = 2000,
                 categories: Optional[Sequence[str]] = None,
                 exclude_audit: bool = True, dry_run: bool = False,
                 on_batch: Optional[Callable[[int, int, int], None]] = None):
        self._storage = storage
        self.batch_size = max(1, int(batch_size))
        self.categories = [c.strip().lower() for c in (categories or []) if str(c).strip()]
        self.exclude_audit = exclude_audit
        self.dry_run = dry_run
        self.on_batch = on_batch

    # ---- 存储层延迟解析（脚本/服务都不必显式依赖 OSS）----
    @property
    def storage(self):
        if self._storage is None:
            from shared.infrastructure.storage import storage as default_storage
            self._storage = default_storage
        return self._storage

    # ---- 查询条件 ----
    def _apply_filters(self, query, cutoff: datetime):
        query = query.filter(Log.time < cutoff)
        if self.categories:
            query = query.filter(_func.lower(Log.category).in_(self.categories))
        elif self.exclude_audit:
            # category 为 NULL 时 `NOT IN` 结果为 NULL（行被静默排除），显式放行
            query = query.filter(_or(
                Log.category.is_(None),
                ~_func.lower(Log.category).in_(sorted(AUDIT_LOG_CATEGORIES)),
            ))
        return query

    def count(self, cutoff: datetime) -> int:
        """符合清理条件的行数。"""
        session = get_db_session()
        try:
            return self._apply_filters(session.query(Log), cutoff).count()
        finally:
            session.close()

    def remaining(self) -> int:
        """logs 表剩余总行数（成功的唯一验收口径）。"""
        session = get_db_session()
        try:
            return session.query(_func.count(Log.id)).scalar() or 0
        finally:
            session.close()

    # ---- 主流程 ----
    def run(self, cutoff: datetime) -> PurgeResult:
        started = time.monotonic()
        result = PurgeResult()
        if self.dry_run:
            result.archived_count = self.count(cutoff)
            result.remaining_count = self.remaining()
            result.elapsed_seconds = time.monotonic() - started
            return result

        last_id = 0
        touched = set()
        while True:
            batch = self._fetch_batch(cutoff, last_id)
            if not batch:
                break
            last_id = batch[-1].id
            try:
                written_keys = self._archive_batch(batch)
            except Exception as e:  # noqa: BLE001 - 任何归档异常都不允许继续删
                result.failed = True
                result.failure_reason = f'第 {result.batch_count + 1} 批归档失败: {e}'
                logger.error('[logs 归档清理] %s，该批 %s 行未删除',
                             result.failure_reason, len(batch))
                break

            try:
                deleted = self._delete_batch([po.id for po in batch])
            except Exception as e:  # noqa: BLE001 - 归档已落盘，行留在库里等下一轮
                result.failed = True
                result.failure_reason = f'第 {result.batch_count + 1} 批删除失败: {e}'
                logger.error('[logs 归档清理] %s，该批 %s 行未删除（归档已写出）',
                             result.failure_reason, len(batch))
                break

            result.batch_count += 1
            result.archived_count += len(batch)
            result.deleted_count += deleted
            result.archive_write_count += len(written_keys)
            touched.update(written_keys)
            result.completed_batches.append({
                'batch': result.batch_count,
                'archived': len(batch),
                'deleted': deleted,
            })
            if self.on_batch is not None:
                self.on_batch(result.batch_count, len(batch), deleted)

        result.archived_file_count = len(touched)
        result.remaining_count = self.remaining()
        result.elapsed_seconds = time.monotonic() - started
        return result

    def _fetch_batch(self, cutoff: datetime, last_id: int) -> List[Log]:
        """keyset 分页（按自增 id）：删除不影响游标，也不会 OFFSET 漂移。"""
        session = get_db_session()
        try:
            return (self._apply_filters(session.query(Log), cutoff)
                    .filter(Log.id > last_id)
                    .order_by(Log.id.asc())
                    .limit(self.batch_size)
                    .all())
        finally:
            session.close()

    def _archive_batch(self, batch: Sequence[Log]) -> List[str]:
        """把一批行按归档 key 分组、与已有文件合并后写回；返回本批写过的 key 列表。

        整批写成功才返回；任一文件写失败直接抛出（调用方不删该批）。
        """
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for po in batch:
            log_date = (po.time or datetime.now()).strftime('%Y-%m-%d')
            key = build_group_key(po.task_id, po.test_case_id, log_date)
            grouped.setdefault(key, []).append(log_po_to_archive_entry(po))

        for key, entries in grouped.items():
            existing = load_archive_entries(self.storage, key)
            write_archive_entries(self.storage, key, merge_archive_entries(existing, entries))
        return list(grouped)

    def _delete_batch(self, log_ids: List[int]) -> int:
        """单批独立事务删除并校验条数；条数不符只告警（不中断整轮）。"""
        session = get_db_session()
        try:
            deleted = (session.query(Log)
                       .filter(Log.id.in_(log_ids))
                       .delete(synchronize_session=False))
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        _clear_aggregate_cache()
        if deleted != len(log_ids):
            logger.warning('[logs 归档清理] 批次删除条数不符: 期望 %s 实际 %s',
                           len(log_ids), deleted)
        return int(deleted or 0)


def _clear_aggregate_cache() -> None:
    """删除后让同进程的日志聚合缓存失效（读侧 total/stats 立即变准）。"""
    try:
        from task_service.infrastructure.persistence.log_repository import _agg_cache_clear
        _agg_cache_clear()
    except Exception:  # noqa: BLE001 - 缓存失效失败不影响清理正确性
        logger.debug('[logs 归档清理] 聚合缓存失效失败', exc_info=True)


def parse_categories(raw: str) -> Optional[List[str]]:
    """`--categories`（逗号分隔）→ 列表；空串 = 默认口径（全部非审计类）。"""
    items = [part.strip() for part in str(raw or '').split(',') if part.strip()]
    return items or None
