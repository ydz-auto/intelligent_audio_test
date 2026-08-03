# -*- coding: utf-8 -*-
"""E2E 测试领域实体。

实体拥有唯一标识（ID），其属性可变。E2ETestSession 是聚合根，
统一管理一次 E2E 测试会话内的设备会话、轮次进度与结果。

注意：本模块为纯领域模型，不包含数据库映射或 IO 调用。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from e2e_test_service.domain.value_objects import DeviceId, TestResult


@dataclass
class DeviceSession:
    """设备会话实体 - 代表一台被测设备在一次 E2E 测试中的上下文"""
    device_id: DeviceId
    device_sn: str
    device_name: str
    driver: Optional[str] = None
    prompt_audio_path: Optional[str] = None
    prompt_audio_name: Optional[str] = None
    needs_prompt_audio: bool = False
    connected: bool = False

    def connect(self):
        """标记设备已连接"""
        self.connected = True

    def disconnect(self):
        """标记设备已断开"""
        self.connected = False


@dataclass
class E2ETestSession:
    """E2E 测试会话聚合根

    聚合了一次任务（task_id）下、一个用例关联（tc_rel_id）的完整 E2E 执行上下文：
    - 关联的设备会话列表
    - 多轮执行进度
    - 已收集的测试结果
    """
    task_id: str
    tc_rel_id: str
    device_sessions: List[DeviceSession] = field(default_factory=list)
    round_progress: Dict[str, Dict] = field(default_factory=dict)
    results: List[TestResult] = field(default_factory=list)
    status: str = "idle"  # idle / running / stopping / completed / failed

    def add_device_session(self, session: DeviceSession):
        """添加设备会话"""
        self.device_sessions.append(session)

    def mark_running(self):
        """标记会话为运行中"""
        self.status = "running"

    def mark_stopping(self):
        """标记会话为停止中"""
        self.status = "stopping"

    def mark_completed(self):
        """标记会话已完成"""
        self.status = "completed"

    def mark_failed(self):
        """标记会话失败"""
        self.status = "failed"

    def update_round_progress(self, round_idx: int, total_rounds: int):
        """更新轮次进度"""
        self.round_progress[self.tc_rel_id] = {
            "round_idx": round_idx,
            "total_rounds": total_rounds,
        }

    def add_result(self, result: TestResult):
        """收集测试结果"""
        self.results.append(result)

    @property
    def is_terminal(self) -> bool:
        """是否处于终态"""
        return self.status in ("completed", "failed")
