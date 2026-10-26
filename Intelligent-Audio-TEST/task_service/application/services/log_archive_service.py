# -*- coding: utf-8 -*-
"""日志归档应用服务（INT-1963）。

把 ``ArchiveLogs`` 从「先删库、再把全量分组塞进一条 gRPC 响应」改成按批推进：

1. 取一批冷日志（``LogArchivePurger._fetch_batch``，只读，不删）；
2. 按分组与已有归档对象合并后写入 —— 写入走 ``ArchiveStore``（只写真 OSS、
   写完 head 回查、失败不降级本地），按 log id 去重合并；
3. 整批写成功后，才按 id 删除该批行。

任一环节失败即抛错：本批一行不删，下一轮巡检原样重试（归档id 去重 + 按 id
删除都幂等）。单次响应只含计数，与批大小无关。

流式实现复用 INT-1785 的 ``LogArchivePurger``（每日保留清扫与一次性历史清理
脚本用的同一份代码），不另写一套归档写入逻辑。
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import timedelta
from typing import Any, Dict, Optional

from shared.infrastructure.config import BaseConfig
from shared.utils.query_utils import now_cst
from task_service.infrastructure.persistence.log_db_archive import (
    ArchiveStore,
    LogArchivePurger,
)

logger = logging.getLogger(__name__)

# 进程内串行：log_worker 巡检与手动归档接口可能同时推进批次。两路各自幂等，
# 串行只避免同一批行被并发读取、重复上传。
_ARCHIVE_LOCK = threading.Lock()

_DEFAULT_BATCH_ROWS = 1000
_DEFAULT_BATCH_MAX_BYTES = 8 * 1024 * 1024


def _cfg_int(name: str, default: int, minimum: int = 0) -> int:
    """读配置整数，缺失/非法按默认值；小于 minimum 的取 minimum。"""
    try:
        return max(minimum, int(getattr(BaseConfig, name, default)))
    except (TypeError, ValueError):
        return default


def _build_purger(dry_run: bool,
                  store: Optional[ArchiveStore] = None) -> LogArchivePurger:
    """构造单批推进器。

    归档口径保持 ``ArchiveLogs`` 的历史语义：**所有**冷日志（不限 category、
    不因 mark 跳过）。审计类排除与保留标记是每日保留清扫（INT-1785）的口径，
    不要在这里混用。
    """
    return LogArchivePurger(
        store=store,
        batch_size=_cfg_int('LOG_ARCHIVE_BATCH_ROWS', _DEFAULT_BATCH_ROWS, 1),
        categories=None,
        exclude_audit=False,
        keep_marked=False,
        dry_run=dry_run,
        max_batch_bytes=_cfg_int(
            'LOG_ARCHIVE_BATCH_MAX_BYTES', _DEFAULT_BATCH_MAX_BYTES, 0),
    )


class LogArchiveService:
    """日志归档编排（一批：取批 → 上传 → 删除）。"""

    @staticmethod
    def archive_batch(days: int = 30, dry_run: bool = False,
                      store: Optional[ArchiveStore] = None) -> Dict[str, Any]:
        """推进一个归档批次。

        dry_run=True 只统计冷日志行数与截止时间，不读内容、不碰存储。
        返回字段：
        - archived_count / deleted_count：本批上传成功 / 删除的行数；
        - remaining_count：logs 表剩余总行数（与改造前同口径）；
        - has_more：是否还有待归档的冷日志（调用方据此推进下一批）；
        - batch_rows / archive_write_count / response_bytes：单批行数、本批
          写过的归档对象数、本次响应字节数（验收要求单批响应远低于 gRPC 上限）；
        - cutoff_date：本批的冷热分界时间。
        """
        days = int(days or 0) or 30
        cutoff = now_cst() - timedelta(days=days)
        purger = _build_purger(dry_run, store=store)

        if dry_run:
            result = purger.run_one_batch(cutoff)
            return {
                'cold_logs_count': result.archived_count,
                'cutoff_date': cutoff.isoformat(),
            }

        with _ARCHIVE_LOCK:
            result = purger.run_one_batch(cutoff)
            group_counts = {'tasks': 0, 'cases': 0, 'other': 0}
            for group_key in result.archived_keys:
                prefix = group_key.split('/', 1)[0]
                group_counts[prefix] = group_counts.get(prefix, 0) + 1
            payload = {
                'archived_count': result.archived_count,
                'deleted_count': result.deleted_count,
                'remaining_count': result.remaining_count or 0,
                'has_more': purger.has_remaining(cutoff),
                'batch_rows': result.archived_count,
                'archive_write_count': result.archive_write_count,
                'cutoff_date': cutoff.isoformat(),
            }
            payload['response_bytes'] = len(
                json.dumps(payload, ensure_ascii=False).encode('utf-8'))
            logger.info(
                'log archive batch: rows=%s deleted=%s files=%s groups=%s '
                'has_more=%s remaining=%s response_bytes=%s elapsed=%.2fs',
                payload['batch_rows'], payload['deleted_count'],
                payload['archive_write_count'], group_counts,
                payload['has_more'], payload['remaining_count'],
                payload['response_bytes'], result.elapsed_seconds)
            return payload
