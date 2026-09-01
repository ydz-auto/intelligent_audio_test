# -*- coding: utf-8 -*-
"""对比报告生成器 —— 持久化 Mixin。

从 report_compare_generator.py 拆分而来，承载对比报告与二次对比报告的落库写入：
- _persist_compare_report: 创建对比报告及关联子表记录
- _create_secondary_report_records: 创建二次对比报告的关联子表记录

统一通过 report_repository 写入，避免直接操作 PO。
"""
import json

from report_service.domain.entities import ReportAggregate
from report_service.infrastructure.persistence.report_repository import report_repository


class ReportComparePersistMixin:
    """对比报告持久化：聚合根 + 摘要 + 元数据 + 用例 + 指标统计 + 对比矩阵写入。"""

    @staticmethod
    def _persist_compare_report(name, description, summary, source_cases, comparison_data):
        """创建对比报告及其关联子表记录。

        原实现使用 get_db_session().add(...) / commit() 直连 PO；
        迁移后改用 report_repository 对应方法写入，每个方法自管理事务。
        返回 new_report_id。
        """
        # 主报告聚合根：使用字符串字面量保持与现有数据模型一致
        aggregate = ReportAggregate(
            task_id=0,
            report_type='comparison',
            status='draft',
            config={'name': name, 'description': description},
            deleted=False,
        )
        new_report_id = report_repository.add(aggregate)

        # 摘要
        summary_data = {
            'total_cases': summary.get('total_cases', 0),
            'completed_cases': summary.get('total_cases', 0),
            'failed_cases': 0,
            'pass_rate': summary.get('overall_success_rate', 0),
            'duration': 0,
            'started_at': None,
            'completed_at': None,
        }
        report_repository.add_summary(new_report_id, summary_data)

        # 摘要元数据
        meta_data = {
            'dimension_values': json.dumps(summary.get('dimension_values', []), ensure_ascii=False),
            'case_categories': json.dumps(summary.get('case_categories', []), ensure_ascii=False),
            'all_case_tags': json.dumps(summary.get('all_case_tags', []), ensure_ascii=False),
            'devices': json.dumps(summary.get('devices', []), ensure_ascii=False),
            'apis': json.dumps(summary.get('apis', []), ensure_ascii=False),
            'resources': json.dumps(summary.get('resources', []), ensure_ascii=False),
            'resource_headers': json.dumps(summary.get('resource_headers', []), ensure_ascii=False),
            'all_metrics': json.dumps(summary.get('all_metrics', []), ensure_ascii=False),
        }
        report_repository.add_summary_meta(new_report_id, meta_data)

        # 原始数据
        report_repository.add_raw_data(new_report_id, {
            'raw_data': json.dumps(summary.get('raw_data', []), ensure_ascii=False),
        })

        # 用例记录
        for case_item in source_cases:
            if not isinstance(case_item, dict):
                continue
            report_repository.add_case(new_report_id, {
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

        # 指标统计
        stats_data = {
            'metric_data': json.dumps(summary.get('metric_data', []), ensure_ascii=False),
            'tag_metric_data': json.dumps(summary.get('tag_metric_data', []), ensure_ascii=False),
            'case_type_stats': json.dumps(summary.get('case_type_stats', []), ensure_ascii=False),
            'device_stats': json.dumps(summary.get('device_stats', []), ensure_ascii=False),
            'api_stats': json.dumps(summary.get('api_stats', []), ensure_ascii=False),
        }
        report_repository.add_metric_stats(new_report_id, stats_data)

        # 对比矩阵
        report_repository.add_comparison_matrix(new_report_id, {
            'comparison_matrix': json.dumps(comparison_data, ensure_ascii=False),
        })

        return new_report_id

    @staticmethod
    def _create_secondary_report_records(
        new_report_id, task_ids, tasks, reports,
        case_categories_list, case_tags_list,
        devices_list, apis_list, resources, resource_headers, all_metrics,
        raw_data, metric_data, tag_metric_data, case_type_stats,
        device_stats, api_stats, source_cases, comparison_matrix_data
    ):
        """创建二次对比报告的关联子表记录。

        原实现使用 get_db_session().add(...) 直连 PO；
        迁移后改用 report_repository 对应方法写入。
        """
        def _t_get(t, key, default=0):
            if isinstance(t, dict):
                return t.get(key, default)
            return getattr(t, key, default)

        total_cases = sum(_t_get(t, 'total_cases', 0) or 0 for t in tasks) if tasks else 0
        completed_cases = sum((_t_get(t, 'completed_cases', 0) or 0) - (_t_get(t, 'failed_cases', 0) or 0) for t in tasks) if tasks else 0
        failed_cases = sum(_t_get(t, 'failed_cases', 0) or 0 for t in tasks) if tasks else 0
        success_rate = (completed_cases / total_cases * 100) if total_cases > 0 else 0

        summary_data = {
            'task_ids': task_ids,
            'total_cases': total_cases,
            'completed_cases': completed_cases,
            'failed_cases': failed_cases,
            'pass_rate': round(success_rate, 2),
            'duration': 0,
            'started_at': None,
            'completed_at': None,
        }
        report_repository.add_summary(new_report_id, summary_data)

        meta_data = {
            'dimension_values': json.dumps([], ensure_ascii=False),
            'case_categories': json.dumps(case_categories_list, ensure_ascii=False),
            'all_case_tags': json.dumps(case_tags_list, ensure_ascii=False),
            'devices': json.dumps(devices_list, ensure_ascii=False),
            'apis': json.dumps(apis_list, ensure_ascii=False),
            'resources': json.dumps(resources, ensure_ascii=False),
            'resource_headers': json.dumps(resource_headers, ensure_ascii=False),
            'all_metrics': json.dumps(all_metrics, ensure_ascii=False),
        }
        report_repository.add_summary_meta(new_report_id, meta_data)

        report_repository.add_raw_data(new_report_id, {
            'raw_data': json.dumps(raw_data, ensure_ascii=False),
        })

        for case_item in source_cases:
            if not isinstance(case_item, dict):
                continue
            report_repository.add_case(new_report_id, {
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

        stats_data = {
            'metric_data': json.dumps(metric_data, ensure_ascii=False),
            'tag_metric_data': json.dumps(tag_metric_data, ensure_ascii=False),
            'case_type_stats': json.dumps(case_type_stats, ensure_ascii=False),
            'device_stats': json.dumps(device_stats, ensure_ascii=False),
            'api_stats': json.dumps(api_stats, ensure_ascii=False),
        }
        report_repository.add_metric_stats(new_report_id, stats_data)

        report_repository.add_comparison_matrix(new_report_id, {
            'comparison_matrix': json.dumps(comparison_matrix_data, ensure_ascii=False),
        })
