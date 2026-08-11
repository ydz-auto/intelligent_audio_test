# -*- coding: utf-8 -*-
"""Device 跨域 ACL 仓储实现 — 通过 gRPC 调用 device_service。

从 audio_service/infrastructure/persistence/audio_repository.py 迁出，
确保自有仓储不再混入跨域查询逻辑。
"""
from __future__ import annotations

import logging

from audio_service.domain.repositories.acl.device_acl_repository import (
    DeviceACLRepository,
)

logger = logging.getLogger(__name__)


class DeviceACLRepositoryImpl(DeviceACLRepository):
    """device_service 跨域只读查询 gRPC 实现。"""

    def check_audio_in_devices(self, audio_id: int) -> int:
        """检查音频是否被设备作为提示词引用。

        通过 gRPC 调用 device_service.ListDevices，在返回结果中
        搜索 prompt_config 是否包含 audio_id；gRPC 不可用时返回 0。
        """
        try:
            from shared.clients.grpc_clients import get_device_config_service_stub
            from shared.proto import device_service_pb2 as _e2e_pb
            from shared.utils.grpc_json import loads as _grpc_loads

            stub = get_device_config_service_stub()
            resp = stub.ListDevices(_e2e_pb.ListDevicesRequest())
            if not resp.success:
                return 0
            data = _grpc_loads(resp.data, {}) or {}
            devices = data.get('devices', []) or data.get('items', []) or []
            count = 0
            for dev in devices:
                prompt_config = dev.get('prompt_config')
                if prompt_config and str(audio_id) in str(prompt_config):
                    count += 1
            return count
        except Exception:
            return 0
