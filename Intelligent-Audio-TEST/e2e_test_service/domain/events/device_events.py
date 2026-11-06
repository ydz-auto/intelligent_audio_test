# -*- coding: utf-8 -*-
"""设备领域事件 - DeviceCreated/DeviceUpdated/DeviceDeleted。

领域事件表示领域中已经发生的事实，供上层（应用层/基础设施层）订阅
以触发副作用（推送进度、写日志、同步状态等）。事件本身只携带数据，
不包含处理逻辑。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class DeviceCreated:
    """设备已创建事件"""
    device_id: int
    name: str
    device_type: str
    timestamp: float = 0.0


@dataclass(frozen=True)
class DeviceUpdated:
    """设备已更新事件"""
    device_id: int
    changes: Dict[str, Any] = None
    timestamp: float = 0.0


@dataclass(frozen=True)
class DeviceDeleted:
    """设备已删除事件（逻辑删除）"""
    device_id: int
    operator: Optional[str] = None
    timestamp: float = 0.0
