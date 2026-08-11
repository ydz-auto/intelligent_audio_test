# -*- coding: utf-8 -*-
"""api_test_service 软删除硬清理任务

定期扫描被逻辑删除超过 60 天的记录，执行物理删除。
只清理 api_test_service owned 的表：
  1. apis

启动方式：在 api_test_service 的 lifespan 中调用 start()，关闭时调用 stop()。
"""
import logging

from shared.utils.soft_delete_cleaner_base import SoftDeleteCleanerBase

logger = logging.getLogger(__name__)


class ApiTestServiceCleaner(SoftDeleteCleanerBase):
    """api_test_service 软删除清理器，只清理本服务 owned 表。"""

    def hard_delete_expired(self, session, threshold_dt) -> dict:
        """硬删除超过保留期的逻辑删除记录。"""
        counts = {}
        bd = self.batch_delete
        cei = self.collect_expired_ids

        # ================================================================
        # 1. apis
        # ================================================================
        api_ids = cei(session, 'apis', threshold_dt)
        if api_ids:
            bd(session, "DELETE FROM apis WHERE id IN :ids", api_ids)
            counts['apis'] = len(api_ids)
            logger.info(f"[软删除清理:api_test_service] 硬删除 apis: {len(api_ids)} 条")

        return counts


# 单例（幂等启动）
_cleaner: ApiTestServiceCleaner | None = None


def get_cleaner() -> ApiTestServiceCleaner:
    """获取 api_test_service cleaner 单例。"""
    global _cleaner
    if _cleaner is None:
        _cleaner = ApiTestServiceCleaner(service_name='api_test_service')
    return _cleaner
