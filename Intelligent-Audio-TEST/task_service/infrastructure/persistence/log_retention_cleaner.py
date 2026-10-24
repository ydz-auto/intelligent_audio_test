# -*- coding: utf-8 -*-
"""logs 表每日保留清扫（INT-1785）。

背景：`logs` 已不再承接业务日志（INT-81 去库化），但历史存量与审计事件仍留
在库里，此前没有任何保留策略。本清扫按 `LOG_DB_RETENTION_DAYS`（默认 180 天）
每日一次归档并删除过期行，**归档先于删除**，失败保留数据。

与一次性历史清理脚本共用 `log_db_archive.LogArchivePurger` 的分批流式实现：
每批「写归档 → 校验 → 单批事务删除」，内存上界 = batch_size。

约定：
- 审计类（auth / device / benchmark）不参与清扫（合规保留，见 INT-1785 卡片）；
- 幂等：重跑时已删除行不再出现，未删成的行归档合并按 id 去重；
- 可观测：每轮打印本轮归档/删除条数；
- 单日失败不阻断服务，也不退出守护线程（下一轮重试）；
- 多实例部署用 Redis 锁保证同一时刻只有一个实例在清扫。
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

from shared.infrastructure.config import BaseConfig
from shared.utils.query_utils import now_cst
from task_service.infrastructure.persistence.log_db_archive import LogArchivePurger

logger = logging.getLogger(__name__)

# 每日一次清扫
SCAN_INTERVAL_SECONDS = 24 * 60 * 60
# 多实例互斥锁（与软删除清理同款：锁定一个扫描周期，进程崩溃后自然过期）
LOCK_KEY_TEMPLATE = 'log_retention:{service}:lock'


class LogRetentionCleaner:
    """logs 表过期行归档 + 删除守护。

    Args:
        retention_days: 保留天数；None = 每轮读 `LogSettings.db_retention_days`，
            0 或负数 = 关闭清扫（只打一条 INFO，不触碰数据）；
        scan_interval: 扫描间隔秒数（默认 24h）；
        batch_size: 单批行数；
        storage: 统一存储层（测试注入用）。
    """

    def __init__(self, retention_days: Optional[int] = None,
                 scan_interval: int = SCAN_INTERVAL_SECONDS,
                 batch_size: int = 2000, storage=None,
                 service_name: str = 'task_service'):
        self._retention_days = retention_days
        self.scan_interval = scan_interval
        self.batch_size = batch_size
        self._storage = storage
        self.service_name = service_name
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------
    def retention_days(self) -> int:
        """保留天数：显式传参优先，否则读日志体系配置快照。"""
        if self._retention_days is not None:
            return int(self._retention_days)
        from shared.logging.config import get_log_settings
        return int(get_log_settings().db_retention_days)

    # ------------------------------------------------------------------
    # 单轮清扫
    # ------------------------------------------------------------------
    def run_once(self) -> dict:
        """执行一轮清扫。异常不外抛（守护线程继续跑），返回本轮统计。"""
        days = self.retention_days()
        if days <= 0:
            logger.info('[日志保留清扫:%s] LOG_DB_RETENTION_DAYS=%s，清扫已关闭',
                        self.service_name, days)
            return {'status': 'disabled', 'retention_days': days}

        lock_token = self._acquire_lock()
        if lock_token is False:
            logger.debug('[日志保留清扫:%s] 其他实例正在执行，本轮跳过', self.service_name)
            return {'status': 'skipped', 'retention_days': days}

        # 库内 time 为 CST 墙钟（naive），截止时间同样按 naive CST 计算
        cutoff = now_cst().replace(tzinfo=None) - timedelta(days=days)
        try:
            purger = LogArchivePurger(
                storage=self._storage,
                batch_size=self.batch_size,
                exclude_audit=True,
            )
            result = purger.run(cutoff)
        except Exception as e:  # noqa: BLE001 - 单日失败不阻断服务
            logger.error('[日志保留清扫:%s] 清扫失败（数据已按批保留）: %s',
                         self.service_name, e, exc_info=True)
            return {'status': 'failed', 'retention_days': days, 'error': str(e)}
        finally:
            self._release_lock(lock_token)

        summary = {
            'status': 'failed' if result.failed else 'ok',
            'retention_days': days,
            'cutoff': cutoff.isoformat(),
            'archived': result.archived_count,
            'deleted': result.deleted_count,
            'batches': result.batch_count,
            'remaining': result.remaining_count,
            'elapsed_seconds': round(result.elapsed_seconds, 2),
        }
        if result.failed:
            summary['error'] = result.failure_reason
            logger.error('[日志保留清扫:%s] 中止于第 %s 批：%s（已归档 %s 条、已删除 %s 条）',
                         self.service_name, result.batch_count + 1, result.failure_reason,
                         result.archived_count, result.deleted_count)
        else:
            logger.info('[日志保留清扫:%s] 完成：截止 %s，归档 %s 条、删除 %s 条、'
                        '剩余 %s 条，耗时 %.2fs', self.service_name, cutoff.isoformat(),
                        result.archived_count, result.deleted_count,
                        result.remaining_count, result.elapsed_seconds)
        return summary

    # ------------------------------------------------------------------
    # Redis 互斥（不可用时降级放行，清扫本身幂等）
    # ------------------------------------------------------------------
    def _acquire_lock(self):
        """返回锁 token；拿不到锁返回 False；Redis 不可用返回 None（放行）。"""
        key = LOCK_KEY_TEMPLATE.format(service=self.service_name)
        try:
            from shared.utils.redis_pubsub import RedisStore
            store = RedisStore()
            token = f'{self.service_name}:{id(self)}'
            acquired = store.redis_client.set(key, token, nx=True, ex=self.scan_interval)
            return token if acquired else False
        except Exception as e:  # noqa: BLE001 - 无 Redis 时降级为单实例语义
            logger.warning('[日志保留清扫:%s] 互斥锁不可用，本轮放行: %s',
                           self.service_name, e)
            return None

    def _release_lock(self, token) -> None:
        if not token:
            return
        key = LOCK_KEY_TEMPLATE.format(service=self.service_name)
        try:
            from shared.utils.redis_pubsub import RedisStore
            store = RedisStore()
            # 只释放自己持有的锁（避免清扫超过一个周期后误删别人的锁）
            if store.redis_client.get(key) in (token.encode('utf-8'), token):
                store.redis_client.delete(key)
        except Exception:  # noqa: BLE001 - 锁按 TTL 自然过期
            logger.debug('[日志保留清扫:%s] 释放互斥锁失败 key=%s',
                         self.service_name, key, exc_info=True)

    # ------------------------------------------------------------------
    # 守护线程（与软删除清理同款：start 幂等 / stop 可重入）
    # ------------------------------------------------------------------
    def _loop(self) -> None:
        logger.info('[日志保留清扫:%s] 守护线程启动，每 %ss 扫描一次',
                    self.service_name, self.scan_interval)
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as e:  # noqa: BLE001 - 兜底，绝不让线程退出
                logger.error('[日志保留清扫:%s] 循环异常: %s',
                             self.service_name, e, exc_info=True)
            self._stop_event.wait(timeout=self.scan_interval)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            logger.info('[日志保留清扫:%s] 线程已在运行，跳过', self.service_name)
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name=f'log-retention-{self.service_name}', daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info('[日志保留清扫:%s] 守护线程已停止', self.service_name)


_cleaner: Optional[LogRetentionCleaner] = None
_cleaner_lock = threading.Lock()


def get_retention_cleaner() -> LogRetentionCleaner:
    """获取单例（lifespan 启动/关闭各调一次）。"""
    global _cleaner
    if _cleaner is None:
        with _cleaner_lock:
            if _cleaner is None:
                _cleaner = LogRetentionCleaner()
    return _cleaner


def log_db_retention_days() -> int:
    """配置读取便捷函数（默认 180，未配置时走 BaseConfig 默认）。"""
    return int(BaseConfig.LOG_DB_RETENTION_DAYS or 0)
