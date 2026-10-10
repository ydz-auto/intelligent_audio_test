# -*- coding: utf-8 -*-
"""API 聚合根实体 — 描述被测 API 配置的聚合根、枚举与快照，纯逻辑，无 IO 依赖。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from shared.models.common_enums import OutputType


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


def normalize_output_types(raw) -> List[str]:
    """output_types 归一化（OutputType 枚举消费，INT-74）

    去重 + 剔除非法值，按 OutputType 枚举定义序输出，保证落库与读侧口径一致。
    """
    if not isinstance(raw, (list, tuple, set)):
        return []
    present = {str(v) for v in raw}
    return [item.value for item in OutputType if item.value in present]


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
    # API 输出类型列表（OutputType 枚举值子集，多模态输出采集口径，INT-74）
    output_types: List[str] = field(default_factory=list)
    # 被测设备类型（DeviceType 枚举值，决定执行路由，UC-0901）
    device_type: str = "http_api"
    # 指定适配器类名（未指定时按 protocol+vendor 自动匹配，UC-0901）
    adapter_class: Optional[str] = None
    # 目标音频格式声明 {"sample_rate","bit_depth","channels","container"}，未配置回退默认（UC-0901）
    audio_config: Optional[Dict] = None

    def set_output_types(self, raw) -> List[str]:
        """设置输出类型列表（经 OutputType 枚举归一化），返回归一化结果"""
        self.output_types = normalize_output_types(raw)
        return self.output_types

    def set_audio_config(self, raw) -> Optional[Dict]:
        """设置目标音频格式（仅保留已知键），返回规整后的 dict"""
        if raw is None:
            self.audio_config = None
            return None
        if not isinstance(raw, dict):
            raise ValueError("audio_config 必须是 JSON 对象")
        allowed = ('sample_rate', 'bit_depth', 'channels', 'container', 'format', 'chunk_duration_ms')
        self.audio_config = {k: raw[k] for k in allowed if k in raw}
        return self.audio_config

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
