# -*- coding: utf-8 -*-
"""device_service 防腐层仓储 — gRPC ACL 适配层。

封装 task_service 对 device_service 的跨域 gRPC 调用，
消除 infrastructure/persistence / read_models 层对
shared.clients.grpc_clients 的直接依赖。

相关 stub：
- shared.clients.grpc_clients.get_device_config_service_stub

proto：shared/proto/device_service_pb2
"""
import json
import logging
from typing import Dict, List, Optional

from shared.utils.grpc_json import loads as _loads

_logger = logging.getLogger(__name__)


class DeviceAclRepository:
    """device_service 防腐层仓储（gRPC ACL 适配层）。"""

    def get_device_statuses(self, device_ids: List[int]) -> List[dict]:
        """批量查询设备状态。

        封装 device_service.DeviceConfigService.GetDeviceStatuses RPC，
        返回 [{'id', 'name', 'status', ...}, ...]；失败返回空列表。
        """
        if not device_ids:
            return []
        from shared.clients.grpc_clients import get_device_config_service_stub
        from shared.proto import device_service_pb2 as e2e_pb
        try:
            stub = get_device_config_service_stub()
            resp = stub.GetDeviceStatuses(e2e_pb.GetDeviceStatusesRequest(
                data=json.dumps({"ids": list(device_ids)}),
            ))
            if not resp.success:
                _logger.warning("GetDeviceStatuses gRPC 失败: %s", resp.message)
                return []
            payload = _loads(resp.data, {}) or {}
            return payload.get('items', []) if isinstance(payload, dict) else (payload if isinstance(payload, list) else [])
        except Exception as e:
            _logger.warning("GetDeviceStatuses gRPC 异常: %s", e)
            return []

    def list_devices(self, page: int = 1, per_page: int = 1) -> dict:
        """查询设备列表（分页）。

        封装 device_service.DeviceConfigService.ListDevices RPC，
        返回 {'total': N, 'items': [...]}；失败返回空 dict。
        """
        from shared.clients.grpc_clients import get_device_config_service_stub
        from shared.proto import device_service_pb2 as e2e_pb
        try:
            stub = get_device_config_service_stub()
            resp = stub.ListDevices(e2e_pb.ListDevicesRequest(
                page=page, per_page=per_page,
            ))
            if not resp.success:
                return {}
            return _loads(resp.data, {}) or {}
        except Exception as e:
            _logger.warning("ListDevices gRPC 异常: %s", e)
            return {}

    def get_device_config_stub(self):
        """获取 DeviceConfigService gRPC stub。

        封装 shared.clients.grpc_clients.get_device_config_service_stub，
        供需要直接调用 stub 的场景使用。
        """
        from shared.clients.grpc_clients import get_device_config_service_stub
        return get_device_config_service_stub()


# 模块级单例
device_acl_repository = DeviceAclRepository()
