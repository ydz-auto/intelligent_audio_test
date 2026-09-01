# -*- coding: utf-8 -*-
"""对比报告生成器 —— 二次对比数据准备 Mixin。

从 report_compare_generator.py 拆分而来，承载二次对比报告（secondary_compare）的数据准备：
- _prepare_secondary_data: 二次对比数据准备（资源/维度/指标/统计/用例/对比矩阵）
- _build_secondary_summary: 二次对比 summary dict 构建
"""
from report_service.application.services.report_utils import ReportUtils
from report_service.application.services.report_query_builder import ReportQueryBuilder
from report_service.application.services.report_compare_helpers import ReportCompareHelpers
from report_service.application.services.report_data_builder import ReportDataBuilder


class ReportSecondaryDataMixin:
    """二次对比报告（secondary_compare）数据准备与摘要构建。"""

    @staticmethod
    def _prepare_secondary_data(report_ids, reports, tasks, task_ids):
        """准备二次对比数据。返回 (data_dict, None) 或 (None, error)。"""
        report_task_type = ReportCompareHelpers._get_task_type(tasks)

        results, resources, devices_list, apis_list, device_ids, api_ids, error = \
            ReportCompareHelpers._collect_all_resources(task_ids, tasks)
        if error:
            return None, error

        res_ids = [(r.get('id') if isinstance(r, dict) else getattr(r, 'id', None)) for r in results]
        res_ids = [rid for rid in res_ids if rid is not None]
        all_dimensions, all_metrics, error = ReportCompareHelpers._build_all_dimensions(res_ids)
        if error:
            return None, error

        dim_results_map, _ = ReportDataBuilder._get_dimension_results_batch(res_ids)

        tasks_map = {}
        for t in tasks:
            t_id = t.get('id') if isinstance(t, dict) else getattr(t, 'id', None)
            if t_id is not None:
                tasks_map[t_id] = t
        core_metrics = ReportUtils.calculate_core_metrics(
            results=results,
            all_dimensions=all_dimensions,
            resources=resources,
            dim_results_map=dim_results_map,
            tasks_map=tasks_map,
            use_time_prefix=False
        )

        metric_data = core_metrics['metric_data']
        tag_metric_data = core_metrics['tag_metric_data']
        raw_data = core_metrics['raw_data']
        case_type_stats = core_metrics['case_type_stats']
        resources = core_metrics['resources']

        resource_headers = ReportUtils.build_resource_headers(
            resources=resources,
            results=results,
            tasks_map=tasks_map,
            use_time_prefix=False,
        )

        device_stats, api_stats = ReportUtils.calculate_device_api_stats(
            results=results,
            all_dimensions=all_dimensions,
            dim_results_map=dim_results_map
        )

        test_cases, _ = ReportDataBuilder._get_task_test_cases(task_ids)
        case_categories_list, case_tags_list = [], []
        if test_cases:
            case_categories_list, case_tags_list = ReportQueryBuilder.extract_case_categories_and_tags(test_cases)

        if not case_categories_list:
            case_categories_list = [{"id": "default_group", "name": "无分组"}]
        if not case_tags_list:
            case_tags_list = [{"id": "default_tag", "name": "无标签"}]

        source_cases = ReportCompareHelpers._get_source_cases_from_reports(reports)
        if not source_cases:
            cases = ReportDataBuilder._build_case_data(
                test_cases, results, all_dimensions, dim_results_map, tasks[0] if tasks else None
            )
            source_cases = cases

        comparison_matrix_data = ReportCompareHelpers._build_comparison_matrix_secondary(
            task_ids, reports, all_dimensions
        )

        return {
            "report_task_type": report_task_type,
            "results": results,
            "resources": resources,
            "devices_list": devices_list,
            "apis_list": apis_list,
            "device_ids": device_ids,
            "api_ids": api_ids,
            "all_dimensions": all_dimensions,
            "all_metrics": all_metrics,
            "dim_results_map": dim_results_map,
            "metric_data": metric_data,
            "tag_metric_data": tag_metric_data,
            "raw_data": raw_data,
            "case_type_stats": case_type_stats,
            "resource_headers": resource_headers,
            "device_stats": device_stats,
            "api_stats": api_stats,
            "case_categories_list": case_categories_list,
            "case_tags_list": case_tags_list,
            "source_cases": source_cases,
            "comparison_matrix_data": comparison_matrix_data,
        }, None

    @staticmethod
    def _build_secondary_summary(tasks, task_ids, reports, data_dict):
        """构建二次对比 summary。"""
        return {
            "case_categories_list": data_dict["case_categories_list"],
            "case_tags_list": data_dict["case_tags_list"],
            "devices_list": data_dict["devices_list"],
            "apis_list": data_dict["apis_list"],
            "resources": data_dict["resources"],
            "resource_headers": data_dict["resource_headers"],
            "all_metrics": data_dict["all_metrics"],
            "raw_data": data_dict["raw_data"],
            "metric_data": data_dict["metric_data"],
            "tag_metric_data": data_dict["tag_metric_data"],
            "case_type_stats": data_dict["case_type_stats"],
            "device_stats": data_dict["device_stats"],
            "api_stats": data_dict["api_stats"],
            "source_cases": data_dict["source_cases"],
            "comparison_matrix_data": data_dict["comparison_matrix_data"],
        }
