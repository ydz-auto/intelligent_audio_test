# -*- coding: utf-8 -*-
"""E2E 测试命令对象。

命令（Command）表示改变系统状态的意图。本模块仅定义命令数据结构，
不包含处理逻辑——处理逻辑在 handlers.py 中实现。
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class StartE2ETestCommand:
    """启动 E2E 测试命令"""
    task_id: str
    tc_rel_id: str
    device_ids: List[int] = field(default_factory=list)


@dataclass
class StopE2ETestCommand:
    """停止 E2E 测试命令"""
    task_id: str


@dataclass
class RecordAudioCommand:
    """录制/采集音频命令"""
    task_id: str
    tc_rel_id: str
    device_id: str
    audio_file_path: str
    device_index: Optional[int] = None
    channel_index: int = 0
    gain: float = 1.0
    loop: bool = False
