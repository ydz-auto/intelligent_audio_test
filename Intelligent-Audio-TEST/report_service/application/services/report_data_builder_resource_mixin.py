# -*- coding: utf-8 -*-
"""报告数据构建器 —— 资源与维度汇总 Mixin。

从 report_data_builder.py 拆分而来，承载：
- _build_resources_list / _get_task_resources / _get_source_task_ids: 资源与任务关系收集
- _get_task_test_cases: 任务用例批量查询
- _calculate_summary_dimensions / _build_all_metrics: 汇总级维度值与指标构建
- _get_result_dimensions: 结果引用维度取集（活跃维度 + 历史维度按 ID 补全）
"""
import logging

from shared.models.common_enums import TaskStatus

from report_service.application.services.report_utils import ReportUtils
from report_service.infrastructure.clients.grpc_clients import (
    _grpc_get_devices_by_ids,
    _grpc_get_apis_by_ids,
    _grpc_get_task_devices,
    _grpc_get_task_apis,
    _grpc_get_task_merge_relations,
    _grpc_get_dimension_by_ids,
    _grpc_list_testcases_by_ids,
    _dim_id, _dim_name, _dim_type_and_parent,
    _dim_statistic_method, _dim_score_unit, _dim_decimal_places,
    _dim_agg_denominator, _dim_sort_order,
)

logger = logging.getLogger(__name__)


