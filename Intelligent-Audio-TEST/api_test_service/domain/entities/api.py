# -*- coding: utf-8 -*-
"""API 聚合根实体 — 描述被测 API 配置的聚合根、枚举与快照，纯逻辑，无 IO 依赖。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class HTTPMethod(str, Enum):
    """HTTP 请求方法枚举"""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class APIStatus(str, Enum):
    """API 状态枚举"""

    active = "active"
    inactive = "inactive"
    deleted = "deleted"


@dataclass(frozen=True)
class APISnapshot:
    """API 快照值对象 — 不可变，记录某一时刻 API 的核心信息。"""

    id: int
    name: str
    url: str
    method: HTTPMethod = HTTPMethod.GET


@dataclass
class APIAggregate:
    """API 聚合根 — 被测 API 配置的聚合根实体。

    聚合 API 的标识、请求定义（URL/方法/请求头/请求体）、
    超时与重试策略以及状态。所有对 API 的变更通过聚合根进行。
    """

    id: int
    name: str
    url: str
    method: HTTPMethod = HTTPMethod.GET
    headers: Dict[str, str] = field(default_factory=dict)
    body_template: Optional[str] = None
    timeout_seconds: int = 30
    retry_count: int = 0
    status: str = "active"
    deleted: bool = False

    def activate(self) -> None:
        """激活 API"""
        self.status = APIStatus.active.value
        self.deleted = False

    def deactivate(self) -> None:
        """停用 API"""
        self.status = APIStatus.inactive.value

    def is_active(self) -> bool:
        """判断 API 是否处于激活态"""
        return self.status == APIStatus.active.value and not self.deleted

    def update_url(self, new_url: str) -> None:
        """更新 API 的 URL"""
        self.url = new_url

    def update_headers(self, new_headers: Dict[str, str]) -> None:
        """更新 API 的请求头"""
        self.headers = dict(new_headers)
