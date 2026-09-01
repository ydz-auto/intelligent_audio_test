# -*- coding: utf-8 -*-
"""报告数据构建器 —— 持久化 Mixin。

从 report_data_builder.py 拆分而来，承载：
- _create_report_record: 创建报告主表聚合根
- _create_report_summary: 创建摘要与摘要元数据记录
- _create_report_detail_data: 创建明细数据记录（原始数据 / 用例 / 指标统计）

统一通过 report_repository 写入，避免直接操作 PO。
"""
import json

from report_service.domain.entities import ReportAggregate
from report_service.infrastructure.persistence.report_repository import report_repository


class ReportDataPersistMixin:
    """任务报告持久化：聚合根 + 摘要 + 明细数据写入。"""

    @staticmethod
    def _create_report_record(name, task_id, description):
        """创建报告主表记录。

        通过 report_repository.add 写入聚合根，避免直接操作 PO。
        报告类型与状态使用字符串字面量 'task' / 'draft'，
        保持与现有数据模型一致（shared.models.common_enums 中定义的值）。
        """
        aggregate = ReportAggregate(
            id=0,
            task_id=task_id,
            report_type='task',
            status='draft',
            config={'name': name, 'description': description},
        )
        report_id = report_repository.add(aggregate)
        return report_id

    @staticmethod
    def _create_report_summary(report_id, task, summary):
        """创建报告摘要与摘要元数据记录。

        通过 report_repository.add_summary / add_summary_meta 写入，
        避免直接操作 PO。
        """
        total_cases = summary.get('total_cases', 0)
        completed_cases = summary.get('completed_cases', 0)

        summary_data = {
            'total_cases': total_cases,
            'completed_cases': completed_cases,
            'failed_cases': summary.get('failed_cases', 0),
            'pass_rate': round((completed_cases / total_cases * 100), 2) if total_cases > 0 else 0,
            'duration': task.get('actual_duration') if isinstance(task, dict) else task.actual_duration,
            'started_at': task.get('started_at') if isinstance(task, dict) else task.started_at,
            'completed_at': task.get('completed_at') if isinstance(task, dict) else task.completed_at,
        }
        summary_id = report_repository.add_summary(report_id, summary_data)

        meta_data = {
            'dimension_values': json.dumps(summary.get('dimension_values', []), ensure_ascii=False),
            'case_categories': json.dumps(summary.get('case_categories', []), ensure_ascii=False),
            'all_case_tags': json.dumps(summary.get('all_case_tags', []), ensure_ascii=False),
            'devices': json.dumps(summary.get('devices', []), ensure_ascii=False),
            'apis': json.dumps(summary.get('apis', []), ensure_ascii=False),
            'resources': json.dumps(summary.get('resources', []), ensure_ascii=False),
            'resource_headers': json.dumps(summary.get('resource_headers', []), ensure_ascii=False),
            'all_metrics': json.dumps(summary.get('all_metrics', []), ensure_ascii=False),
            'field_mappings': summary.get('field_mappings', {}),
        }
        meta_id = report_repository.add_summary_meta(report_id, meta_data)

        return summary_id, meta_id

    @staticmethod
    def _create_report_detail_data(report_id, summary):
        """创建报告明细数据记录。

        通过 report_repository.add_raw_data / add_case / add_metric_stats 写入，
        避免直接操作 PO。
        """
        raw_data_id = report_repository.add_raw_data(report_id, {
            'raw_data': json.dumps(summary.get('raw_data', []), ensure_ascii=False),
        })

        cases = summary.get('cases', [])
        if isinstance(cases, str):
            cases = json.loads(cases)
        case_ids = []
        for case_item in cases:
            if not isinstance(case_item, dict):
                continue
            case_id = report_repository.add_case(report_id, {
                'test_case_id': case_item.get('id'),
                'name': case_item.get('name'),
                'description': case_item.get('description'),
                'category': case_item.get('category'),
                'tags': case_item.get('tags'),
                'metrics': case_item.get('metrics'),
                'results': case_item.get('results'),
                'audios': case_item.get('audios'),
                'reference_params': case_item.get('reference_params'),
                'algorithm_results': case_item.get('algorithm_results'),
                'algorithm_type': case_item.get('algorithm_type'),
                'logs': case_item.get('logs'),
            })
            case_ids.append(case_id)

        metric_stats_id = report_repository.add_metric_stats(report_id, {
            'metric_data': json.dumps(summary.get('metric_data', []), ensure_ascii=False),
            'tag_metric_data': json.dumps(summary.get('tag_metric_data', []), ensure_ascii=False),
            'tag_category_metric_data': json.dumps(summary.get('tag_category_metric_data', {}), ensure_ascii=False),
            'case_type_stats': json.dumps(summary.get('case_type_stats', []), ensure_ascii=False),
            'device_stats': json.dumps(summary.get('device_stats', []), ensure_ascii=False),
            'api_stats': json.dumps(summary.get('api_stats', []), ensure_ascii=False),
        })

        return raw_data_id, metric_stats_id
