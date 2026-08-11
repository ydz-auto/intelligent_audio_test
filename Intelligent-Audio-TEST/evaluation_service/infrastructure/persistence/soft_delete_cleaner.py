# -*- coding: utf-8 -*-
"""evaluation_service 软删除硬清理任务

定期扫描被逻辑删除超过 60 天的记录，执行物理删除。
只清理 evaluation_service owned 的表：
  1. dimensions（子维度先删）
  2. categories
  3. test_result_dimensions（孤儿清理：父 test_results 已被 task_service 删除时）

注：test_results 归属 task_service，test_result_dimensions 是其子表。
     test_result_dimensions 无 deleted_at，通过查找孤儿记录
    （test_result_id NOT IN test_results）清理。

启动方式：在 evaluation_service 的 lifespan 中调用 start()，关闭时调用 stop()。
"""
import logging

from sqlalchemy import text, bindparam

from shared.utils.soft_delete_cleaner_base import SoftDeleteCleanerBase

logger = logging.getLogger(__name__)


class EvaluationServiceCleaner(SoftDeleteCleanerBase):
    """evaluation_service 软删除清理器，只清理本服务 owned 表。"""

    def hard_delete_expired(self, session, threshold_dt) -> dict:
        """硬删除超过保留期的逻辑删除记录及其关联数据。"""
        counts = {}
        bd = self.batch_delete
        cei = self.collect_expired_ids

        # ================================================================
        # 1. dimensions（子维度先删，再删主维度）
        # ================================================================
        dim_ids = cei(session, 'dimensions', threshold_dt)
        if dim_ids:
            # 1.1 先删子维度（parent_dimension_id 指向待删主维度）
            bd(session, "DELETE FROM dimensions WHERE parent_dimension_id IN :ids", dim_ids)
            # 1.2 删维度本体
            bd(session, "DELETE FROM dimensions WHERE id IN :ids", dim_ids)
            counts['dimensions'] = len(dim_ids)
            logger.info(f"[软删除清理:evaluation_service] 硬删除 dimensions: {len(dim_ids)} 条")

        # ================================================================
        # 2. categories
        # ================================================================
        cat_ids = cei(session, 'categories', threshold_dt)
        if cat_ids:
            bd(session, "DELETE FROM categories WHERE id IN :ids", cat_ids)
            counts['categories'] = len(cat_ids)
            logger.info(f"[软删除清理:evaluation_service] 硬删除 categories: {len(cat_ids)} 条")

        # ================================================================
        # 3. test_result_dimensions 孤儿清理
        #    父 test_results 被 task_service 删除后，遗留的维度得分记录。
        #    通过 NOT IN 查找孤儿，避免跨服务 gRPC 调用。
        # ================================================================
        orphan_rows = session.execute(text(
            "SELECT id FROM test_result_dimensions "
            "WHERE test_result_id NOT IN (SELECT id FROM test_results)"
        )).all()
        orphan_ids = [r[0] for r in orphan_rows]
        if orphan_ids:
            session.execute(text(
                "DELETE FROM test_result_dimensions WHERE id IN :ids"
            ).bindparams(bindparam('ids', expanding=True)), {"ids": orphan_ids})
            counts['test_result_dimensions'] = len(orphan_ids)
            logger.info(
                f"[软删除清理:evaluation_service] 硬删除 test_result_dimensions 孤儿: {len(orphan_ids)} 条")

        return counts


# 单例（幂等启动）
_cleaner: EvaluationServiceCleaner | None = None


def get_cleaner() -> EvaluationServiceCleaner:
    """获取 evaluation_service cleaner 单例。"""
    global _cleaner
    if _cleaner is None:
        _cleaner = EvaluationServiceCleaner(service_name='evaluation_service')
    return _cleaner
