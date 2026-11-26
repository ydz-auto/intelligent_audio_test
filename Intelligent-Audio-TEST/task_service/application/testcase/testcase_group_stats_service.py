# -*- coding: utf-8 -*-
"""分组时长统计读模型服务（CQRS 读侧：DB 物化 + Redis 读缓存）。

分组列表组头「总时长」原先每次遍历组内用例 config 现算，且只在组内用例
分页加载后才有值。改为：
- DB：``test_case_group_stats`` 物化 ``total_duration`` + ``stats_updated_at``
  （权威数据，Redis/进程重启后可回源）；
- Redis：按分组字段缓存的读缓存（命中直接返回，避免重复读库与现算）；
- 失效：用例/分组写路径调用 :func:`invalidate_group_stats` 删除读模型行与缓存，
  下次列表读取惰性重算并回写；
- 过期：Redis 字段与 DB 行均按 ``STATS_TTL_SECONDS`` 判过期，过期即重算。

降级：Redis 不可用或读模型表未就绪时，退化为实时计算，不阻塞分组列表。
"""
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

_REDIS_KEY = 'testcase_group_stats'
_CACHE_TTL_SECONDS = 60
_STATS_TTL_SECONDS = 60


def _repo():
    from task_service.infrastructure.persistence.testcase_repository import (
        testcase_repository,
    )
    return testcase_repository


def _store():
    from shared.utils.redis_pubsub import RedisStore
    return RedisStore()


def _now_ts() -> float:
    return time.time()


def _db_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _db_row_fresh(stats_updated_at) -> bool:
    if stats_updated_at is None:
        return False
    return (_db_now() - stats_updated_at).total_seconds() <= _STATS_TTL_SECONDS


def _cache_load() -> Dict[str, dict]:
    """读取 Redis 读缓存（{group_id: {total_duration, ts}}）；异常按未命中降级。"""
    try:
        raw = _store().load_task(_REDIS_KEY) or {}
        return {str(k): v for k, v in raw.items() if isinstance(v, dict)}
    except Exception as e:
        logger.warning('[GroupStats] Redis 读取降级: %s', e)
        return {}


def _cache_save(entries: Dict[str, dict]) -> None:
    if not entries:
        return
    try:
        _store().save_task(_REDIS_KEY, entries, ttl_seconds=_CACHE_TTL_SECONDS)
    except Exception as e:
        logger.warning('[GroupStats] Redis 写入降级: %s', e)


def invalidate_group_stats(group_ids: Optional[Iterable[str]] = None) -> None:
    """失效分组时长统计（用例/分组写路径调用；None = 全部分组）。

    只失效不重算：重算交给下一次分组列表读取（避免批量写路径逐条现算）。
    """
    ids = None if group_ids is None else [str(g) for g in group_ids if g]
    try:
        store = _store()
        if ids is None:
            store.delete_task(_REDIS_KEY)
        elif ids:
            store.remove_fields(_REDIS_KEY, *ids)
    except Exception as e:
        logger.warning('[GroupStats] Redis 失效降级: %s', e)
    try:
        _repo().delete_group_stats(ids)
    except Exception as e:
        logger.warning('[GroupStats] 读模型失效降级（等待 TTL 过期重算）: %s', e)


def get_group_durations(group_ids: Iterable[str]) -> Dict[str, float]:
    """取分组总时长（秒）：Redis → DB 读模型 → 实时计算回源并回写。"""
    ids = [str(g) for g in group_ids if g]
    if not ids:
        return {}

    result: Dict[str, float] = {}
    missing: List[str] = []
    cached = _cache_load()
    for group_id in ids:
        entry = cached.get(group_id)
        if entry is not None and _now_ts() - float(entry.get('ts') or 0) <= _CACHE_TTL_SECONDS:
            result[group_id] = float(entry.get('total_duration') or 0.0)
        else:
            missing.append(group_id)
    if not missing:
        return result

    db_rows: Dict[str, dict] = {}
    try:
        db_rows = _repo().read_group_stats(missing)
    except Exception as e:
        logger.warning('[GroupStats] 读模型读取降级（走实时计算）: %s', e)

    to_compute: List[str] = []
    backfill: Dict[str, dict] = {}
    for group_id in missing:
        row = db_rows.get(group_id)
        if row is not None and _db_row_fresh(row.get('stats_updated_at')):
            result[group_id] = float(row.get('total_duration') or 0.0)
            backfill[group_id] = {
                'total_duration': result[group_id], 'ts': _now_ts()}
        else:
            to_compute.append(group_id)
    _cache_save(backfill)

    if to_compute:
        try:
            computed = _repo().compute_group_durations(to_compute)
        except Exception as e:
            logger.warning('[GroupStats] 实时计算降级（本次不显示时长）: %s', e)
            computed = {}
        # 0 时长也落库/落缓存，避免无音频分组每次读取都回源现算
        values = {gid: float(computed.get(gid) or 0.0) for gid in to_compute}
        result.update(values)
        _cache_save({
            gid: {'total_duration': value, 'ts': _now_ts()}
            for gid, value in values.items()
        })
        try:
            _repo().upsert_group_stats(values)
        except Exception as e:
            logger.warning('[GroupStats] 读模型回写降级: %s', e)
    return result
