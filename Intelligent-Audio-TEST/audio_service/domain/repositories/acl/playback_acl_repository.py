# -*- coding: utf-8 -*-
"""PlaybackConfig 跨域 ACL 仓储接口。

device_service 域的播放设备数据通过 gRPC 只读访问，
接口定义在此 ABC，实现在 infrastructure/acl/playback_acl_repository.py。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List


class PlaybackConfigACLRepository(ABC):
    """device_service 播放设备跨域只读查询接口。"""

    @abstractmethod
    def list_playback_devices(self) -> List[dict]:
        """查询播放设备列表（ListPlaybackDevices）

        返回设备 dict 列表，每个 dict 包含 id/name/device_type/is_deleted 等字段。
        gRPC 不可用时返回空列表。
        """
        ...

    @abstractmethod
    def get_playback_device(self, device_id) -> dict:
        """通过 gRPC 从 device_service 获取 PlaybackDevice 数据（返回 dict 或 None）。

        PlaybackDevice 归属 device_service，audio_service 不再直连 PO。
        """
        ...

    @abstractmethod
    def find_playback_device_by_unique_id(self, device_unique_id: str) -> dict:
        """通过 gRPC ListPlaybackDevices 按 device_unique_id 查找（返回 dict 或 None）。"""
        ...
