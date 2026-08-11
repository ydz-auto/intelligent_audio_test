# -*- coding: utf-8 -*-
"""API 领域事件 — 描述 API 生命周期中的业务事件，纯数据载体。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class APIEvent:
    """API 事件基类 — 所有 API 事件的公共字段。"""

    api_id: int
    occurred_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class APICreated(APIEvent):
    """API 创建事件 — 在新建 API 时发布。"""

    name: str = ""
    url: str = ""
    method: str = "GET"


@dataclass(frozen=True)
class APIUpdated(APIEvent):
    """API 更新事件 — 在 API 字段变更时发布。"""

    changed_fields: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class APIDeleted(APIEvent):
    """API 删除事件 — 在 API 被删除时发布。"""
