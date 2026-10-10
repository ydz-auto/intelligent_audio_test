# -*- coding: utf-8 -*-
"""PlaybackConfig 跨域 ACL 仓储接口。

device_service 域的播放设备数据通过 gRPC 只读访问，
接口定义在此 ABC，实现在 infrastructure/acl/playback_acl_repository.py。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List


class PlaybackDeviceQueryError(RuntimeError):
    """播放设备跨域查询基础设施失败（device_service gRPC 调用异常或显式失败响应）。

    与「查询成功但无匹配设备」（返回 None / 空列表）严格区分：基础设施故障
    不得伪装成业务空结果（INT-90 缺陷 C——gRPC 间歇失败曾被翻译成
    「未找到可用设备。请先在设备管理中配置播放设备」误导排障）。
    """


class PlaybackConfigACLRepository(ABC):
    """device_service 播放设备跨域只读查询接口。"""

    @abstractmethod
    def list_playback_devices(self) -> List[dict]:
        """查询播放设备列表（ListPlaybackDevices）

        返回设备 dict 列表，每个 dict 包含 id/name/device_type/is_deleted 等字段。
        空列表 = device_service 正常应答但无设备；基础设施失败抛
        PlaybackDeviceQueryError。
        """
        ...

    @abstractmethod
    def get_playback_device(self, device_id) -> dict:
        """通过 gRPC 从 device_service 获取 PlaybackDevice 数据（返回 dict 或 None）。

        None = device_service 正常应答但设备不存在（GetPlaybackDeviceResponse
        未透传 code，success=False 的 404 与失败不可区分，维持既有「dict 或
        None」契约）；gRPC 调用异常抛 PlaybackDeviceQueryError。
        PlaybackDevice 归属 device_service，audio_service 不再直连 PO。
        """
        ...

    @abstractmethod
    def find_playback_device_by_unique_id(self, device_unique_id: str) -> dict:
        """通过 gRPC ListPlaybackDevices 按 device_unique_id 查找（返回 dict 或 None）。

        None = 列表正常应答但无匹配；基础设施失败抛 PlaybackDeviceQueryError。
        """
        ...

    @abstractmethod
    def find_playback_device_by_name(self, name: str) -> dict:
        """通过 gRPC ListPlaybackDevices 按 name 查找（返回 dict 或 None）。

        None = 列表正常应答但无匹配；基础设施失败抛 PlaybackDeviceQueryError。
        """
        ...
