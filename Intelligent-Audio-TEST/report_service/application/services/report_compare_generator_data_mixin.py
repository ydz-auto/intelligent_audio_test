# -*- coding: utf-8 -*-
"""对比报告生成器 —— 对比报告数据准备 Mixin。

从 report_compare_generator.py 拆分而来，承载对比报告（compare）的数据准备与摘要构建：
- _validate_and_get_tasks: 任务状态校验
- _prepare_compare_data: 对比数据准备（维度/指标/统计/用例/对比矩阵）
- _build_compare_summary: 对比报告 summary dict 构建
"""
from shared.models.common_enums import TaskStatus
from shared.utils.query_utils import now_cst

from report_service.application.services.report_utils import ReportUtils
from report_service.application.services.report_query_builder import ReportQueryBuilder
from report_service.application.services.report_compare_helpers import ReportCompareHelpers
from report_service.application.services.report_compare_helpers import (
    _grpc_get_tasks_by_ids, _grpc_get_test_results_by_task_ids,
)
from report_service.infrastructure.clients.grpc_clients import (
    _grpc_list_testcases_by_ids, _dim_id, _dim_name, _dim_weight,
    _dim_score_unit, _dim_decimal_places,
)


class ReportCompareDataMixin:
    """对比报告（compare）数据准备与摘要构建。"""

    @staticmethod
    def _validate_and_get_tasks(task_ids):
        """校验任务状态，返回 (tasks, error_message) 或 (None, error)。"""
        all_tasks = _grpc_get_tasks_by_ids(task_ids)
        valid_statuses = {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.MERGED.value}
        tasks = []
        for t in all_tasks:
            status = t.get('status') if isinstance(t, dict) else getattr(t, 'status', None)
            if status in valid_statuses:
                tasks.append(t)
        if not tasks:
            return None, "未找到指定任务或任务状态不是completed、failed或merged"
        return tasks, None

    @staticmethod
    def _prepare_compare_data(tasks, task_ids, results):
        """准备对比数据。返回 (data_dict, None) 或 (None, error_message)。"""
        def _t_get(t, key, default=None):
            if isinstance(t, dict):
                return t.get(key, default)
            return getattr(t, key, default)

        def _r_get(r, key, default=None):
            if isinstance(r, dict):
                return r.get(key, default)
            return getattr(r, key, default)

        included_task_types = {_t_get(t, 'type') for t in tasks if _t_get(t, 'type')}
        report_task_type = (
            "api"
            if included_task_types == {"api"}
            else ("e2e" if included_task_types == {"e2e"} else "all")
        )

        res_ids_all = [_r_get(r, 'id') for r in results]
        all_dimensions = ReportCompareHelpers._get_all_dimensions_with_results(res_ids_all)

        task_weighted_values = ReportCompareHelpers._calculate_task_weighted_values(
            task_ids, results, all_dimensions
        )

        total_cases = sum(_t_get(t, 'total_cases', 0) or 0 for t in tasks)
        completed_cases = sum((_t_get(t, 'completed_cases', 0) or 0) - (_t_get(t, 'failed_cases', 0) or 0) for t in tasks)
        success_rate = (completed_cases / total_cases * 100) if total_cases > 0 else 0

        test_case_ids = set()
        for res in results:
            tc_id = _r_get(res, 'test_case_id')
            if tc_id is not None:
                test_case_ids.add(tc_id)

        test_cases = _grpc_list_testcases_by_ids(list(test_case_ids)) if test_case_ids else []

        case_categories_list, case_tags_list = ReportQueryBuilder.extract_case_categories_and_tags(test_cases)

        resource_names, device_list, api_list = ReportCompareHelpers._collect_resources_batch(tasks, results)

        if not resource_names:
            resource_names = {"默认资源"}

        resource_list = sorted(list(resource_names))
        resources = resource_list

        if not device_list and not api_list:
            return None, "对比失败: 未找到设备或API资源数据"

        all_metrics = []
        for dim in all_dimensions:
            unit = _dim_score_unit(dim)
            unit = unit if unit and str(unit).strip() else "%"
            decimal_places = _dim_decimal_places(dim)
            decimal_places = decimal_places if decimal_places is not None else 2
            all_metrics.append({"id": _dim_id(dim), "name": _dim_name(dim), "unit": unit, "decimal_places": decimal_places})

        if not all_metrics:
            return None, "对比失败: 未找到评估维度数据"

        if not results:
            return None, "对比失败: 未找到测试结果数据"

        tasks_map = {}
        for t in tasks:
            t_id = _t_get(t, 'id')
            if t_id is not None:
                tasks_map[t_id] = t

        core_metrics = ReportUtils.calculate_core_metrics(
            results=results,
            all_dimensions=all_dimensions,
            resources=resources,
            dim_results_map=None,
            tasks_map=tasks_map,
            use_time_prefix=True
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
            use_time_prefix=True,
        )

        device_stats, api_stats = ReportUtils.calculate_device_api_stats(
            results=results,
            all_dimensions=all_dimensions,
            dim_results_map=None
        )

        cases = ReportCompareHelpers._build_case_data_compare(
            test_cases, results, all_dimensions, tasks_map, report_task_type
        )

        source_cases = ReportCompareHelpers._get_source_cases(tasks)
        if not source_cases:
            source_cases = cases

        comparison_matrix = ReportCompareHelpers._build_comparison_matrix(results, all_dimensions)

        task_names = []
        for t in tasks:
            task_names.append(_t_get(t, 'name', ''))

        comparison_data = {
            "task_ids": task_ids,
            "task_names": task_names,
            "matrix": comparison_matrix,
            "weighted_values": task_weighted_values,
            "generated_at": now_cst().isoformat()
        }

        return {
            "report_task_type": report_task_type,
            "task_weighted_values": task_weighted_values,
            "total_cases": total_cases,
            "success_rate": success_rate,
            "test_cases": test_cases,
            "case_categories_list": case_categories_list,
            "case_tags_list": case_tags_list,
            "device_list": device_list,
            "api_list": api_list,
            "resources": resources,
            "all_metrics": all_metrics,
            "metric_data": metric_data,
            "tag_metric_data": tag_metric_data,
            "raw_data": raw_data,
            "case_type_stats": case_type_stats,
            "device_stats": device_stats,
            "api_stats": api_stats,
            "source_cases": source_cases,
            "resource_headers": resource_headers,
            "comparison_data": comparison_data,
        }, None

    @staticmethod
    def _build_compare_summary(tasks, task_ids, results, data_dict):
        """构建 summary dict。"""
        def _t_get(t, key, default=None):
            if isinstance(t, dict):
                return t.get(key, default)
            return getattr(t, key, default)

        tasks_info = []
        for t in tasks:
            t_id = _t_get(t, 'id')
            tasks_info.append({
                "id": t_id,
                "name": _t_get(t, 'name'),
                "status": _t_get(t, 'status'),
                "type": _t_get(t, 'type'),
                "weighted_value": data_dict["task_weighted_values"].get(t_id, 0)
            })

        summary = {
            "task_count": len(tasks),
            "task_type": data_dict["report_task_type"],
            "total_cases": data_dict["total_cases"],
            "overall_success_rate": round(data_dict["success_rate"], 2),
            "tasks_info": tasks_info,
            "case_categories": data_dict["case_categories_list"],
            "all_case_tags": data_dict["case_tags_list"],
            "all_tags": data_dict["case_tags_list"],
            "devices": data_dict["device_list"],
            "apis": data_dict["api_list"],
            "resources": data_dict["resources"],
            "resource_headers": data_dict["resource_headers"],
            "all_metrics": data_dict["all_metrics"],
            "metric_data": data_dict["metric_data"],
            "tag_metric_data": data_dict["tag_metric_data"],
            "raw_data": data_dict["raw_data"],
            "device_stats": data_dict["device_stats"],
            "api_stats": data_dict["api_stats"],
            "case_type_stats": data_dict["case_type_stats"],
            "cases": data_dict["source_cases"]
        }

        summary = ReportUtils.normalize_summary_metrics(summary)
        return summary
