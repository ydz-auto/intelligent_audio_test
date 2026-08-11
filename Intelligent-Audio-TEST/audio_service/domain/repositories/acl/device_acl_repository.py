# -*- coding: utf-8 -*-
"""Device 跨域 ACL 仓储接口。

device_service 域的数据通过 gRPC 只读访问，
接口定义在此 ABC，实现在 infrastructure/acl/device_acl_repository.py。
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class DeviceACLRepository(ABC):
    """device_service 跨域只读查询接口。"""

    @abstractmethod
    def check_audio_in_devices(self, audio_id: int) -> int:
        """检查音频是否被设备作为提示词引用"""
        ...
