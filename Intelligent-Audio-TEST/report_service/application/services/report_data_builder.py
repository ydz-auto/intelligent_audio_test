# -*- coding: utf-8 -*-
"""报告数据构建辅助（report_service 版本）。

从 api_gateway/application/services/report/report_data_builder.py 迁移而来，
保持 ReportDataBuilder 类原有逻辑不变，仅做以下调整：
- 移除 PO / get_db_session 直接数据库访问，改用 report_repository 写入聚合根与子实体
- 移除 api_gateway 专属依赖（response / schemas.report / report_util / report_helpers），
  改从 report_service 对应模块导入
- gRPC helper 统一从 report_service.infrastructure.clients.grpc_clients 导入
- _create_report_record / _create_report_summary / _create_report_detail_data
  改为通过 report_repository 对应方法写入
- 移除 _build_response（Pydantic 响应组装属 api_gateway 职责，不在 report_service 内）
- 报告状态/类型使用字符串字面量 'draft' / 'task'，保持与现有数据模型一致
"""

from shared.models.common_enums import TaskStatus
from shared.utils.response import success_response, error_response
from shared.utils.result_data_store import load_full_result_data
from report_service.infrastructure.clients.grpc_clients import _grpc_algo_get_reference_params_for_report

from report_service.application.services.report_utils import ReportUtils
from report_service.application.services.report_query_builder import ReportQueryBuilder
from report_service.application.services.report_helpers import ReportHelpers
from report_service.infrastructure.persistence.report_repository import report_repository
from report_service.domain.entities import ReportAggregate

# 复用 grpc_clients 中已定义的 gRPC helper，避免重复实现
from report_service.infrastructure.clients.grpc_clients import (
    _grpc_get_dimension_results_by_result_ids as _grpc_get_dim_results,
    _grpc_list_dimensions_all,
    _grpc_list_testcases_by_ids,
    _dim_id, _dim_name,
    _grpc_get_device, _grpc_get_devices_by_ids,
    _grpc_get_api, _grpc_get_apis_by_ids,
    _grpc_get_task_devices, _grpc_get_task_apis,
    _grpc_get_tasks_by_ids, _grpc_get_test_results_by_task_ids,
    _grpc_get_task_merge_relations,
    _grpc_get_task_merge_relations_by_source,
)

import json


