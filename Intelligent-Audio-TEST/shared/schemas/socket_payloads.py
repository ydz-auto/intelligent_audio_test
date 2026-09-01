# -*- coding: utf-8 -*-
"""Socket.IO 实时通道 payload 契约 —— snake_case

规范：
- Socket 通道（task_progress / task_log）payload 统一 snake_case，与后端字段一致；
  HTTP 通道的 camelCase 序列化（APIModel）不适用于 socket 通道。
- 前端由 infrastructure/adapters/taskProgressAdapter.ts 统一转换为 camelCase ReadModel。
- 本模块是 socket 进度 payload 的唯一字段契约来源，禁止各处手拼裸字典。
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class SocketPayload(BaseModel):
    """socket payload 基类：snake_case 字段直出，忽略未知字段。"""
    model_config = ConfigDict(extra="ignore")


class RoundProgress(SocketPayload):
    """多轮进度（内存态数据，gRPC 无法提供）"""
    current: int = 0
    total: int = 0


class ProgressCurrentCase(SocketPayload):
    """当前执行中的用例"""
    case_id: str = ""
    name: str = ""
    step: str = ""
    start_time: int = 0


class ProgressCaseItem(SocketPayload):
    """用例进度项"""
    id: str = ""
    status: str = ""
    execution_status: str = ""
    evaluation_status: str = ""
    duration: int = 0
    error_message: str = ""
    round_progress: Optional[RoundProgress] = None


class ProgressLogItem(SocketPayload):
    """最近日志项"""
    id: int = 0
    level: str = "info"
    message: str = ""
    timestamp: int = 0


class ProgressApiResource(SocketPayload):
    """API 资源实时状态"""
    id: str = ""
    name: str = ""
    current_concurrent: int = 0
    queue_length: int = 0
    avg_response_time: int = 0
    max_concurrent: int = 5


class TaskProgressPayload(SocketPayload):
    """task_progress 事件 payload（/ 命名空间）"""
    task_id: str
    status: str
    total_progress: float = 0.0
    completed_count: int = 0
    in_progress_count: int = 0
    execution_failed_count: int = 0
    evaluation_failed_count: int = 0
    total_count: int = 0
    current_case: Optional[ProgressCurrentCase] = None
    test_cases: List[ProgressCaseItem] = []
    logs: List[ProgressLogItem] = []
    api_resources: List[ProgressApiResource] = []
    expected_complete_time: str = ""
    expected_total_time: str = ""
    used_time: str = "0分钟"


class TaskLogEnvelope(SocketPayload):
    """task_log 事件外层包装（/ws/logs，Redis 转发路径）"""
    task_id: str
    log: Dict = {}
