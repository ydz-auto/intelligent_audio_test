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

「写成功」与「不存在」的判定走 `ArchiveStore`（严格语义），不走
`shared.infrastructure.storage.Storage`：后者 OSS 写失败会静默降级写本地磁盘并
返回 `local://`，且 `exists()`/`load_bytes()` 把 OSS 读失败吞掉回落本地副本——
删库前用它会把「归档只在本地」当成成功（丢归档），或把「读失败」当成「文件不
存在」而整文件覆盖（丢老条目）。`ArchiveStore` 只接受真 OSS 落盘，读失败一律
中止该批。
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


class ArchiveStoreError(RuntimeError):
    """归档对象存储走不通：该批一行都不能删（宁可留着，不能丢归档）。"""


# 对象存储明确表示「没有这个 key」的错误码；只有这些才算「文件不存在」
_NOT_FOUND_ERROR_CODES = frozenset({'NoSuchKey', 'NoSuchObject', 'NotFound', '404'})
_ARCHIVE_CONTENT_TYPE = 'application/json'


def is_not_found_error(exc: BaseException) -> bool:
    """存储异常是否是「对象不存在」。

    连接失败 / 超时 / 权限 / 5xx 一律 **不算** 不存在——把它们当成不存在就是
    INT-1785 P1-2 丢归档的根因。
    """
    try:
        from botocore.exceptions import ClientError
    except Exception:  # noqa: BLE001 - 没有 botocore 时一律按「失败」处理
        return False
    if not isinstance(exc, ClientError):
        return False
    response = getattr(exc, 'response', None) or {}
    code = str((response.get('Error') or {}).get('Code', ''))
    status = (response.get('ResponseMetadata') or {}).get('HTTPStatusCode')
    return code in _NOT_FOUND_ERROR_CODES or status == 404


class ArchiveStore:
    """归档对象的严格读写端口（删库前唯一的存储访问入口）。

    与 `shared.infrastructure.storage.Storage` 的差异正是本卡失败安全的落点：

    - 写：只走对象存储，失败直接抛 `ArchiveStoreError`，**不做本地降级**；
      写完用 head 回查，确认对象真的在 OSS 里，才算归档成功；
    - 读：只有对象存储明确回「不存在」才返回 None；读失败抛
      `ArchiveStoreError`，调用方中止该批（数据保留），绝不覆盖既有归档。

    参数 `client` 是对象存储客户端（默认 `shared.clients.oss_client.oss`），
    需实现 `download_bytes / upload_bytes / exists`（与 `OSSClient` 一致）。
    """

    def __init__(self, client=None):
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from shared.clients.oss_client import oss as default_client
            self._client = default_client
        return self._client

    def read_bytes(self, category: str, key: str) -> Optional[bytes]:
        """读对象；返回 None 仅代表「确认不存在」，其余异常都抛出。"""
        try:
            return self.client.download_bytes(category, key)
        except Exception as e:  # noqa: BLE001 - 读失败不能当作不存在
            if is_not_found_error(e):
                return None
            raise ArchiveStoreError(
                f'归档对象读取失败（不当作「不存在」）: {category}/{key}: {e}') from e

    def write_bytes(self, category: str, key: str, payload: bytes) -> str:
        """写对象并回查落盘；返回 `{category}/{key}`。"""
        try:
            self.client.upload_bytes(payload, category, key,
                                     content_type=_ARCHIVE_CONTENT_TYPE)
        except Exception as e:  # noqa: BLE001 - 禁止降级本地后再删库
            raise ArchiveStoreError(
                f'归档对象写入 OSS 失败（不允许降级本地后删库）: {category}/{key}: {e}') from e

        try:
            landed = bool(self.client.exists(category, key))
        except Exception as e:  # noqa: BLE001 - 回查失败也不能认为写成功
            raise ArchiveStoreError(
                f'归档对象写后回查失败（无法确认已落 OSS）: {category}/{key}: {e}') from e
        if not landed:
            raise ArchiveStoreError(
                f'归档对象写后回查不存在（无法确认已落 OSS）: {category}/{key}')
        return f'{category}/{key}'


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


def load_archive_entries(store: ArchiveStore, group_key: str) -> List[Dict[str, Any]]:
    """读取已有归档文件条目；对象确认不存在返回空列表。

    读失败抛 `ArchiveStoreError`、内容不是 JSON 数组抛 `ArchiveFormatError`：
    两种都由调用方中止该批（不删除），避免像既有网关实现那样把读不出来的旧归档
    直接覆盖掉。
    """
    key = f'{group_key}{ARCHIVE_FILE_SUFFIX}'
    data = store.read_bytes(ARCHIVE_STORAGE_CATEGORY, key)
    if not data:
        return []
    try:
        parsed = json.loads(data)
    except ValueError as e:
        raise ArchiveFormatError(
            f'归档文件不是合法 JSON: {ARCHIVE_STORAGE_CATEGORY}/{key}: {e}') from e
    if not isinstance(parsed, list):
        raise ArchiveFormatError(
            f'归档文件顶层不是数组: {ARCHIVE_STORAGE_CATEGORY}/{key}')
    return parsed


