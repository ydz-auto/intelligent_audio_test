# -*- coding: utf-8 -*-
"""task_service 软删除硬清理任务

定期扫描被逻辑删除超过 60 天的记录，执行物理删除。
只清理 task_service owned 的表：
  1. test_cases 及其子表（test_case_tags / task_case_relations / test_results / logs）
  2. test_case_groups
  3. test_tasks 及其关联表（task_tags / task_case_relations / task_device_relations / task_api_relations）
  4. tags（关联表 test_case_tags / task_tags 已随父记录清理）
  5. tag_categories

注：test_result_dimensions 归属 evaluation_service，由其 cleaner 负责清理孤儿记录。
     audio_tags / device_tags / task_tags 分别归属各自服务。

启动方式：在 task_service 的 lifespan 中调用 start()，关闭时调用 stop()。
"""
import logging

from shared.utils.soft_delete_cleaner_base import SoftDeleteCleanerBase

logger = logging.getLogger(__name__)


class TaskServiceCleaner(SoftDeleteCleanerBase):
    """task_service 软删除清理器，只清理本服务 owned 表。"""

    def hard_delete_expired(self, session, threshold_dt) -> dict:
        """硬删除超过保留期的逻辑删除记录及其关联数据。

        删除顺序严格遵循依赖关系（子→父），避免违反引用完整性。
        """
        counts = {}
        bd = self.batch_delete
        cei = self.collect_expired_ids

        # ================================================================
        # 1. test_cases 及其关联子表
        # ================================================================
        case_ids = cei(session, 'test_cases', threshold_dt)
        if case_ids:
            # 1.1 test_case_tags
            bd(session, "DELETE FROM test_case_tags WHERE test_case_id IN :ids", case_ids)
            # 1.2 task_case_relations（关联表，随父删除）
            bd(session, "DELETE FROM task_case_relations WHERE test_case_id IN :ids", case_ids)
            # 1.3 test_results（本服务 owned，test_result_dimensions 由 evaluation_service 清理）
            bd(session, "DELETE FROM test_results WHERE test_case_id IN :ids", case_ids)
            # 1.4 logs（有 TTL 清理，这里只清理 deleted_at 过期关联）
            bd(session, "DELETE FROM logs WHERE test_case_id IN :ids", case_ids)
            # 1.5 test_cases
            bd(session, "DELETE FROM test_cases WHERE id IN :ids", case_ids)
            counts['test_cases'] = len(case_ids)
            logger.info(f"[软删除清理:task_service] 硬删除 test_cases: {len(case_ids)} 条")

        # ================================================================
        # 2. test_case_groups
        # ================================================================
        group_ids = cei(session, 'test_case_groups', threshold_dt)
        if group_ids:
            bd(session, "DELETE FROM test_case_groups WHERE id IN :ids", group_ids)
            counts['test_case_groups'] = len(group_ids)
            logger.info(f"[软删除清理:task_service] 硬删除 test_case_groups: {len(group_ids)} 条")

        # ================================================================
        # 3. test_tasks 及其关联表
        # ================================================================
        task_ids = cei(session, 'test_tasks', threshold_dt)
        if task_ids:
            # 3.1 task_tags
            bd(session, "DELETE FROM task_tags WHERE task_id IN :ids", task_ids)
            # 3.2 task_case_relations（残留关联）
            bd(session, "DELETE FROM task_case_relations WHERE task_id IN :ids", task_ids)
            # 3.3 task_device_relations
            bd(session, "DELETE FROM task_device_relations WHERE task_id IN :ids", task_ids)
            # 3.4 task_api_relations
            bd(session, "DELETE FROM task_api_relations WHERE task_id IN :ids", task_ids)
            # 3.5 test_tasks
            bd(session, "DELETE FROM test_tasks WHERE id IN :ids", task_ids)
            counts['test_tasks'] = len(task_ids)
            logger.info(f"[软删除清理:task_service] 硬删除 test_tasks: {len(task_ids)} 条")

        # ================================================================
        # 4. tags（关联表已随父记录清理）
        # ================================================================
        tag_ids = cei(session, 'tags', threshold_dt)
        if tag_ids:
            bd(session, "DELETE FROM tags WHERE id IN :ids", tag_ids)
            counts['tags'] = len(tag_ids)
            logger.info(f"[软删除清理:task_service] 硬删除 tags: {len(tag_ids)} 条")

        # ================================================================
        # 5. tag_categories
        # ================================================================
        tc_ids = cei(session, 'tag_categories', threshold_dt)
        if tc_ids:
            bd(session, "DELETE FROM tag_categories WHERE id IN :ids", tc_ids)
            counts['tag_categories'] = len(tc_ids)
            logger.info(f"[软删除清理:task_service] 硬删除 tag_categories: {len(tc_ids)} 条")

        return counts


# 单例（幂等启动）
_cleaner: TaskServiceCleaner | None = None


def get_cleaner() -> TaskServiceCleaner:
    """获取 task_service cleaner 单例。"""
    global _cleaner
    if _cleaner is None:
        _cleaner = TaskServiceCleaner(service_name='task_service')
    return _cleaner
