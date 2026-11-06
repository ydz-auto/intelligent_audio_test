# -*- coding: utf-8 -*-
"""算法领域事件。

归属：algorithm_service.domain.events

说明：
- 本模块为纯领域层 dataclass，不依赖 SQLAlchemy / db.Model。
- AlgorithmEvent 为领域事件基类，记录 definition_id 与发生时间。
- 子类：AlgorithmCreated / AlgorithmUpdated / AlgorithmDeprecated。
- 领域事件用于在聚合状态变更后通知下游（如发消息、写日志、触发流程）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class AlgorithmEvent:
    """算法领域事件基类。

    - definition_id: 关联的算法定义ID
    - occurred_at: 事件发生时间
    """

    definition_id: int
    occurred_at: datetime = field(default_factory=datetime.now)


@dataclass
class AlgorithmCreated(AlgorithmEvent):
    """算法定义创建事件。

    - name: 算法名称
    - algorithm_type: 算法类型代码
    """

    name: str = ""
    algorithm_type: str = ""


@dataclass
class AlgorithmUpdated(AlgorithmEvent):
    """算法定义更新事件。

    - changes: 变更字段键值对
    """

    changes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AlgorithmDeprecated(AlgorithmEvent):
    """算法定义废弃事件。

    - reason: 废弃原因
    """

    reason: Optional[str] = None