class ReportDataResourceMixin:
    """资源列表与汇总级维度/指标构建。"""

    @staticmethod
    def _build_resources_list(devices, apis, task, device_result_types, api_result_types):
        resources = []

        for d in devices:
            d_id = d.get('id') if isinstance(d, dict) else d.id
            result_type = device_result_types.get(d_id, 'default')

            class TempResult:
                def __init__(self, device_id, result_type):
                    self.device_id = device_id
                    self.api_id = None
                    self.result_data = {"result_type": result_type}

            resource = ReportUtils.get_resource_name(TempResult(d_id, result_type), task, use_time_prefix=False)
            resources.append(resource)

        for a in apis:
            a_id = a.get('id') if isinstance(a, dict) else a.id
            result_type = api_result_types.get(a_id, 'default')

            class TempResult:
                def __init__(self, api_id, result_type):
                    self.api_id = api_id
                    self.device_id = None
                    self.result_data = {"result_type": result_type}

            resource = ReportUtils.get_resource_name(TempResult(a_id, result_type), task, use_time_prefix=False)
            resources.append(resource)

        return resources

    @staticmethod
    def _get_source_task_ids(task):
        # 差异#2 收尾：合并容器任务由 TaskMergeRelation(merged_task_id) 存在性判定（task.type 已废弃）
        task_status = task.get('status') if isinstance(task, dict) else task.status
        if task_status == TaskStatus.COMPLETED.value:
            task_id = task.get('id') if isinstance(task, dict) else task.id
            merge_relations = _grpc_get_task_merge_relations(task_id)
            return [r.get('source_task_id') for r in merge_relations]
        return []

    @staticmethod
    def _get_task_resources(task_ids):
        if isinstance(task_ids, int):
            task_ids = [task_ids]

        task_devices = []
        task_apis = []
        for tid in task_ids:
            tds = _grpc_get_task_devices(tid)
            task_devices.extend(tds)
            tas = _grpc_get_task_apis(tid)
            task_apis.extend(tas)

        device_ids = list(set([td.get('device_id') for td in task_devices if td.get('device_id')]))
        api_ids = list(set([ta.get('api_id') for ta in task_apis if ta.get('api_id')]))

        devices_map = _grpc_get_devices_by_ids(device_ids) if device_ids else {}
        apis_map = _grpc_get_apis_by_ids(api_ids) if api_ids else {}

        devices_list = [ReportUtils.serialize_device(d) for d in devices_map.values() if d]
        apis_list = [ReportUtils.serialize_api(a) for a in apis_map.values() if a]

        return devices_list, apis_list, device_ids, api_ids

    @staticmethod
    def _get_task_test_cases(task_ids):
        if isinstance(task_ids, int):
            task_ids = [task_ids]

        # 通过 gRPC 获取 TaskCase 列表
        from report_service.application.services.report_query_builder import _grpc_get_task_case_ids_batch
        task_cases = _grpc_get_task_case_ids_batch(task_ids)
        test_case_ids = list(set([tc.get('test_case_id') for tc in task_cases if tc.get('test_case_id')]))
        tc_map = _grpc_list_testcases_by_ids(test_case_ids)
        test_cases = list(tc_map.values())
        return test_cases, test_case_ids

    @staticmethod
    def _get_result_dimensions(all_dimensions_all, dim_stats):
        """取报告指标维度：任务结果引用的维度（活跃维度 + 历史维度按 ID 补全）。

        INT-1571：dim_stats 的键来自 test_result_dimensions.dimension_id，即“评估当时
        使用的维度”。维度后来被停用/软删后不会出现在 ListDimensions（只返回活跃维度）
        的结果里，若仍按活跃列表取交集，老任务会得到空指标集，报告在 prepare_data
        阶段被判定「任务没有关联任何评估维度」而恒失败（真实库 397/413 等）。

        因此：结果引用但已不在活跃列表中的维度，按 ID 经 gRPC 解析（evaluation_service
        GetDimensionByIds 按引用解析，不过滤 status/deleted），用其历史口径字段还原
        指标列。解析不到的维度（已被硬删）跳过并记 WARNING，不影响其余维度出报告。
        """
        if not dim_stats:
            return list(all_dimensions_all)
        # dim_stats 正常为 {dimension_id: stat}；非标量键（异常桩数据）不参与取集
        used_ids_order = [key for key in dim_stats if isinstance(key, (int, str))]
        used_ids = set(used_ids_order)
        if not used_ids:
            return list(all_dimensions_all)

        active_ids = {_dim_id(d) for d in all_dimensions_all}
        selected = [d for d in all_dimensions_all if _dim_id(d) in used_ids]

        missing_ids = [dim_id for dim_id in used_ids_order if dim_id not in active_ids]
        if not missing_ids:
            return selected

        resolved = _grpc_get_dimension_by_ids(missing_ids)
        unresolved = []
        for dim_id in missing_ids:
            dim = resolved.get(str(dim_id)) if resolved else None
            if not dim:
                unresolved.append(dim_id)
                continue
            selected.append(dim)
        if unresolved:
            logger.warning(
                'report 历史维度解析失败，指标列将缺失: dim_ids=%s（维度已被硬删除）',
                sorted(unresolved))
        return selected

    @staticmethod
    def _calculate_summary_dimensions(dim_stats):
        summary_dim_values = []
        for d_id, stat in dim_stats.items():
            avg_value = (stat["total_dimension_value"] / stat["count"]) if stat["count"] > 0 else 0
            summary_dim_values.append({
                "id": d_id,
                "name": stat["name"],
                "average_value": avg_value
            })
        return summary_dim_values

    @staticmethod
    def _build_all_metrics(all_dimensions):
        # 维度ID→名称映射，用于补充 parent_dimension_name
        dim_id_to_name = {_dim_id(d): _dim_name(d) for d in all_dimensions}
        all_metrics = []
        for dim in all_dimensions:
            statistic_method = _dim_statistic_method(dim) or 'average'
            # 聚合方式决定 unit：pass_rate/ratio/weighted_sum_ratio/weighted_wer 产出百分比，强制为 %；其余用维度配置的 score_unit
            if statistic_method in ('pass_rate', 'ratio', 'weighted_sum_ratio', 'weighted_wer'):
                unit = "%"
            else:
                score_unit = _dim_score_unit(dim)
                unit = score_unit if score_unit and score_unit.strip() else ""
            decimal_places = _dim_decimal_places(dim)
            decimal_places = decimal_places if decimal_places is not None else 2
            dim_id = _dim_id(dim)
            dim_name = _dim_name(dim)
            dim_type, parent_dim_id = _dim_type_and_parent(dim)
            all_metrics.append({
                "id": dim_id,
                "name": dim_name,
                "unit": unit,
                "decimal_places": decimal_places,
                "statistic_method": statistic_method,
                "agg_denominator": _dim_agg_denominator(dim),
                "sort_order": _dim_sort_order(dim),
                "dimension_type": dim_type,
                "parent_dimension_id": parent_dim_id,
                "parent_dimension_name": dim_id_to_name.get(parent_dim_id) if parent_dim_id else None,
            })
        # 报告页按 sort_order 稳定排序（sort_order 相同按下标）
        all_metrics.sort(key=lambda m: (m.get('sort_order') or 0, m.get('id') or 0))
        return all_metrics
