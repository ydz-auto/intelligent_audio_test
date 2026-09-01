# -*- coding: utf-8 -*-
"""报告数据构建器 —— 资源与维度汇总 Mixin。

从 report_data_builder.py 拆分而来，承载：
- _build_resources_list / _get_task_resources / _get_source_task_ids: 资源与任务关系收集
- _get_task_test_cases: 任务用例批量查询
- _calculate_summary_dimensions / _build_all_metrics: 汇总级维度值与指标构建
"""
from shared.models.common_enums import TaskStatus

from report_service.application.services.report_utils import ReportUtils
from report_service.infrastructure.clients.grpc_clients import (
    _grpc_get_devices_by_ids,
    _grpc_get_apis_by_ids,
    _grpc_get_task_devices,
    _grpc_get_task_apis,
    _grpc_get_task_merge_relations,
    _grpc_list_testcases_by_ids,
    _dim_id, _dim_name,
)


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
        task_type = task.get('type') if isinstance(task, dict) else task.type
        task_status = task.get('status') if isinstance(task, dict) else task.status
        if task_type == 'merged' and task_status == TaskStatus.COMPLETED.value:
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
        all_metrics = []
        for dim in all_dimensions:
            score_unit = dim.get('score_unit') if isinstance(dim, dict) else getattr(dim, 'score_unit', None)
            unit = score_unit if score_unit and score_unit.strip() else "%"
            decimal_places = dim.get('decimal_places') if isinstance(dim, dict) else getattr(dim, 'decimal_places', None)
            decimal_places = decimal_places if decimal_places is not None else 2
            dim_id = _dim_id(dim)
            dim_name = _dim_name(dim)
            all_metrics.append({"id": dim_id, "name": dim_name, "unit": unit, "decimal_places": decimal_places})
        return all_metrics
