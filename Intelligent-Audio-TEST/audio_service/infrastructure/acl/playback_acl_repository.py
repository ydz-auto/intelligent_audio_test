# -*- coding: utf-8 -*-
"""PlaybackConfig 跨域 ACL 仓储实现 — 通过 gRPC 调用 device_service。

封装 device_service 的播放设备查询，
使 application 层不再直接 import shared.clients.grpc_clients。

失败语义（INT-90 缺陷 C）：基础设施失败（gRPC 调用异常、列表类接口
success=False）抛 PlaybackDeviceQueryError 向上传递真实错误，不返回
[]/None 伪装成业务空结果；「正常应答但无匹配」仍返回 []/None。
"""
from __future__ import annotations

from typing import List

from audio_service.domain.repositories.acl.playback_acl_repository import (
    PlaybackConfigACLRepository,
    PlaybackDeviceQueryError,
)


class PlaybackConfigACLRepositoryImpl(PlaybackConfigACLRepository):
    """device_service 播放设备跨域只读查询 gRPC 实现。"""

    def list_playback_devices(self) -> List[dict]:
        """查询播放设备列表（ListPlaybackDevices）

        通过 gRPC 调用 device_service.PlaybackConfigService.ListPlaybackDevices。
        基础设施失败抛 PlaybackDeviceQueryError，正常应答无设备返回空列表。
        """
        try:
            from shared.clients.grpc_clients import get_playback_config_service_stub
            from shared.proto import device_service_pb2 as _e2e_pb
            from shared.utils.grpc_json import loads as _loads

            stub = get_playback_config_service_stub()
            resp = stub.ListPlaybackDevices(_e2e_pb.ListPlaybackDevicesRequest())
            if not resp.success:
                raise PlaybackDeviceQueryError(
                    f"ListPlaybackDevices 响应失败: {resp.message}")
            data = _loads(resp.data, {}) or {}
            return data.get('devices', []) or data.get('items', []) or []
        except PlaybackDeviceQueryError:
            raise
        except Exception as e:
            raise PlaybackDeviceQueryError(
                f"ListPlaybackDevices gRPC 调用失败: {e}") from e

    def get_playback_device(self, device_id) -> dict:
        """通过 gRPC 从 device_service 获取 PlaybackDevice 数据（返回 dict 或 None）。

        PlaybackDevice 归属 device_service，audio_service 不再直连 PO。
        """
        try:
            device_id = int(device_id)
        except (TypeError, ValueError):
            return None
        try:
            from shared.clients.grpc_clients import get_playback_config_service_stub
            from shared.proto import device_service_pb2 as _e2e_pb
            from shared.utils.grpc_json import loads as _grpc_loads

            stub = get_playback_config_service_stub()
            resp = stub.GetPlaybackDevice(
                _e2e_pb.GetPlaybackDeviceRequest(device_id=device_id)
            )
            if resp.success:
                return _grpc_loads(resp.data, {}) or {}
            return None
        except Exception as e:
            raise PlaybackDeviceQueryError(
                f"GetPlaybackDevice({device_id}) gRPC 调用失败: {e}") from e

    def find_playback_device_by_unique_id(self, device_unique_id: str) -> dict:
        """通过 gRPC ListPlaybackDevices 按 device_unique_id 查找（返回 dict 或 None）。"""
        devices = self.list_playback_devices()
        for dev in devices:
            if dev.get('device_unique_id') == device_unique_id and not dev.get('is_deleted'):
                return dev
        return None

    def find_playback_device_by_name(self, name: str) -> dict:
        """通过 gRPC ListPlaybackDevices 按 name 查找（返回 dict 或 None）。"""
        devices = self.list_playback_devices()
        for dev in devices:
            if dev.get('name') == name and not dev.get('is_deleted'):
                return dev
        return None
