# -*- coding: utf-8 -*-
"""报告聚合统计 — 资源聚合 Mixin（P4-5 大文件拆分）。

职责：聚合设备/API 资源列表、构建资源唯一键与表头、加载测试用例映射表。
"""
from __future__ import annotations

from report_service.application.services.report_aggregation.common import _r_get
from report_service.application.services.report_helpers import ReportHelpers
from report_service.application.services.report_utils import ReportUtils
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
    def _aggregate_resource_list(task, task_id: int) -> tuple:
        """聚合设备/API 资源列表，返回 (resources, resource_headers)。"""
        task_devices = _grpc_get_task_devices(task_id)
        task_apis = _grpc_get_task_apis(task_id)

        device_ids = [td.get('device_id') if isinstance(td, dict) else getattr(td, 'device_id', None) for td in task_devices]
        device_ids = [did for did in device_ids if did is not None]
        api_ids = [ta.get('api_id') if isinstance(ta, dict) else getattr(ta, 'api_id', None) for ta in task_apis]
        api_ids = [aid for aid in api_ids if aid is not None]

        devices_map = _grpc_get_devices_by_ids(device_ids) if device_ids else {}
        apis_map = _grpc_get_apis_by_ids(api_ids) if api_ids else {}

        time_prefix = ReportHelpers.get_task_time_prefix(task)
        resources = []
        resource_headers = []

        # 设备资源
        for td in task_devices:
            td_device_id = td.get('device_id') if isinstance(td, dict) else getattr(td, 'device_id', None)
            d = devices_map.get(td_device_id) if td_device_id else None
            if d:
                key = _AggregationResourceMixin._build_device_resource_key(time_prefix, d)
                resources.append(key)
                resource_headers.append(
                    _AggregationResourceMixin._build_device_resource_header(task, key, d)
                )

        # API 资源
        for ta in task_apis:
            ta_api_id = ta.get('api_id') if isinstance(ta, dict) else getattr(ta, 'api_id', None)
            a = apis_map.get(ta_api_id) if ta_api_id else None
            if a:
                key = _AggregationResourceMixin._build_api_resource_key(time_prefix, a)
                resources.append(key)
                resource_headers.append(
                    _AggregationResourceMixin._build_api_resource_header(task, key, a)
                )

        return resources, resource_headers

    @staticmethod
    def _build_device_resource_key(time_prefix: str, d) -> str:
        """构建设备资源唯一键。"""
        d_id = d.get('id') if isinstance(d, dict) else getattr(d, 'id', None)
        d_name = d.get('name') if isinstance(d, dict) else getattr(d, 'name', '')
        return f"{time_prefix}-{d_id}-{str(d_name).lower()}"

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
    def _build_api_resource_key(time_prefix: str, a) -> str:
        """构建 API 资源唯一键。"""
        a_id = a.get('id') if isinstance(a, dict) else getattr(a, 'id', None)
        a_name = a.get('name') if isinstance(a, dict) else getattr(a, 'name', '')
        return f"{time_prefix}-{a_id}-{str(a_name).lower()}"

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
