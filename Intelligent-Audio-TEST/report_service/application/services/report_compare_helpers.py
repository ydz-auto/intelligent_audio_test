# -*- coding: utf-8 -*-
"""对比报告查询辅助方法集合（report_service 版本）。

从 api_gateway/application/services/report/report_compare_helpers.py 迁移而来，
保持 ReportCompareHelpers 类原有逻辑不变，仅做以下调整：
- 移除直接数据库访问（PO / get_db_session），改为通过 report_repository 读取 ReportCase PO
- 移除 api_gateway 专属依赖（response / error_codes / sqlalchemy / storage / pandas 等）
- gRPC helper 函数统一从 report_service.infrastructure.clients.grpc_clients 导入
- ReportUtils / ReportQueryBuilder 导入路径切换到 report_service
- _get_report_helpers 延迟导入指向 report_service.application.services.report_helpers
"""

from shared.models.common_enums import ReportStatus, ReportType, TaskStatus, TestType
from shared.utils.log_handler import log_not_emit, log_and_emit
from shared.utils.query_utils import (
    escape_like_pattern, sanitize_keyword, normalize_sort_field,
    normalize_sort_order, now_cst,
)
from shared.utils.result_data_store import load_full_result_data
from shared.infrastructure.storage import storage
from report_service.infrastructure.clients.grpc_clients import _grpc_algo_get_reference_params_for_report
from datetime import datetime
from sqlalchemy.orm import joinedload
from sqlalchemy import or_
import os
import zipfile
import json
import io
import pandas as pd

from report_service.application.services.report_utils import ReportUtils
from report_service.application.services.report_query_builder import ReportQueryBuilder

# 复用 grpc_clients 中已定义的 gRPC helper，避免重复实现
from report_service.infrastructure.clients.grpc_clients import (
    _grpc_get_dimension_results_by_result_ids as _grpc_get_dim_results,
    _grpc_list_dimensions_all,
    _grpc_get_dimension_params,
    _grpc_list_testcases_by_ids,
    _dim_id, _dim_name, _dim_weight,
    _grpc_get_device, _grpc_get_devices_by_ids,
    _grpc_get_api, _grpc_get_apis_by_ids,
    _grpc_get_task_devices,
    _grpc_get_task_apis,
    _grpc_get_tasks_by_ids,
    _grpc_get_test_results_by_task_ids,
    _grpc_get_test_result_by_id,
)

# 仓储：用于读取已存报告的 ReportCase PO（_get_source_cases /
# _get_source_cases_from_reports / _validate_reports_and_get_tasks）
from report_service.infrastructure.persistence.report_repository import report_repository


# 延迟导入 ReportHelpers 避免循环依赖（ReportHelpers 也 import 了本模块的 gRPC helpers）
def _get_report_helpers():
    from report_service.application.services.report_helpers import ReportHelpers
    return ReportHelpers


