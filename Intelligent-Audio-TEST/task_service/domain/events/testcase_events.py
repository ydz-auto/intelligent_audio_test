# -*- coding: utf-8 -*-
"""TestCase 领域事件"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional  # noqa: F401


@dataclass
class TestCaseCreated:
    """用例创建事件"""
    case_id: str
    name: str
    algorithm_type: str


@dataclass
class TestCaseUpdated:
    """用例更新事件"""
    case_id: str
    updated_fields: list = field(default_factory=list)


@dataclass
class TestCaseDeleted:
    """用例删除事件"""
    case_id: str


@dataclass(frozen=True)
class TestCaseBatchAction:
    """用例批量操作领域事件（CASE_EVENTS 通道）。

    batch_action 调度成功后发布：
    - status='completed'：同步动作已提交并落库
    - status='submitted'：超阈值异步任务已提交（如 refresh_reference > 50 条），
      任务终态由 ReferenceRefreshTask 完成时再补发 completed/failed 事件
    to_dict() 输出即 EventBus 发布 payload，字段与事件契约一一对应。
    """
    action: str
    case_ids: List[str] = field(default_factory=list)
    success_count: int = 0
    message: str = ''
    idempotency_key: str = ''
    status: str = 'completed'  # completed / submitted / failed
    async_task_id: str = ''
    occurred_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'action': self.action,
            'ids': list(self.case_ids),
            'success_count': self.success_count,
            'message': self.message,
            'idempotency_key': self.idempotency_key,
            'status': self.status,
            'async_task_id': self.async_task_id,
            'occurred_at': self.occurred_at,
        }
