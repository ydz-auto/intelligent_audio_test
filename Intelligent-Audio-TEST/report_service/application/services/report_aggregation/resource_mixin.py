# -*- coding: utf-8 -*-
"""报告聚合统计 — 资源聚合 Mixin（P4-5 大文件拆分）。

职责：聚合设备/API 资源列表、构建资源唯一键与表头、加载测试用例映射表。
"""
from __future__ import annotations

from report_service.application.services.report_aggregation.common import _r_get
from report_service.application.services.report_utils import ReportUtils
from report_service.application.services.report_utils.resource_mixin import (
    result_type_from_db_payload,
)
from report_service.infrastructure.clients.grpc_clients import (
    _grpc_get_task_devices,
    _grpc_get_task_apis,
    _grpc_get_devices_by_ids,
    _grpc_get_apis_by_ids,
    _grpc_list_testcases_by_ids,
)


class _AggregationResourceMixin:
    """资源聚合 Mixin：设备/API 资源列表聚合与用例映射加载。"""

    # ------------------------------------------------------------------
    # 子方法：资源列表聚合
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_resource_list(task, task_id, test_results=None, tasks_map=None,
                                 use_time_prefix=False) -> tuple:
        """聚合设备/API 资源列表，返回 (resources, resource_headers)。

        任务报告口径（与报告生成完全一致，INT-1059 对齐 b47cae340）：
        资源 key 无时间前缀、含版本、含 result_type 后缀（get_resource_name 形态），
        修复筛选聚合匹配恒失败导致 metricData 为空（筛选后数据全为 "-"）。
        多源任务（对比报告源任务集合）去重保序。

        对比/二次对比报告口径（INT-1059 返工，use_time_prefix=True）：
        资源 key 带 t{task}-{time} 前缀、按源任务各自聚合，与对比报告摘要资源列一致
        （report_compare_generator_data_mixin._collect_resources_batch 同源），
        修复前端对比面板列（按源任务展示）与筛选响应 key 不匹配导致数值不显示。

        Args:
            task: 任务对象（取第一个源任务即可满足标签格式化）
            task_id: 任务 ID（int 或 list，对比报告传源任务集合）
            test_results: 已过滤测试结果（用于派生 device/api result_type 后缀）
            tasks_map: {task_id: task}（use_time_prefix=True 时必传源任务映射）
            use_time_prefix: 对比/二次对比报告为 True——按源任务加 t{task}-{time} 前缀
        """
        if use_time_prefix:
            return _AggregationResourceMixin._aggregate_resource_list_per_task(
                test_results, tasks_map
            )

        task_devices, task_apis = _AggregationResourceMixin._collect_task_resources(task_id)

        device_ids = _AggregationResourceMixin._extract_ids(task_devices, 'device_id')
        api_ids = _AggregationResourceMixin._extract_ids(task_apis, 'api_id')

        devices_map = _grpc_get_devices_by_ids(device_ids) if device_ids else {}
        apis_map = _grpc_get_apis_by_ids(api_ids) if api_ids else {}

        # 按 task 关联顺序取设备/API 对象（去重保序，与表头顺序一一对应；
        # 对比报告多源任务共享同一设备/API 时仅保留首现）
        devices = []
        seen_devices = set()
        for td in task_devices:
            td_device_id = td.get('device_id') if isinstance(td, dict) else getattr(td, 'device_id', None)
            d = devices_map.get(td_device_id) if td_device_id else None
            if d and td_device_id not in seen_devices:
                seen_devices.add(td_device_id)
                devices.append(d)
        apis = []
        seen_apis = set()
        for ta in task_apis:
            ta_api_id = ta.get('api_id') if isinstance(ta, dict) else getattr(ta, 'api_id', None)
            a = apis_map.get(ta_api_id) if ta_api_id else None
            if a and ta_api_id not in seen_apis:
                seen_apis.add(ta_api_id)
                apis.append(a)

        # 从测试结果派生 device/api 的 result_type（与报告生成 _get_resource_result_types_batch 同源）
        device_result_types, api_result_types = _AggregationResourceMixin._get_result_types_from_results(
            test_results, device_ids, api_ids
        )

        # 复用报告生成资源构建：get_resource_name(TempResult, task, use_time_prefix=False)
        from report_service.application.services.report_data_builder_resource_mixin import (
            ReportDataResourceMixin,
        )
        resources = ReportDataResourceMixin._build_resources_list(
            devices, apis, task, device_result_types, api_result_types
        )

        resource_headers = []
        for idx, d in enumerate(devices):
            key = resources[idx] if idx < len(resources) else _AggregationResourceMixin._fallback_key(d)
            resource_headers.append(_AggregationResourceMixin._build_device_resource_header(task, key, d))
        for idx, a in enumerate(apis):
            key = resources[len(devices) + idx] if len(devices) + idx < len(resources) else _AggregationResourceMixin._fallback_key(a)
            resource_headers.append(_AggregationResourceMixin._build_api_resource_header(task, key, a))

        return resources, resource_headers

    @staticmethod
    def _aggregate_resource_list_per_task(test_results=None, tasks_map=None) -> tuple:
        """对比/二次对比报告筛选：按源任务聚合资源 key（t{task}-{time}-{resource} 前缀）。

        与对比报告摘要 _collect_resources_batch 同源（get_resource_name + use_time_prefix=True），
        保证筛选响应资源/指标 key 与前端对比面板列（summary.resources）一一对应；
        缺失任务映射时回退无前缀（任务报告行为）。
        """
        resource_set = set()
        for r in test_results or []:
            r_task_id = r.get('task_id') if isinstance(r, dict) else getattr(r, 'task_id', None)
            r_task = tasks_map.get(r_task_id) if tasks_map and r_task_id is not None else None
            if r_task is None:
                continue
            key = ReportUtils.get_resource_name(r, r_task, use_time_prefix=True)
            if key:
                resource_set.add(key)

        resources = sorted(resource_set)
        resource_headers = ReportUtils.build_resource_headers(
            resources=resources,
            results=test_results,
            tasks_map=tasks_map,
            use_time_prefix=True,
        ) if resources else []
        return resources, resource_headers

    @staticmethod
    def _fallback_key(obj) -> str:
        """资源 key 兜底（_build_resources_list 未产出时，退化为 无版本无后缀 形态）。"""
        obj_id = obj.get('id') if isinstance(obj, dict) else getattr(obj, 'id', None)
        obj_name = obj.get('name') if isinstance(obj, dict) else getattr(obj, 'name', '')
        return f"{obj_id}-{str(obj_name).lower()}"

    @staticmethod
    def _collect_task_resources(task_id) -> tuple:
        """按任务 ID（int 或 list）收集 TaskDevice / TaskAPI 关联记录。"""
        task_ids = task_id if isinstance(task_id, list) else [task_id]
        task_devices = []
        task_apis = []
        for tid in task_ids:
            task_devices.extend(_grpc_get_task_devices(tid))
            task_apis.extend(_grpc_get_task_apis(tid))
        return task_devices, task_apis

    @staticmethod
    def _extract_ids(rows, key) -> list:
        """从 TaskDevice/TaskAPI 行提取关联 ID（去重保序）。"""
        ids = []
        seen = set()
        for row in rows:
            rid = row.get(key) if isinstance(row, dict) else getattr(row, key, None)
            if rid is not None and rid not in seen:
                seen.add(rid)
                ids.append(rid)
        return ids

    @staticmethod
    def _get_result_types_from_results(test_results, device_ids, api_ids) -> tuple:
        """从测试结果派生 device/api 的 result_type 映射（与报告生成同源口径）。

        返回 (device_result_types, api_result_types)，key 为设备/API ID。
        """
        from report_service.application.services.report_utils.result_data_loader import (
            load_full_result_data_cached,
        )
        from report_service.application.services.report_data_builder_task_mixin import (
            ReportDataTaskMixin,
        )

        device_result_types = {}
        api_result_types = {}
        dev_id_set = set(device_ids or [])
        api_id_set = set(api_ids or [])
        for r in test_results or []:
            r_device_id = r.get('device_id') if isinstance(r, dict) else getattr(r, 'device_id', None)
            r_api_id = r.get('api_id') if isinstance(r, dict) else getattr(r, 'api_id', None)
            r_data = r.get('result_data') if isinstance(r, dict) else getattr(r, 'result_data', None)
            r_data_path = r.get('result_data_path') if isinstance(r, dict) else getattr(r, 'result_data_path', None)
            if not r_data:
                continue
            # INT-1572 返工：DB 轻量载荷已有 result_type 时不再读 OSS 结果文件
            # （缺失对象每条一次 head 请求，138 用例叠成几十秒）
            result_type = result_type_from_db_payload(r_data)
            if result_type is None:
                try:
                    full_data = load_full_result_data_cached(r_data, r_data_path)
                except Exception:
                    continue
                result_type = ReportDataTaskMixin._extract_result_type(full_data)
            if r_device_id and r_device_id in dev_id_set:
                device_result_types[r_device_id] = result_type
            if r_api_id and r_api_id in api_id_set:
                api_result_types[r_api_id] = result_type
        return device_result_types, api_result_types

    @staticmethod
    def _build_device_resource_header(task, key: str, d) -> dict:
        """构建设备资源表头。"""
        d_id = d.get('id') if isinstance(d, dict) else getattr(d, 'id', None)
        d_name = d.get('name') if isinstance(d, dict) else getattr(d, 'name', '')
        d_app_version = d.get('app_version') if isinstance(d, dict) else getattr(d, 'app_version', None)
        return {
            "key": key,
            "label": ReportUtils._format_resource_label(task, d_name, d_app_version, use_time_prefix=False) or key,
            "type": "device",
            "id": int(d_id) if d_id is not None else None,
            "name": str(d_name),
            "version": str(d_app_version) if d_app_version is not None else None,
            "editable": True,
        }

    @staticmethod
    def _build_api_resource_header(task, key: str, a) -> dict:
        """构建 API 资源表头。"""
        a_id = a.get('id') if isinstance(a, dict) else getattr(a, 'id', None)
        a_name = a.get('name') if isinstance(a, dict) else getattr(a, 'name', '')
        version = ReportUtils._extract_api_version(a)
        return {
            "key": key,
            "label": ReportUtils._format_resource_label(task, a_name, version, use_time_prefix=False) or key,
            "type": "api",
            "id": int(a_id) if a_id is not None else None,
            "name": str(a_name),
            "version": version,
            "editable": True,
        }

    # ------------------------------------------------------------------
    # 子方法：测试用例映射
    # ------------------------------------------------------------------

    @staticmethod
    def _load_test_cases_map(test_results: list) -> dict:
        """加载测试用例映射表，返回 {test_case_id: test_case}。"""
        test_case_ids_to_fetch = set()
        for result in test_results:
            tc_id = _r_get(result, 'test_case_id')
            if tc_id is not None:
                test_case_ids_to_fetch.add(tc_id)
        test_cases_map = {}
        if test_case_ids_to_fetch:
            tcs = _grpc_list_testcases_by_ids(list(test_case_ids_to_fetch))
            for tc in tcs.values() if isinstance(tcs, dict) else tcs:
                tc_id = tc.get('id') if isinstance(tc, dict) else getattr(tc, 'id', None)
                if tc_id is not None:
                    test_cases_map[tc_id] = tc
        return test_cases_map
