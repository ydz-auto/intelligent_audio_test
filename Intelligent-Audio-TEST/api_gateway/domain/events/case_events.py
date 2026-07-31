"""api_gateway 领域层 —— 领域事件"""
from dataclasses import dataclass, field
from typing import Optional, List, Any, Dict
from datetime import datetime


@dataclass
class DomainEvent:
    """领域事件基类"""
    occurred_at: datetime = field(default_factory=datetime.now)
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseCreated(DomainEvent):
    """测试用例创建事件"""
    case_id: str = ''


@dataclass
class CaseUpdated(DomainEvent):
    """测试用例更新事件"""
    case_id: str = ''


@dataclass
class ReportRequested(DomainEvent):
    """报告生成请求事件"""
    report_id: str = ''
    task_id: str = ''


@dataclass
class ReportCompleted(DomainEvent):
    """报告完成事件"""
    report_id: str = ''


class EventBus:
    """简单事件总线（进程内）"""
    def __init__(self):
        self._handlers: Dict[str, List] = {}

    def subscribe(self, event_type: str, handler):
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def publish(self, event_type: str, event):
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                pass


event_bus = EventBus()
