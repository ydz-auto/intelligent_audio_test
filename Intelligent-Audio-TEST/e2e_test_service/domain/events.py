# -*- coding: utf-8 -*-
"""E2E 测试领域事件。

领域事件表示领域中已经发生的事实，供上层（应用层/基础设施层）订阅
以触发副作用（推送进度、写日志、同步状态等）。事件本身只携带数据，
不包含处理逻辑。
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TestStarted:
    """测试已开始事件"""
    task_id: str
    tc_rel_id: str
    timestamp: float = 0.0


@dataclass(frozen=True)
class DeviceConnected:
    """设备已连接事件"""
    task_id: str
    device_id: str
    device_sn: str
    timestamp: float = 0.0


@dataclass(frozen=True)
class AudioRecorded:
    """音频已录制/采集事件"""
    task_id: str
    tc_rel_id: str
    device_id: str
    audio_key: str
    timestamp: float = 0.0


@dataclass(frozen=True)
class TestCompleted:
    """测试已完成事件"""
    task_id: str
    tc_rel_id: str
    success: bool
    round_count: int = 0
    error_message: Optional[str] = None
    timestamp: float = 0.0
