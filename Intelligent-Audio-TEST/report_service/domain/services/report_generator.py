# -*- coding: utf-8 -*-
"""报告生成领域服务（纯领域逻辑，不依赖基础设施）

封装报告生成过程中的纯计算逻辑：
- 指标汇总统计（avg/min/max/std_dev）
- 任务状态到报告状态的映射
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

from report_service.domain.entities import ReportStatus


class ReportGenerator:
    """报告生成领域服务。

    提供报告生成过程中的纯领域计算逻辑，不依赖 DB / HTTP 等基础设施。
    """

    @staticmethod
    def calculate_summary(metric_values: List[float]) -> Dict[str, Any]:
        """计算指标汇总统计。

        Args:
            metric_values: 指标值列表

        Returns:
            包含 avg/min/max/std_dev/sample_count 的统计字典；
            空列表返回零值统计。
        """
        if not metric_values:
            return {
                'avg': 0.0,
                'min': 0.0,
                'max': 0.0,
                'std_dev': 0.0,
                'sample_count': 0,
            }

        count = len(metric_values)
        avg = sum(metric_values) / count
        min_val = min(metric_values)
        max_val = max(metric_values)
        # 总体标准差
        if count > 1:
            variance = sum((v - avg) ** 2 for v in metric_values) / count
            std_dev = math.sqrt(variance)
        else:
            std_dev = 0.0

        return {
            'avg': round(avg, 6),
            'min': min_val,
            'max': max_val,
            'std_dev': round(std_dev, 6),
            'sample_count': count,
        }

    @staticmethod
    def determine_status(task_status: str) -> str:
        """映射任务完成状态到报告状态。

        Args:
            task_status: 任务状态字符串

        Returns:
            报告状态字符串（pending/generating/completed/failed）
        """
        # 任务终态映射规则
        _COMPLETED_LIKE = {
            'completed', 'stopped', 'skipped',
        }
        _FAILED_LIKE = {
            'failed',
        }
        _RUNNING_LIKE = {
            'running', 'evaluating', 'reevaluating',
            'queued', 'reevaluate_queued', 'pending',
        }

        lowered = (task_status or '').lower()
        if lowered in _COMPLETED_LIKE:
            return ReportStatus.COMPLETED.value
        if lowered in _FAILED_LIKE:
            return ReportStatus.FAILED.value
        if lowered in _RUNNING_LIKE:
            return ReportStatus.GENERATING.value
        # 未知任务状态默认回到 pending，等待后续流转
        return ReportStatus.PENDING.value

    @staticmethod
    def orchestrate_task_report(task_id: int, name: str = None, description: str = None) -> dict:
        """协调任务报告生成流程。

        委托 ReportTaskGenerator 执行实际生成逻辑。
        """
        from report_service.application.services.report_task_generator import ReportTaskGenerator
        return ReportTaskGenerator.generate_task_report(task_id, name, description)
