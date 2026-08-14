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

保护策略：硬删除前检查待删记录是否仍被**活跃**（未删除）记录引用。
          若被引用则跳过该条硬删除，并刷新 deleted_at 为当前时间，
          重置 60 天保留期，给引用方窗口自然清理。

启动方式：在 task_service 的 lifespan 中调用 start()，关闭时调用 stop()。
"""
import logging

from sqlalchemy import text, bindparam

from shared.utils.soft_delete_cleaner_base import SoftDeleteCleanerBase

logger = logging.getLogger(__name__)


class TaskServiceCleaner(SoftDeleteCleanerBase):
    """task_service 软删除清理器，只清理本服务 owned 表。"""

    def hard_delete_expired(self, session, threshold_dt) -> dict:
        """硬删除超过保留期的逻辑删除记录及其关联数据。

        删除顺序严格遵循依赖关系（子→父），避免违反引用完整性。
        删除前检查是否仍被活跃记录引用，若引用则跳过。
        """
        counts = {}
        bd = self.batch_delete
        cei = self.collect_expired_ids
        rda = self.refresh_deleted_at

        # ================================================================
        # 1. test_cases 及其关联子表
        # ================================================================
        case_ids = cei(session, 'test_cases', threshold_dt)
        if case_ids:
            # 1.0 跳过仍被活跃 test_tasks 通过 task_case_relations 引用的用例
            rows = session.execute(text(
                "SELECT DISTINCT tcr.test_case_id FROM task_case_relations tcr "
                "JOIN test_tasks t ON tcr.task_id = t.id "
                "WHERE tcr.test_case_id IN :ids AND t.deleted = FALSE"
            ).bindparams(bindparam('ids', expanding=True)), {"ids": case_ids}).all()
            active_ref = {r[0] for r in rows}
            if active_ref:
                rda(session, 'test_cases', list(active_ref))
                logger.info(
                    f"[软删除清理:task_service] 跳过 {len(active_ref)} 条 "
                    f"仍被活跃 task 引用的 test_cases，已刷新 deleted_at")
                case_ids = [i for i in case_ids if i not in active_ref]
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
            # 跳过仍被活跃 test_cases 引用的分组
            referenced = self.filter_referenced_ids(
                session, 'test_cases', 'group_id', group_ids)
            if referenced:
                rda(session, 'test_case_groups', list(referenced))
                logger.info(
                    f"[软删除清理:task_service] 跳过 {len(referenced)} 条 "
                    f"仍被活跃 test_cases 引用的 test_case_groups，已刷新 deleted_at")
                group_ids = [i for i in group_ids if i not in referenced]
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
            # 跳过仍被活跃 test_cases / test_tasks 引用的 tag
            case_tag_rows = session.execute(text(
                "SELECT DISTINCT tct.tag_id FROM test_case_tags tct "
                "JOIN test_cases c ON tct.test_case_id = c.id "
                "WHERE tct.tag_id IN :ids AND c.deleted = FALSE"
            ).bindparams(bindparam('ids', expanding=True)), {"ids": tag_ids}).all()
            task_tag_rows = session.execute(text(
                "SELECT DISTINCT tt.tag_id FROM task_tags tt "
                "JOIN test_tasks tk ON tt.task_id = tk.id "
                "WHERE tt.tag_id IN :ids AND tk.deleted = FALSE"
            ).bindparams(bindparam('ids', expanding=True)), {"ids": tag_ids}).all()
            active_refs = {r[0] for r in case_tag_rows} | {r[0] for r in task_tag_rows}
            if active_refs:
                rda(session, 'tags', list(active_refs))
                logger.info(
                    f"[软删除清理:task_service] 跳过 {len(active_refs)} 条 "
                    f"仍被活跃记录引用的 tags，已刷新 deleted_at")
                tag_ids = [i for i in tag_ids if i not in active_refs]
            if tag_ids:
                bd(session, "DELETE FROM tags WHERE id IN :ids", tag_ids)
                counts['tags'] = len(tag_ids)
                logger.info(f"[软删除清理:task_service] 硬删除 tags: {len(tag_ids)} 条")

        # ================================================================
        # 5. tag_categories
        # ================================================================
        tc_ids = cei(session, 'tag_categories', threshold_dt)
        if tc_ids:
            # 跳过仍被活跃 tags 引用的分类
            referenced = self.filter_referenced_ids(
                session, 'tags', 'category_id', tc_ids)
            if referenced:
                rda(session, 'tag_categories', list(referenced))
                logger.info(
                    f"[软删除清理:task_service] 跳过 {len(referenced)} 条 "
                    f"仍被活跃 tags 引用的 tag_categories，已刷新 deleted_at")
                tc_ids = [i for i in tc_ids if i not in referenced]
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
