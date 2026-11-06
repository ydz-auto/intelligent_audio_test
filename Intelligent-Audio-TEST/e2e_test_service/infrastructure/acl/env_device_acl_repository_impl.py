# -*- coding: utf-8 -*-
"""环境设备 ACL 仓储 — gRPC 实现

封装 device_service.ControlEnvDevice gRPC 调用，供 e2e_test_service application 层使用。
替代原 e2e_device_manager.py 中内联定义的 _EnvDeviceProxy。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class EnvDeviceAclRepositoryImpl:
    """环境设备 ACL 仓储实现

    封装对 gRPC DeviceService.ControlEnvDevice 的调用，
    application 层通过此仓储控制环境设备（导轨等），不直接操作 gRPC stub。
    """

    def __init__(self, device_type: str = ''):
        self.device_type = device_type

    def _get_stub(self):
        from shared.clients.grpc_clients import get_env_device_service_stub
        return get_env_device_service_stub()

    def is_available(self) -> bool:
        """探测环境设备是否可用"""
        from shared.proto import device_service_pb2
        try:
            resp = self._get_stub().ControlEnvDevice(
                device_service_pb2.ControlEnvDeviceRequest(
                    task_id='',
                    device_action=json.dumps({
                        'device_type': self.device_type,
                        'action': 'is_available',
                    }),
                )
            )
            return resp.success
        except Exception:
            return False

    def setup(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """设置环境设备，返回状态供 teardown 恢复"""
        from shared.proto import device_service_pb2
        try:
            resp = self._get_stub().ControlEnvDevice(
                device_service_pb2.ControlEnvDeviceRequest(
                    task_id='',
                    device_action=json.dumps({
                        'device_type': self.device_type,
                        'action': 'setup',
                        'settings': settings,
                    }),
                )
            )
            if resp.success and resp.data:
                return json.loads(resp.data)
            return {}
        except Exception:
            return {}

    def teardown(self, state: Dict[str, Any]) -> None:
        """恢复环境设备到 setup 前的状态"""
        from shared.proto import device_service_pb2
        try:
            self._get_stub().ControlEnvDevice(
                device_service_pb2.ControlEnvDeviceRequest(
                    task_id='',
                    device_action=json.dumps({
                        'device_type': self.device_type,
                        'action': 'teardown',
                        'state': state,
                    }),
                )
            )
        except Exception:
            logger.warning("teardown 恢复环境设备状态失败 (device_type=%s)", self.device_type, exc_info=True)
