# -*- coding: utf-8 -*-
"""报告领域事件 (Domain Events)。

定义报告生命周期中的关键事件，供事件分发器消费。
事件本身是不可变的数据载体，不包含业务逻辑。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict


@dataclass(frozen=True)
class ReportEvent:
    """报告事件基类。"""
    report_id: int
    occurred_at: str = field(default_factory=lambda: datetime.now().isoformat())
    event_type: str = field(default='ReportEvent')

    def to_dict(self) -> Dict[str, Any]:
        return {
            'event_type': self.event_type,
            'report_id': self.report_id,
            'occurred_at': self.occurred_at,
        }


@dataclass(frozen=True)
class ReportGenerated(ReportEvent):
    """报告生成完成事件。"""
    report_type: str = 'standard'
    task_id: int = 0
    event_type: str = field(default='ReportGenerated', init=False)


@dataclass(frozen=True)
class ReportFailed(ReportEvent):
    """报告生成失败事件。"""
    reason: str = ''
    task_id: int = 0
    event_type: str = field(default='ReportFailed', init=False)


@dataclass(frozen=True)
class ReportDeleted(ReportEvent):
    """报告删除事件。"""
    event_type: str = field(default='ReportDeleted', init=False)
