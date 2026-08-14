# -*- coding: utf-8 -*-
"""report_service / api_test_service 防腐层仓储 — gRPC ACL 适配层。

封装 task_service 对 report_service / api_test_service 的跨域 gRPC 调用，
消除 infrastructure/read_models 层对 shared.clients.grpc_clients 的直接依赖。

相关 stub：
- shared.clients.grpc_clients.get_report_config_service_stub
- shared.clients.grpc_clients.get_api_test_service_stub

proto：shared/proto/report_service_pb2 / api_test_service_pb2
"""
import logging
from typing import List

from shared.utils.grpc_json import loads as _loads

_logger = logging.getLogger(__name__)


class ReportAclRepository:
    """report_service 防腐层仓储（gRPC ACL 适配层）。"""

    def list_reports(self, task_id=None, page: int = 1, per_page: int = 100) -> dict:
        """查询报告列表（可按 task_id 过滤）。

        封装 report_service.ReportConfigService.ListReports RPC，
        返回 {'total': N, 'items': [...]}；失败返回空 dict。
        """
        from shared.clients.grpc_clients import get_report_config_service_stub
        from shared.proto import report_service_pb2 as report_pb
        try:
            stub = get_report_config_service_stub()
            resp = stub.ListReports(report_pb.ListReportsRequest(
                page=page, per_page=per_page,
                task_id=int(task_id) if task_id else 0,
            ))
            if not resp.success:
                return {}
            return _loads(resp.data, {}) or {}
        except Exception as e:
            _logger.warning("ListReports gRPC 异常: %s", e)
            return {}

    def list_reports_count(self) -> int:
        """查询报告总数。失败返回 0。"""
        payload = self.list_reports(page=1, per_page=1)
        return int(payload.get('total', 0) or 0) if payload else 0

    def get_report_config_stub(self):
        """获取 ReportConfigService gRPC stub。

        封装 shared.clients.grpc_clients.get_report_config_service_stub，
        供需要直接调用 stub 的场景使用。
        """
        from shared.clients.grpc_clients import get_report_config_service_stub
        return get_report_config_service_stub()


# 模块级单例
report_acl_repository = ReportAclRepository()


class ApiTestAclRepository:
    """api_test_service 防腐层仓储（gRPC ACL 适配层）。"""

    def list_apis_count(self) -> int:
        """查询 API 总数。失败返回 0。"""
        from shared.clients.grpc_clients import get_api_test_service_stub
        from shared.proto import api_test_service_pb2 as api_pb
        try:
            stub = get_api_test_service_stub()
            resp = stub.ListAPIConfigs(api_pb.ListAPIConfigsRequest(
                page=1, per_page=1,
            ))
            if not resp.success:
                return 0
            payload = _loads(resp.data, {}) or {}
            return int(payload.get('total', 0) or 0)
        except Exception as e:
            _logger.warning("ListAPIConfigs gRPC 异常: %s", e)
            return 0

    def get_api_config(self, api_id) -> dict:
        """按 ID 查询单个 API 配置，返回 dict 或 None。"""
        from shared.clients.grpc_clients import get_api_test_service_stub
        from shared.proto import api_test_service_pb2 as api_pb
        try:
            stub = get_api_test_service_stub()
            resp = stub.GetAPIConfig(api_pb.GetAPIConfigRequest(api_id=api_id))
            if resp.success and resp.data:
                return _loads(resp.data, {}) or {}
        except Exception as e:
            _logger.warning("GetAPIConfig gRPC 异常 (api_id=%s): %s", api_id, e)
        return None

    def fetch_api_list(self, api_ids: List) -> list:
        """批量获取 API 列表（含 id/name/status）。

        封装 api_test_service.APITestService.GetAPIConfig 逐个查询，
        失败时返回空列表。
        """
        if not api_ids:
            return []
        result = []
        for api_id in api_ids:
            api_data = self.get_api_config(api_id)
            if isinstance(api_data, dict):
                result.append({
                    'id': api_data.get('id'),
                    'name': api_data.get('name'),
                    'status': api_data.get('status'),
                })
        return result

    def fetch_api_names(self, api_ids: List) -> dict:
        """批量获取 API 名称，返回 {api_id: name} 映射。失败时返回空 dict。"""
        if not api_ids:
            return {}
        name_map = {}
        for api_id in api_ids:
            api_data = self.get_api_config(api_id)
            if isinstance(api_data, dict):
                name_map[api_id] = api_data.get('name')
        return name_map

    def get_api_test_stub(self):
        """获取 APITestService gRPC stub。

        封装 shared.clients.grpc_clients.get_api_test_service_stub，
        供需要直接调用 stub 的场景使用。
        """
        from shared.clients.grpc_clients import get_api_test_service_stub
        return get_api_test_service_stub()


# 模块级单例
api_test_acl_repository = ApiTestAclRepository()