def write_archive_entries(store: ArchiveStore, group_key: str,
                          entries: Sequence[Dict[str, Any]]) -> str:
    """写出归档文件（整体覆盖），返回带 category 前缀的存储路径。"""
    key = f'{group_key}{ARCHIVE_FILE_SUFFIX}'
    payload = json.dumps(list(entries), ensure_ascii=False, indent=2).encode('utf-8')
    return store.write_bytes(ARCHIVE_STORAGE_CATEGORY, key, payload)


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
      store: 归档对象存储端口 `ArchiveStore`（默认按 OSS 客户端延迟构造）；
      batch_size: 单批行数（同时是内存上界）；
      categories: 显式指定参与清理的分类；None = 全部非审计类；
      exclude_audit: categories 为 None 时是否排除审计类（默认 True）；
      keep_marked: 是否保留已标记行（默认 True，契约 §Q5.1：DB 侧清扫必须保留
          `mark` 非空的行；判据与 `LogRepository.clear(keep_marked=True)` 一致，
          归档与删除同一条件）；
      dry_run: 只统计不写不删；
      on_batch: 进度回调 `(batch_index, archived, deleted) -> None`。
    """

    def __init__(self, store: Optional[ArchiveStore] = None, batch_size: int = 2000,
                 categories: Optional[Sequence[str]] = None,
                 exclude_audit: bool = True, keep_marked: bool = True,
                 dry_run: bool = False,
                 on_batch: Optional[Callable[[int, int, int], None]] = None):
        self._store = store
        self.batch_size = max(1, int(batch_size))
        self.categories = [c.strip().lower() for c in (categories or []) if str(c).strip()]
        self.exclude_audit = exclude_audit
        self.keep_marked = keep_marked
        self.dry_run = dry_run
        self.on_batch = on_batch

    # ---- 存储端口延迟解析（脚本/服务都不必显式依赖 OSS）----
    @property
    def store(self) -> ArchiveStore:
        if self._store is None:
            self._store = ArchiveStore()
        return self._store

    # ---- 查询条件 ----
    def _apply_filters(self, query, cutoff: datetime):
        query = query.filter(Log.time < cutoff)
        if self.keep_marked:
            # 契约 §Q5.1：已标记行是排查期留痕，不参与清扫（归档与删除同一条件）。
            # 判据照 `LogRepository.clear(keep_marked=True)`：NULL 与空串都算未标记。
            query = query.filter(_or(Log.mark.is_(None), Log.mark == ''))
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
        """执行一轮清理；**不向上抛异常**（DB 中断也走 failed + 已完成批次）。

        任何未预期异常（含 psycopg2 连接中断、库启动中等）都只记在本轮结果里，
        调用方据此打印统计并非零退出；已提交的批次数据与归档保持一致。
        """
        started = time.monotonic()
        result = PurgeResult()
        try:
            self._run_batches(cutoff, result)
        except Exception as e:  # noqa: BLE001 - 保留数据，交给调用方报错
            result.failed = True
            if not result.failure_reason:
                if self.dry_run:
                    result.failure_reason = f'dry-run 统计失败: {e}'
                else:
                    result.failure_reason = (
                        f'第 {result.batch_count + 1} 批读取失败: {e}')
            logger.error('[logs 归档清理] %s（已完成 %s 批：归档 %s 条、删除 %s 条）',
                         result.failure_reason, result.batch_count,
                         result.archived_count, result.deleted_count)
        finally:
            result.elapsed_seconds = time.monotonic() - started
        return result

    def _run_batches(self, cutoff: datetime, result: PurgeResult) -> None:
        if self.dry_run:
            result.archived_count = self.count(cutoff)
            result.remaining_count = self.remaining()
            return

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
        try:
            result.remaining_count = self.remaining()
        except Exception as e:  # noqa: BLE001 - 统计失败不改已完成的清理结果
            result.failed = True
            result.failure_reason = result.failure_reason or f'统计剩余条数失败: {e}'
            logger.error('[logs 归档清理] %s', result.failure_reason)

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
            existing = load_archive_entries(self.store, key)
            write_archive_entries(self.store, key, merge_archive_entries(existing, entries))
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
