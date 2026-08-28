# -*- coding: utf-8 -*-
"""任务配置值对象（封装 task.config JSON 字段）"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from shared.models.common_enums import TestType


@dataclass(frozen=True)
class TaskId:
    """任务 ID 值对象。"""
    value: int

    def __post_init__(self):
        if self.value is None or self.value < 0:
            raise ValueError(f"TaskId 必须为非负整数，得到: {self.value}")

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True)
class TaskProgress:
    """任务进度值对象。"""
    total_cases: int = 0
    completed_cases: int = 0
    failed_cases: int = 0

    @property
    def processed_cases(self) -> int:
        """已处理用例数（完成 + 失败）。"""
        return self.completed_cases + self.failed_cases

    @property
    def percent(self) -> float:
        """进度百分比。"""
        if self.total_cases <= 0:
            return 0.0
        return round(self.processed_cases / self.total_cases * 100, 2)

    @property
    def is_complete(self) -> bool:
        """是否全部处理完毕。"""
        return self.total_cases > 0 and self.processed_cases >= self.total_cases

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_cases': self.total_cases,
            'completed_cases': self.completed_cases,
            'failed_cases': self.failed_cases,
            'processed_cases': self.processed_cases,
            'percent': self.percent,
        }


@dataclass(frozen=True)
class TaskConfig:
    """任务配置值对象（封装 task.config JSON 字段）。"""
    task_type: str = TestType.API.value
    algorithm_type: Optional[str] = None
    algorithm_params: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'TaskConfig':
        """从字典构造（容忍 None）。"""
        if not data:
            return cls()
        return cls(
            task_type=data.get('type', TestType.API.value),
            algorithm_type=data.get('algorithm_type'),
            algorithm_params=data.get('algorithm_params', {}) or {},
            extra={k: v for k, v in data.items()
                   if k not in ('type', 'algorithm_type', 'algorithm_params')},
        )

    def to_dict(self) -> Dict[str, Any]:
        result = dict(self.extra)
        result['type'] = self.task_type
        if self.algorithm_type:
            result['algorithm_type'] = self.algorithm_type
        if self.algorithm_params:
            result['algorithm_params'] = self.algorithm_params
        return result