class ReportCompareHelpers:
    """对比报告查询辅助方法集合。

    承载从 ReportQueryService 拆分出的对比报告辅助方法，
    保持原有逻辑不变，仅做文件拆分。
    """

    # ------------------------------------------------------------------
    # 对比报告查询辅助方法（原 ReportControllerCompare，只读部分）
    # ------------------------------------------------------------------

    @staticmethod
    def _get_all_dimensions_with_results(result_ids):
        all_dimensions_all = _grpc_list_dimensions_all()

        used_dim_ids = set()
        if result_ids:
            dim_map = _grpc_get_dim_results(result_ids)
            # 从返回的 items 中收集所有出现过的 dimension_id
            for rid, items in dim_map.items():
                for it in items:
                    if isinstance(it, dict):
                        dim_id = it.get('dimension_id')
                        if dim_id is not None:
                            used_dim_ids.add(dim_id)

        all_dimensions = [d for d in all_dimensions_all if _dim_id(d) in used_dim_ids] if used_dim_ids else all_dimensions_all

        # 过滤掉 visible_in_report=False 的维度（所有 output 参数都不可见的维度）
        # 通过 gRPC 查询每个维度的 output 参数，判断是否有 visible_in_report=True 的参数
        all_output_dim_ids = set()
        visible_dim_ids = set()
        for dim in all_dimensions_all:
            dim_id = _dim_id(dim)
            if dim_id is None:
                continue
            params = _grpc_get_dimension_params(dim_id)
            for p in params:
                if not isinstance(p, dict):
                    continue
                if p.get('param_direction') != 'output':
                    continue
                if p.get('deleted', False):
                    continue
                all_output_dim_ids.add(dim_id)
                if p.get('visible_in_report', True):
                    visible_dim_ids.add(dim_id)

        hidden_dim_ids = all_output_dim_ids - visible_dim_ids
        if hidden_dim_ids:
            all_dimensions = [d for d in all_dimensions if _dim_id(d) not in hidden_dim_ids]

        return all_dimensions

    @staticmethod
    def _calculate_task_weighted_values(task_ids, results, all_dimensions):
        dim_map = {_dim_id(d): d for d in all_dimensions}
        total_weight = sum(_dim_weight(d) for d in all_dimensions if _dim_weight(d) is not None) if all_dimensions else 1
        if not total_weight:
            total_weight = 1

        task_weighted_values = {}

        res_ids_all = [r.get('id') if isinstance(r, dict) else r.id for r in results]
        dim_results_map, _ = ReportQueryBuilder.get_dimension_results_batch(res_ids_all)

        for tid in task_ids:
            task_results = [r for r in results if (r.get('task_id') if isinstance(r, dict) else r.task_id) == tid]
            if not task_results:
                task_weighted_values[tid] = 0
                continue

            dim_sums = {}
            dim_counts = {}

            for r in task_results:
                r_id = r.get('id') if isinstance(r, dict) else r.id
                result_dims = dim_results_map.get(r_id, [])
                for dr in result_dims:
                    dim_id = dr.get('dimension_id') if isinstance(dr, dict) else getattr(dr, 'dimension_id', None)
                    dim_value = dr.get('dimension_value') if isinstance(dr, dict) else getattr(dr, 'dimension_value', None)

                    dim_sums[dim_id] = dim_sums.get(dim_id, 0) + (dim_value or 0)
                    dim_counts[dim_id] = dim_counts.get(dim_id, 0) + 1

            weighted_sum = 0
            for dim_id, total_dimension_value in dim_sums.items():
                if dim_id in dim_map:
                    dim = dim_map[dim_id]
                    avg_value = total_dimension_value / dim_counts[dim_id]
                    w = _dim_weight(dim) or 0
                    weighted_sum += avg_value * (w / total_weight)

            task_weighted_values[tid] = weighted_sum

        return task_weighted_values

    @staticmethod
    def _collect_resources_batch(tasks, results):
        ReportHelpers = _get_report_helpers()
        resource_names = set()
        device_list = []
        api_list = []

        task_ids = [t.get('id') if isinstance(t, dict) else t.id for t in tasks]

        # 通过 gRPC 批量查询 TaskDevice / TaskAPI
        task_devices = []
        task_apis = []
        for tid in task_ids:
            tds = _grpc_get_task_devices(tid)
            for td in tds:
                if isinstance(td, dict):
                    task_devices.append(td)
            tas = _grpc_get_task_apis(tid)
            for ta in tas:
                if isinstance(ta, dict):
                    task_apis.append(ta)

        device_ids = list(set([td.get('device_id') for td in task_devices if td.get('device_id')]))
        api_ids = list(set([ta.get('api_id') for ta in task_apis if ta.get('api_id')]))

        devices_by_id = _grpc_get_devices_by_ids(device_ids) if device_ids else {}
        apis_by_id = _grpc_get_apis_by_ids(api_ids) if api_ids else {}

        tasks_map = {t.get('id') if isinstance(t, dict) else t.id: t for t in tasks}

        for res in results:
            res_task_id = res.get('task_id') if isinstance(res, dict) else res.task_id
            task = tasks_map.get(res_task_id)
            if task:
                resource = ReportHelpers.get_resource_name(res, task, use_time_prefix=True)
                if resource:
                    resource_names.add(resource)

        added_device_ids = set()
        for td in task_devices:
            dev_id = td.get('device_id')
            if dev_id and dev_id not in added_device_ids and dev_id in devices_by_id:
                device_list.append(ReportUtils.serialize_device(devices_by_id[dev_id]))
                added_device_ids.add(dev_id)

        added_api_ids = set()
        for ta in task_apis:
            api_id = ta.get('api_id')
            if api_id and api_id not in added_api_ids and api_id in apis_by_id:
                api_list.append(ReportUtils.serialize_api(apis_by_id[api_id]))
                added_api_ids.add(api_id)

        return resource_names, device_list, api_list

    @staticmethod
    def _build_case_data_compare(test_cases, results, all_dimensions, tasks_map, report_task_type):
        ReportHelpers = _get_report_helpers()
        results_by_case = {}
        for result in results:
            tc_id = result.get('test_case_id') if isinstance(result, dict) else result.test_case_id
            if tc_id not in results_by_case:
                results_by_case[tc_id] = []
            results_by_case[tc_id].append(result)

        res_ids_all = [r.get('id') if isinstance(r, dict) else r.id for r in results]
        dim_results_map, _ = ReportQueryBuilder.get_dimension_results_batch(res_ids_all)

        cases = []

        for test_case in test_cases:
            tc_id = test_case.get('id') if isinstance(test_case, dict) else test_case.id
            case_results = results_by_case.get(tc_id, [])
            case_metrics = {}
            config = (test_case.get('config') if isinstance(test_case, dict) else test_case.config) or {}

            reference_params_dict = ReportCompareHelpers._build_reference_params(case_results, config)

            for result in case_results:
                res_task_id = result.get('task_id') if isinstance(result, dict) else result.task_id
                task = tasks_map.get(res_task_id)
                resource = ReportUtils.get_resource_name(result, task, use_time_prefix=True)

                if not resource:
                    continue

                r_id = result.get('id') if isinstance(result, dict) else result.id
                dim_values = ReportHelpers.extract_dimension_values(
                    r_id, all_dimensions, dim_results_map=dim_results_map
                )
                case_metrics[resource] = dim_values

            audios_list = ReportHelpers._build_audios_list(test_case, mode='compare')

            tc_name = test_case.get('name') if isinstance(test_case, dict) else test_case.name
            tc_desc = (test_case.get('description') if isinstance(test_case, dict) else test_case.description) or ""
            group = test_case.get('group') if isinstance(test_case, dict) else getattr(test_case, 'group', None)
            category = (group.get('name') if isinstance(group, dict) else getattr(group, 'name', None)) if group else "未分类"
            tc_tags_raw = (test_case.get('tags') if isinstance(test_case, dict) else getattr(test_case, 'tags', [])) or []
            tc_algo_type = test_case.get('algorithm_type') if isinstance(test_case, dict) else getattr(test_case, 'algorithm_type', None)

            case_obj = {
                "id": tc_id,
                "name": tc_name,
                "description": tc_desc,
                "category": category,
                "tags": [{"name": (t.get('name') if isinstance(t, dict) else getattr(t, 'name', None))} for t in tc_tags_raw],
                "metrics": case_metrics,
                "results": [],
                "audios": audios_list,
                "reference_params": reference_params_dict,
                "algorithm_results": [],
                "algorithm_type": tc_algo_type,
                "logs": "\n".join([(result.get('error_message') if isinstance(result, dict) else result.error_message) for result in case_results if (result.get('error_message') if isinstance(result, dict) else result.error_message)])
            }

            for result in case_results:
                res_task_id = result.get('task_id') if isinstance(result, dict) else result.task_id
                task = tasks_map.get(res_task_id)
                resource = ReportHelpers.get_resource_name(result, task, use_time_prefix=True)
                exec_status = result.get('execution_status') if isinstance(result, dict) else result.execution_status
                created_at = result.get('created_at') if isinstance(result, dict) else result.created_at

                case_obj["results"].append({
                    "resource": resource,
                    "status": "成功" if exec_status == "completed" else "失败",
                    "start_time": created_at.isoformat() if hasattr(created_at, 'isoformat') else (created_at if isinstance(created_at, str) else None),
                    "end_time": created_at.isoformat() if hasattr(created_at, 'isoformat') else (created_at if isinstance(created_at, str) else None),
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

            cases.append(case_obj)

        return cases

    @staticmethod
    def _build_reference_params(case_results, config):
        adjusted_reference_params = None

        for result in case_results:
            result_data_raw = result.get('result_data') if isinstance(result, dict) else result.result_data
            result_data_path = result.get('result_data_path') if isinstance(result, dict) else getattr(result, 'result_data_path', None)
            result_data = load_full_result_data(result_data_raw, result_data_path)
            if result_data and isinstance(result_data, dict):
                adjusted_ref = result_data.get('adjusted_reference_params')
                if adjusted_ref:
                    adjusted_reference_params = adjusted_ref

        # 双记录架构：使用 adjusted params 覆盖 config 中的 reference_params
        effective_config = config
        if adjusted_reference_params:
            effective_config = {'reference_params': adjusted_reference_params}

        reference_params = _grpc_algo_get_reference_params_for_report(effective_config)

        reference_params_dict = {}
        for code, param_info in reference_params.items():
            reference_params_dict[code] = {
                "code": code,
                "type": param_info.get('type', 'text'),
                "value": param_info.get('value'),
                "segments": param_info.get('segments', []),
                "text": param_info.get('text', ''),
                "json": param_info.get('json', ''),
            }

        return reference_params_dict

    @staticmethod
    def _build_comparison_matrix(results, all_dimensions):
        dim_map = {_dim_id(d): d for d in all_dimensions}
        comparison_matrix = {}

        test_case_ids = list(set([r.get('test_case_id') if isinstance(r, dict) else r.test_case_id for r in results]))
        test_cases_map = _grpc_list_testcases_by_ids(test_case_ids)

        res_ids = [r.get('id') if isinstance(r, dict) else r.id for r in results]
        dim_results_map, _ = ReportQueryBuilder.get_dimension_results_batch(res_ids)

        for res in results:
            res_tc_id = res.get('test_case_id') if isinstance(res, dict) else res.test_case_id
            if res_tc_id not in comparison_matrix:
                case = test_cases_map.get(res_tc_id) if isinstance(res_tc_id, int) else None
                case_name = (case.get('name') if isinstance(case, dict) else getattr(case, 'name', None)) if case else res_tc_id
                comparison_matrix[res_tc_id] = {
                    "case_id": res_tc_id,
                    "case_name": case_name
                }

            dim_values = {}
            res_id = res.get('id') if isinstance(res, dict) else res.id
            result_dims = dim_results_map.get(res_id, [])
            for d in result_dims:
                dim_id = d.get('dimension_id') if isinstance(d, dict) else getattr(d, 'dimension_id', None)
                dim_value = d.get('dimension_value') if isinstance(d, dict) else getattr(d, 'dimension_value', None)
                if dim_id in dim_map:
                    dim_values[_dim_name(dim_map[dim_id])] = dim_value or 0

            for dim in all_dimensions:
                dname = _dim_name(dim)
                if dname and dname not in dim_values:
                    dim_values[dname] = 0

            res_task_id = res.get('task_id') if isinstance(res, dict) else res.task_id
            res_exec_status = res.get('execution_status') if isinstance(res, dict) else res.execution_status
            res_response_time = res.get('response_time') if isinstance(res, dict) else res.response_time

            comparison_matrix[res_tc_id][f"task_{res_task_id}"] = {
                "status": 'completed' if res_exec_status == 'completed' else 'failed',
                "response_time": res_response_time or 0,
                "values": dim_values
            }

        return comparison_matrix

    @staticmethod
    def _get_source_cases(tasks):
        """从各 task 最新报告中读取已存 ReportCase PO，组装为 source_cases。

        原实现使用 Report.query.filter(Report.task_id.in_(task_ids)) 与
        ReportCase.query.filter_by(report_id=...) 直连 PO；
        迁移后改用 report_repository.get_report_by_task_id_raw /
        get_cases_by_report_id 读取原始 PO。
        """
        source_cases = []
        task_ids = [t.id for t in tasks]

        # 逐 task 取最新报告 PO（原 Report.query.filter(...).order_by(...).all()
        # 取每个 task 最新一条，等价于循环调用 get_report_by_task_id_raw）
        reports_by_task = {}
        for task_id in task_ids:
            report = report_repository.get_report_by_task_id_raw(task_id)
            if report:
                reports_by_task[task_id] = report

        for task_id in task_ids:
            report = reports_by_task.get(task_id)
            if report:
                case_records = report_repository.get_cases_by_report_id(report.id)
                for case_record in case_records:
                    case_item = {
                        "id": case_record.test_case_id,
                        "name": case_record.name,
                        "description": case_record.description or "",
                        "category": case_record.category,
                        "tags": case_record.tags or [],
                        "metrics": case_record.metrics or {},
                        "results": case_record.results or [],
                        "audios": case_record.audios or [],
                        "reference_params": case_record.reference_params,
                        "algorithm_results": case_record.algorithm_results,
                        "algorithm_type": case_record.algorithm_type,
                        "logs": case_record.logs
                    }
                    source_cases.append(case_item)

        return source_cases

    # ------------------------------------------------------------------
    # 二次对比报告查询辅助方法（原 ReportControllerSecondary，只读部分）
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_reports_and_get_tasks(report_ids):
        """校验报告列表并提取关联 task_ids。

        原实现使用 Report.query.filter(Report.id.in_(report_ids))
        .order_by(Report.created_at.asc()).all() 直连 PO；
        迁移后改用 report_repository.get_report_by_id_raw 逐个读取原始 PO。
        """
        # 逐个按 ID 读取原始 Report PO，保持按 created_at 升序排列
        reports = []
        for rid in report_ids:
            po = report_repository.get_report_by_id_raw(rid)
            if po is not None:
                reports.append(po)
        # 按 created_at 升序排序（原 .order_by(Report.created_at.asc())）
        reports.sort(key=lambda r: (r.created_at is None, r.created_at))

        if len(reports) < 2:
            return None, None, None, "二次对比至少需要两个报告"

        task_ids = set()
        for report in reports:
            if report.task_id:
                task_ids.add(report.task_id)
            elif report.type in ('comparison', 'secondary_comparison'):
                summary_info = getattr(report, 'summary_info', None)
                if summary_info and summary_info.task_ids:
                    for tid in summary_info.task_ids:
                        task_ids.add(tid)

        task_ids = list(task_ids)
        tasks = []
        if task_ids:
            all_tasks = _grpc_get_tasks_by_ids(task_ids)
            tasks = [t for t in all_tasks if t.get('status') in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.MERGED.value]]

        if not tasks:
            return None, None, None, "未找到关联的任务数据"

        return reports, tasks, task_ids, None

    @staticmethod
    def _get_task_type(tasks):
        included_task_types = {(t.get('type') if isinstance(t, dict) else getattr(t, "type", None)) for t in tasks if (t.get('type') if isinstance(t, dict) else getattr(t, "type", None))}
        if included_task_types == {TestType.API.value}:
            return TestType.API.value
        elif included_task_types == {TestType.E2E.value}:
            return TestType.E2E.value
        return "all"

    @staticmethod
    def _collect_all_resources(task_ids, tasks):
        ReportHelpers = _get_report_helpers()
        from report_service.application.services.report_data_builder import ReportDataBuilder

        results = _grpc_get_test_results_by_task_ids(task_ids)
        if not results:
            return None, None, None, None, None, "未找到测试结果数据"

        resources = set()
        for t in tasks:
            t_id = t.get('id') if isinstance(t, dict) else t.id
            task_results = [r for r in results if (r.get('task_id') if isinstance(r, dict) else r.task_id) == t_id]
            for res in task_results:
                resource = ReportHelpers.get_resource_name(res, t, use_time_prefix=False)
                if resource:
                    resources.add(resource)

        if not resources:
            resources = {"默认资源"}
        resources = sorted(list(resources))

        devices_list, apis_list, device_ids, api_ids = ReportDataBuilder._get_task_resources(task_ids)

        if not devices_list and not apis_list:
            return None, None, None, None, None, "未找到设备或API资源数据"

        return results, resources, devices_list, apis_list, device_ids, api_ids, None

    @staticmethod
    def _build_all_dimensions(result_ids):
        from report_service.application.services.report_data_builder import ReportDataBuilder

        used_dim_ids = set()
        if result_ids:
            dim_map = _grpc_get_dim_results(result_ids)
            for rid, items in dim_map.items():
                for it in items:
                    if isinstance(it, dict):
                        dim_id = it.get('dimension_id')
                        if dim_id is not None:
                            used_dim_ids.add(dim_id)

        all_dimensions_all = _grpc_list_dimensions_all()
        all_dimensions = [d for d in all_dimensions_all if _dim_id(d) in used_dim_ids] if used_dim_ids else all_dimensions_all

        # 过滤掉 visible_in_report=False 的维度（所有 output 参数都不可见的维度）
        all_output_dim_ids = set()
        visible_dim_ids = set()
        for dim in all_dimensions_all:
            dim_id = _dim_id(dim)
            if dim_id is None:
                continue
            params = _grpc_get_dimension_params(dim_id)
            for p in params:
                if not isinstance(p, dict):
                    continue
                if p.get('param_direction') != 'output':
                    continue
                if p.get('deleted', False):
                    continue
                all_output_dim_ids.add(dim_id)
                if p.get('visible_in_report', True):
                    visible_dim_ids.add(dim_id)

        hidden_dim_ids = all_output_dim_ids - visible_dim_ids
        if hidden_dim_ids:
            all_dimensions = [d for d in all_dimensions if _dim_id(d) not in hidden_dim_ids]

        if not all_dimensions:
            return None, None, "未找到评估维度数据"

        all_metrics = ReportDataBuilder._build_all_metrics(all_dimensions)
        return all_dimensions, all_metrics, None

    @staticmethod
    def _build_comparison_matrix_secondary(task_ids, reports, all_dimensions):
        comparison_matrix = {}
        if not task_ids:
            return {}

        results = _grpc_get_test_results_by_task_ids(task_ids)
        dim_map = {_dim_id(d): d for d in all_dimensions}

        # 预取所有维度结果
        res_ids = [r.get('id') if isinstance(r, dict) else r.id for r in results]
        dim_results_map = _grpc_get_dim_results(res_ids)

        # 预取所有 TestCase
        test_case_ids = list(set([r.get('test_case_id') if isinstance(r, dict) else r.test_case_id for r in results]))
        test_cases_map = _grpc_list_testcases_by_ids(test_case_ids)

        for res in results:
            res_tc_id = res.get('test_case_id') if isinstance(res, dict) else res.test_case_id
            if res_tc_id not in comparison_matrix:
                case = test_cases_map.get(res_tc_id) if isinstance(res_tc_id, int) else None
                case_name = (case.get('name') if isinstance(case, dict) else getattr(case, 'name', None)) if case else res_tc_id
                comparison_matrix[res_tc_id] = {
                    "case_id": res_tc_id,
                    "case_name": case_name
                }

            res_id = res.get('id') if isinstance(res, dict) else res.id
            dimensions = dim_results_map.get(res_id, [])
            dim_values = {}
            for d in dimensions:
                if isinstance(d, dict):
                    dim_id = d.get('dimension_id')
                    dim_val = d.get('dimension_value')
                else:
                    dim_id = getattr(d, 'dimension_id', None)
                    dim_val = getattr(d, 'dimension_value', None)
                if dim_id in dim_map:
                    dim_values[_dim_name(dim_map[dim_id])] = dim_val or 0

            for dim in all_dimensions:
                dname = _dim_name(dim)
                if dname and dname not in dim_values:
                    dim_values[dname] = 0

            res_task_id = res.get('task_id') if isinstance(res, dict) else res.task_id
            res_exec_status = res.get('execution_status') if isinstance(res, dict) else res.execution_status
            res_response_time = res.get('response_time') if isinstance(res, dict) else res.response_time

            comparison_matrix[res_tc_id][f"task_{res_task_id}"] = {
                "status": 'completed' if res_exec_status == 'completed' else 'failed',
                "response_time": res_response_time or 0,
                "values": dim_values
            }

        return {
            "report_ids": [r.id for r in reports],
            "report_names": [r.name for r in reports],
            "task_ids": task_ids,
            "task_names": [],
            "matrix": comparison_matrix,
            "generated_at": now_cst().isoformat()
        }

    @staticmethod
    def _get_source_cases_from_reports(reports):
        """从给定报告列表读取已存 ReportCase PO，组装为 source_cases。

        原实现使用 ReportCase.query.filter_by(report_id=report.id).all() 直连 PO；
        迁移后改用 report_repository.get_cases_by_report_id 读取原始 PO。
        """
        source_cases = []
        for report in reports:
            case_records = report_repository.get_cases_by_report_id(report.id)
            for case_record in case_records:
                case_item = {
                    "id": case_record.test_case_id,
                    "name": case_record.name,
                    "description": case_record.description or "",
                    "category": case_record.category,
                    "tags": case_record.tags or [],
                    "metrics": case_record.metrics or {},
                    "results": case_record.results or [],
                    "audios": case_record.audios or [],
                    "reference_params": case_record.reference_params,
                    "algorithm_results": case_record.algorithm_results,
                    "algorithm_type": case_record.algorithm_type,
                    "logs": case_record.logs
                }
                source_cases.append(case_item)
        return source_cases
