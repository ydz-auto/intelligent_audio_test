# -*- coding: utf-8 -*-
"""任务命令定义 (Task Commands) - CQRS 写模型。

命令对象是不可变的意图描述，仅包含执行所需数据，不包含业务逻辑。
处理器消费命令并委托给 ExecutionEngine 等基础设施。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Command:
    """命令基类。所有命令返回 (success: bool, message: str)。"""
    pass


@dataclass(frozen=True)
class CreateTaskCommand(Command):
    """创建任务命令。

    ExecutionEngine 不提供独立的 create_task，
    实际 Task 记录由上层业务创建后通过 StartTaskCommand 启动。
    本命令用于在应用层显式建立任务记录。
    """
    name: str
    task_type: str = 'api'  # api / e2e
    description: str = ''
    config: Dict[str, Any] = field(default_factory=dict)
    algorithm_type: Optional[str] = None
    algorithm_params: Dict[str, Any] = field(default_factory=dict)
    case_ids: List[str] = field(default_factory=list)
    device_ids: List[int] = field(default_factory=list)
    api_ids: List[int] = field(default_factory=list)
    created_by: Optional[int] = None


@dataclass(frozen=True)
class StartTaskCommand(Command):
    """启动任务命令。委托给 ExecutionEngine.start_task。"""
    task_id: int


@dataclass(frozen=True)
class StopTaskCommand(Command):
    """停止任务命令。委托给 ExecutionEngine.control_task(task_id, 'stop')。"""
    task_id: int


@dataclass(frozen=True)
class PauseTaskCommand(Command):
    """暂停任务命令。委托给 ExecutionEngine.control_task(task_id, 'pause')。"""
    task_id: int


@dataclass(frozen=True)
class ResumeTaskCommand(Command):
    """恢复任务命令。委托给 ExecutionEngine.control_task(task_id, 'resume')。"""
    task_id: int


@dataclass(frozen=True)
class RemoveFromQueueCommand(Command):
    """从队列移除任务命令。委托给 ExecutionEngine.remove_from_queue。"""
    task_id: int


@dataclass(frozen=True)
class ReevaluateTaskCommand(Command):
    """重新评估任务命令。委托给 ReevaluationExecutor.submit。"""
    task_id: int
    reextract_device_output: bool = True
    reevaluate_type: str = 'all'  # all / failed


@dataclass(frozen=True)
class MergeTasksCommand(Command):
    """合并任务命令。

    将多个源任务的结果合并到一个新任务。
    参数由调用方提供源任务列表和合并后的任务配置。
    """
    source_task_ids: List[int]
    merged_task_name: str
    merged_task_type: str = 'api'
    description: str = ''
    created_by: Optional[int] = None
