# -*- coding: utf-8 -*-
"""evaluation_service 领域事件

领域事件表示领域中有意义的业务事件，由领域层发布，可被 application 层订阅
用于触发后续动作（如通知 task_service 更新状态、发 WebSocket 推送等）。

当前为骨架，事件发布机制待 P1.4 阶段接入 message broker / in-process event bus。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional


def _utc8now() -> datetime:
    return datetime.now(timezone(timedelta(hours=8)))


@dataclass
class EvaluationEvent:
    """领域事件基类"""
    occurred_at: datetime = field(default_factory=_utc8now)
    task_id: Optional[int] = None
    result_id: Optional[int] = None


@dataclass
class EvaluationCompleted(EvaluationEvent):
    """评估完成事件

    单个用例的所有维度评分完成后触发。
    """
    test_case_id: Optional[str] = None
    dimensions_count: int = 0
    passed_count: int = 0


@dataclass
class EvaluationFailed(EvaluationEvent):
    """评估失败事件"""
    test_case_id: Optional[str] = None
    dimension_id: Optional[int] = None
    error_message: str = ''


@dataclass
class DimensionScored(EvaluationEvent):
    """单维度评分完成事件"""
    dimension_id: int = 0
    score: Optional[float] = None
    status: Optional[str] = None  # passed / failed
    round_number: Optional[int] = None


@dataclass
class ReevaluationSubmitted(EvaluationEvent):
    """重新评估任务已提交事件"""
    reevaluate_type: str = 'all'
    reextract_device_output: bool = False


from evaluation_service.domain.events.evaluation_events import (
    CaseEvaluated,
    DimensionScored as EvaluationDimensionScored,
    ReevaluationSubmitted as EvaluationReevaluationSubmitted,
    ReevaluationCompleted,
    DimensionResultDeleted,
)

__all__ = [
    'EvaluationEvent',
    'EvaluationCompleted',
    'EvaluationFailed',
    'DimensionScored',
    'ReevaluationSubmitted',
    'CaseEvaluated',
    'EvaluationDimensionScored',
    'EvaluationReevaluationSubmitted',
    'ReevaluationCompleted',
    'DimensionResultDeleted',
]
