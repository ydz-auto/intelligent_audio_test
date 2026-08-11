# -*- coding: utf-8 -*-
"""report_service 软删除硬清理任务

定期扫描被逻辑删除超过 60 天的记录，执行物理删除。
只清理 report_service owned 的表：
  1. test_reports 及其子表
     （report_summaries / report_summary_meta / report_raw_data / report_cases /
      report_metric_stats / report_comparison_matrix）

启动方式：在 report_service 的 lifespan 中调用 start()，关闭时调用 stop()。
"""
import logging

from shared.utils.soft_delete_cleaner_base import SoftDeleteCleanerBase

logger = logging.getLogger(__name__)


class ReportServiceCleaner(SoftDeleteCleanerBase):
    """report_service 软删除清理器，只清理本服务 owned 表。"""

    def hard_delete_expired(self, session, threshold_dt) -> dict:
        """硬删除超过保留期的逻辑删除记录及其关联数据。"""
        counts = {}
        bd = self.batch_delete
        cei = self.collect_expired_ids

        # ================================================================
        # 1. test_reports 及其子表
        # ================================================================
        report_ids = cei(session, 'test_reports', threshold_dt)
        if report_ids:
            # 1.1 report_summaries
            bd(session, "DELETE FROM report_summaries WHERE report_id IN :ids", report_ids)
            # 1.2 report_summary_meta
            bd(session, "DELETE FROM report_summary_meta WHERE report_id IN :ids", report_ids)
            # 1.3 report_raw_data
            bd(session, "DELETE FROM report_raw_data WHERE report_id IN :ids", report_ids)
            # 1.4 report_cases
            bd(session, "DELETE FROM report_cases WHERE report_id IN :ids", report_ids)
            # 1.5 report_metric_stats
            bd(session, "DELETE FROM report_metric_stats WHERE report_id IN :ids", report_ids)
            # 1.6 report_comparison_matrix
            bd(session, "DELETE FROM report_comparison_matrix WHERE report_id IN :ids", report_ids)
            # 1.7 test_reports
            bd(session, "DELETE FROM test_reports WHERE id IN :ids", report_ids)
            counts['test_reports'] = len(report_ids)
            logger.info(f"[软删除清理:report_service] 硬删除 test_reports: {len(report_ids)} 条")

        return counts


# 单例（幂等启动）
_cleaner: ReportServiceCleaner | None = None


def get_cleaner() -> ReportServiceCleaner:
    """获取 report_service cleaner 单例。"""
    global _cleaner
    if _cleaner is None:
        _cleaner = ReportServiceCleaner(service_name='report_service')
    return _cleaner
