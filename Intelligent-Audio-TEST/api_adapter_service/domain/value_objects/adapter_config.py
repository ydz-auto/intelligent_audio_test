# -*- coding: utf-8 -*-
"""API 适配配置值对象

说明：本模块的 VendorConfig 与同包 ``__init__`` 内已有的
``VendorConfig``（frozen，被 ``domain/services/AdapterSelector`` 使用）
并存。本模块面向 HTTP API 适配场景，字段更贴合外部请求
（api_key/base_url/model/temperature/max_tokens）。
如需纯领域层选择适配器，请继续使用 ``domain.value_objects.VendorConfig``。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class VendorConfig:
    """供应商配置值对象"""
    vendor: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    extra_params: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> Optional["VendorConfig"]:
        if not data:
            return None
        return cls(
            vendor=data.get('vendor', ''),
            api_key=data.get('api_key'),
            base_url=data.get('base_url'),
            model=data.get('model'),
            temperature=data.get('temperature', 0.7),
            max_tokens=data.get('max_tokens', 4096),
            extra_params=data.get('extra_params', {}),
        )


@dataclass
class DialogContext:
    """对话上下文值对象"""
    session_id: str
    turn_count: int = 0
    max_turns: int = 10
    system_prompt: Optional[str] = None
    history: List[Dict[str, str]] = field(default_factory=list)
