# -*- coding: utf-8 -*-
"""PlaybackConfig 跨域 ACL 仓储实现 — 通过 gRPC 调用 device_service。

封装 device_service 的播放设备查询，
使 application 层不再直接 import shared.clients.grpc_clients。
"""
from __future__ import annotations

import logging
from typing import List

from audio_service.domain.repositories.acl.playback_acl_repository import (
    PlaybackConfigACLRepository,
)

logger = logging.getLogger(__name__)


class PlaybackConfigACLRepositoryImpl(PlaybackConfigACLRepository):
    """device_service 播放设备跨域只读查询 gRPC 实现。"""

    def list_playback_devices(self) -> List[dict]:
        """查询播放设备列表（ListPlaybackDevices）

        通过 gRPC 调用 device_service.PlaybackConfigService.ListPlaybackDevices。
        gRPC 不可用时返回空列表。
        """
        try:
            from shared.clients.grpc_clients import get_playback_config_service_stub
            from shared.proto import device_service_pb2 as _e2e_pb
            from shared.utils.grpc_json import loads as _loads

            stub = get_playback_config_service_stub()
            resp = stub.ListPlaybackDevices(_e2e_pb.ListPlaybackDevicesRequest())
            if resp.success:
                data = _loads(resp.data, {}) or {}
                return data.get('devices', []) or data.get('items', []) or []
        except Exception:
            logger.debug("通过 gRPC 查询播放设备列表失败", exc_info=True)
        return []

    def get_playback_device(self, device_id) -> dict:
        """通过 gRPC 从 device_service 获取 PlaybackDevice 数据（返回 dict 或 None）。

        PlaybackDevice 归属 device_service，audio_service 不再直连 PO。
        """
        try:
            from shared.clients.grpc_clients import get_playback_config_service_stub
            from shared.proto import device_service_pb2 as _e2e_pb
            from shared.utils.grpc_json import loads as _grpc_loads

            stub = get_playback_config_service_stub()
            resp = stub.GetPlaybackDevice(
                _e2e_pb.GetPlaybackDeviceRequest(device_id=int(device_id))
            )
            if resp.success:
                return _grpc_loads(resp.data, {}) or {}
            return None
        except Exception:
            return None

    def find_playback_device_by_unique_id(self, device_unique_id: str) -> dict:
        """通过 gRPC ListPlaybackDevices 按 device_unique_id 查找（返回 dict 或 None）。"""
        try:
            from shared.clients.grpc_clients import get_playback_config_service_stub
            from shared.proto import device_service_pb2 as _e2e_pb
            from shared.utils.grpc_json import loads as _grpc_loads

            stub = get_playback_config_service_stub()
            resp = stub.ListPlaybackDevices(_e2e_pb.ListPlaybackDevicesRequest())
            if resp.success:
                data = _grpc_loads(resp.data, {}) or {}
                devices = data.get('devices', []) or data.get('items', []) or []
                for dev in devices:
                    if dev.get('device_unique_id') == device_unique_id and not dev.get('is_deleted'):
                        return dev
            return None
        except Exception:
            return None

    def find_playback_device_by_name(self, name: str) -> dict:
        """通过 gRPC ListPlaybackDevices 按 name 查找（返回 dict 或 None）。"""
        try:
            from shared.clients.grpc_clients import get_playback_config_service_stub
            from shared.proto import device_service_pb2 as _e2e_pb
            from shared.utils.grpc_json import loads as _grpc_loads

            stub = get_playback_config_service_stub()
            resp = stub.ListPlaybackDevices(_e2e_pb.ListPlaybackDevicesRequest())
            if resp.success:
                data = _grpc_loads(resp.data, {}) or {}
                devices = data.get('devices', []) or data.get('items', []) or []
                for dev in devices:
                    if dev.get('name') == name and not dev.get('is_deleted'):
                        return dev
            return None
        except Exception:
            return None
