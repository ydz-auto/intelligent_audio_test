# -*- coding: utf-8 -*-
"""领域事件 (Domain Events)。

定义任务生命周期中的关键事件，供事件分发器消费。
事件本身是不可变的数据载体，不包含业务逻辑。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional  # noqa: F401


@dataclass(frozen=True)
class TaskEvent:
    """任务事件基类。"""
    task_id: int
    occurred_at: str = field(default_factory=lambda: datetime.now().isoformat())
    event_type: str = field(default='TaskEvent')

    def to_dict(self) -> Dict[str, Any]:
        return {
            'event_type': self.event_type,
            'task_id': self.task_id,
            'occurred_at': self.occurred_at,
        }


@dataclass(frozen=True)
class TaskCreated(TaskEvent):
    """任务创建事件。"""
    task_name: str = ''
    task_type: str = 'api'
    total_cases: int = 0
    created_by: Optional[int] = None
    event_type: str = field(default='TaskCreated', init=False)


@dataclass(frozen=True)
class TaskStarted(TaskEvent):
    """任务启动事件。"""
    task_type: str = 'api'
    event_type: str = field(default='TaskStarted', init=False)


@dataclass(frozen=True)
class TaskCompleted(TaskEvent):
    """任务完成事件。"""
    completed_cases: int = 0
    failed_cases: int = 0
    actual_duration: Optional[int] = None
    event_type: str = field(default='TaskCompleted', init=False)


@dataclass(frozen=True)
class TaskFailed(TaskEvent):
    """任务失败事件。"""
    reason: str = ''
    event_type: str = field(default='TaskFailed', init=False)


@dataclass(frozen=True)
class TaskStopped(TaskEvent):
    """任务停止事件。"""
    event_type: str = field(default='TaskStopped', init=False)