class ReportDataBuilder:
    """报告数据构建辅助（原 ReportCommandService 中 B 组方法）。

    承载任务报告数据构建相关的静态辅助方法，保持原有逻辑不变。
    """

    @staticmethod
    def _validate_task_and_get_results(task_id):
        # 通过 gRPC 获取 Task
        tasks = _grpc_get_tasks_by_ids([task_id])
        task = tasks[0] if tasks else None
        if not task:
            return None, None, error_response("未找到指定任务")

        task_type = task.get('type') if isinstance(task, dict) else task.type
        task_status = task.get('status') if isinstance(task, dict) else task.status

        if task_type == 'merged' and task_status == TaskStatus.COMPLETED.value:
            merge_relations = _grpc_get_task_merge_relations(task_id)
            if merge_relations:
                source_task_ids = [r.get('source_task_id') for r in merge_relations]
                results = _grpc_get_test_results_by_task_ids(source_task_ids)
            else:
                results = _grpc_get_test_results_by_task_ids([task_id])
            if not results:
                return None, None, error_response("生成失败: 合并任务没有测试结果数据")
            return task, results, None

        elif task_type == 'merged':
            merge_relations = _grpc_get_task_merge_relations(task_id)
            if merge_relations:
                source_task_ids = [r.get('source_task_id') for r in merge_relations]
                results = _grpc_get_test_results_by_task_ids(source_task_ids)
            else:
                results = _grpc_get_test_results_by_task_ids([task_id])
            if not results:
                return None, None, error_response("生成失败: 合并任务没有测试结果数据")
            return task, results, None

        elif task_status == TaskStatus.MERGED.value:
            merge_relations = _grpc_get_task_merge_relations_by_source(task_id)
            if merge_relations:
                merged_task_id = merge_relations[0].get('merged_task_id')
                source_relations = _grpc_get_task_merge_relations(merged_task_id)
                source_task_ids = [r.get('source_task_id') for r in source_relations]
                results = _grpc_get_test_results_by_task_ids(source_task_ids)
            else:
                results = _grpc_get_test_results_by_task_ids([task_id])
            if not results:
                return None, None, error_response("生成失败: 任务没有测试结果数据")
            return task, results, None

        elif task_status not in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]:
            return None, None, error_response("只有任务状态为completed、failed或merged时才能生成报告")

        results = _grpc_get_test_results_by_task_ids([task_id])
        if not results:
            return None, None, error_response("生成失败: 任务没有测试结果数据")

        return task, results, None

    @staticmethod
    def _get_dimension_results_batch(result_ids):
        if not result_ids:
            return {}, []

        dim_map = _grpc_get_dim_results(result_ids)

        dim_results_map = {}
        dim_stats = {}

        for rid, items in dim_map.items():
            for it in items:
                if not isinstance(it, dict):
                    continue
                dim_id = it.get('dimension_id')
                dim_val = it.get('dimension_value') or 0
                dim_name = it.get('dimension_name') or it.get('name')

                if rid not in dim_results_map:
                    dim_results_map[rid] = []
                dim_results_map[rid].append(it)

                if dim_id is not None:
                    if dim_id not in dim_stats:
                        dim_stats[dim_id] = {
                            "name": dim_name,
                            "total_dimension_value": 0,
                            "count": 0
                        }
                    dim_stats[dim_id]["total_dimension_value"] += dim_val
                    dim_stats[dim_id]["count"] += 1

        return dim_results_map, dim_stats

    @staticmethod
    def _get_resource_result_types_batch(task_id_or_ids, device_ids, api_ids):
        device_result_types = {}
        api_result_types = {}

        if isinstance(task_id_or_ids, list):
            results = _grpc_get_test_results_by_task_ids(task_id_or_ids)
        else:
            results = _grpc_get_test_results_by_task_ids([task_id_or_ids])

        if device_ids:
            dev_id_set = set(device_ids)
            device_results = [r for r in results if r.get('device_id') in dev_id_set]
            for result in device_results:
                if result.get('device_id') and result.get('result_data'):
                    full_data = load_full_result_data(result.get('result_data'), result.get('result_data_path'))
                    result_type = ReportDataBuilder._extract_result_type(full_data)
                    device_result_types[result.get('device_id')] = result_type

        if api_ids:
            api_id_set = set(api_ids)
            api_results = [r for r in results if r.get('api_id') in api_id_set]
            for result in api_results:
                if result.get('api_id') and result.get('result_data'):
                    full_data = load_full_result_data(result.get('result_data'), result.get('result_data_path'))
                    result_type = ReportDataBuilder._extract_result_type(full_data)
                    api_result_types[result.get('api_id')] = result_type

        return device_result_types, api_result_types

    @staticmethod
    def _extract_result_type(result_data):
        if not result_data:
            return 'default'
        try:
            if isinstance(result_data, str) and result_data.strip():
                result_data_dict = json.loads(result_data)
            elif isinstance(result_data, dict):
                result_data_dict = result_data
            else:
                return 'default'
            return result_data_dict.get('result_type', 'default') if isinstance(result_data_dict, dict) else 'default'
        except Exception:
            return 'default'

    @staticmethod
    def _build_case_basic_info(tc, results, task):
        """构建用例基本信息。"""
        case_results = results
        test_type = 'api' if case_results and (case_results[0].get('api_id') if isinstance(case_results[0], dict) else case_results[0].api_id) else 'e2e'

        audios_list = ReportHelpers._build_audios_list(tc, mode='task')
        reference_params_dict = ReportDataBuilder._get_reference_params(tc, case_results, test_type)

        tc_id = tc.get('id') if isinstance(tc, dict) else tc.id
        tc_name = tc.get('name') if isinstance(tc, dict) else tc.name
        tc_desc = (tc.get('description') if isinstance(tc, dict) else tc.description) or ""
        group = tc.get('group') if isinstance(tc, dict) else getattr(tc, 'group', None)
        category = (group.get('name') if isinstance(group, dict) else getattr(group, 'name', None)) if group else "未分类"
        tc_tags = (tc.get('tags') if isinstance(tc, dict) else getattr(tc, 'tags', [])) or []
        tc_algo_type = tc.get('algorithm_type') if isinstance(tc, dict) else getattr(tc, 'algorithm_type', None)

        case_obj = {
            "id": tc_id,
            "name": tc_name,
            "description": tc_desc,
            "category": category,
            "tags": [{"name": (t.get('name') if isinstance(t, dict) else getattr(t, 'name', None))} for t in tc_tags],
            "metrics": [],
            "results": [],
            "audios": audios_list,
            "reference_params": reference_params_dict,
            "algorithm_results": [],
            "algorithm_type": tc_algo_type,
            "logs": "\n".join([(r.get('error_message') if isinstance(r, dict) else r.error_message) for r in case_results if (r.get('error_message') if isinstance(r, dict) else r.error_message)])
        }

        for result in case_results:
            resource = ReportHelpers.get_resource_name(result, task, use_time_prefix=False)

            case_obj["results"].append({
                "resource": resource,
                **ReportHelpers.build_result_info(result),
            })

            algo_res = result.get('algorithm_result') if isinstance(result, dict) else result.algorithm_result
            result_data_raw = result.get('result_data') if isinstance(result, dict) else result.result_data
            result_data_path = result.get('result_data_path') if isinstance(result, dict) else getattr(result, 'result_data_path', None)
            result_data = load_full_result_data(result_data_raw, result_data_path)
            if not isinstance(result_data, dict):
                result_data = None

            if algo_res or result_data:
                combined_data = {}
                if algo_res:
                    combined_data.update(algo_res)
                if result_data:
                    combined_data.update(result_data)

                # 扁平列表格式，与 task_controller.py 一致
                for param_key, param_value in combined_data.items():
                    if param_key and param_value is not None:
                        param_type = ReportHelpers._infer_param_type(param_key)
                        case_obj["algorithm_results"].append({
                            'device': resource,
                            'param_code': param_key,
                            'param_type': param_type,
                            'label': param_key,
                            'value': param_value
                        })

        return case_obj

    @staticmethod
    def _build_case_metrics(tc, results, all_dimensions, dim_results_map, task):
        """构建用例指标数据，返回 metrics_list。"""
        case_results = results
        resource_metrics_map = {}

        for result in case_results:
            resource = ReportHelpers.get_resource_name(result, task, use_time_prefix=False)
            r_id = result.get('id') if isinstance(result, dict) else result.id
            dim_values = ReportHelpers.extract_dimension_values(
                r_id, all_dimensions, dim_results_map=dim_results_map
            )

            result_data_raw = result.get('result_data') if isinstance(result, dict) else result.result_data
            result_data_path = result.get('result_data_path') if isinstance(result, dict) else getattr(result, 'result_data_path', None)
            result_data = load_full_result_data(result_data_raw, result_data_path)
            if result_data and isinstance(result_data, dict):
                eval_data = result_data.get('evaluation_data') or result_data.get('eval_data') or {}
                if isinstance(eval_data, dict):
                    for dim_name, dim_value in eval_data.items():
                        if dim_name not in dim_values or dim_values.get(dim_name) is None:
                            dim_values[dim_name] = dim_value

            resource_metrics = []
            for dim_name, dim_value in dim_values.items():
                if dim_value is not None:
                    dim_id = None
                    for dim in all_dimensions:
                        if _dim_name(dim) == dim_name:
                            dim_id = _dim_id(dim)
                            break
                    resource_metrics.append({
                        "id": dim_id,
                        "metric": dim_name,
                        "value": dim_value
                    })
            if resource_metrics:
                resource_metrics_map[resource] = resource_metrics

        metrics_list = []
        for resource, metrics_data in resource_metrics_map.items():
            metrics_list.append({
                "resource": resource,
                "metrics": metrics_data
            })

        return metrics_list

    @staticmethod
    def _build_case_data(test_cases, results, all_dimensions, dim_results_map, task):
        results_by_case = {}
        for result in results:
            tc_id = result.get('test_case_id') if isinstance(result, dict) else result.test_case_id
            if tc_id not in results_by_case:
                results_by_case[tc_id] = []
            results_by_case[tc_id].append(result)

        cases = []

        for test_case in test_cases:
            tc_id = test_case.get('id') if isinstance(test_case, dict) else test_case.id
            case_results = results_by_case.get(tc_id, [])

            case_obj = ReportDataBuilder._build_case_basic_info(test_case, case_results, task)

            metrics_list = ReportDataBuilder._build_case_metrics(
                test_case, case_results, all_dimensions, dim_results_map, task
            )
            case_obj["metrics"] = metrics_list

            cases.append(case_obj)

        return cases

    @staticmethod
    def _get_reference_params(test_case, case_results, test_type):
        adjusted_reference_params = None
        for result in case_results:
            result_data_raw = result.get('result_data') if isinstance(result, dict) else result.result_data
            result_data_path = result.get('result_data_path') if isinstance(result, dict) else getattr(result, 'result_data_path', None)
            result_data = load_full_result_data(result_data_raw, result_data_path)
            if result_data and isinstance(result_data, dict):
                adjusted_reference_params = result_data.get('adjusted_reference_params')
                if adjusted_reference_params:
                    break

        if adjusted_reference_params:
            config_for_ref = {'reference_params': adjusted_reference_params}
        else:
            # 优先从独立列读取，兼容旧 config
            ref_col = getattr(test_case, 'reference_params', None) if not isinstance(test_case, dict) else test_case.get('reference_params')
            if ref_col:
                return _grpc_algo_get_reference_params_for_report(ref_col)
            config_for_ref = test_case.get('config') if isinstance(test_case, dict) else test_case.config

        return _grpc_algo_get_reference_params_for_report(config_for_ref)

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

            resource = ReportHelpers.get_resource_name(TempResult(d_id, result_type), task, use_time_prefix=False)
            resources.append(resource)

        for a in apis:
            a_id = a.get('id') if isinstance(a, dict) else a.id
            result_type = api_result_types.get(a_id, 'default')

            class TempResult:
                def __init__(self, api_id, result_type):
                    self.api_id = api_id
                    self.device_id = None
                    self.result_data = {"result_type": result_type}

            resource = ReportHelpers.get_resource_name(TempResult(a_id, result_type), task, use_time_prefix=False)
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
