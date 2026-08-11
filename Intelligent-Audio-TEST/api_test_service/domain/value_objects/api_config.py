# -*- coding: utf-8 -*-
"""APIConfig 值对象 — 不可变，描述被测 API 的全局默认配置，纯逻辑，无 IO 依赖。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass(frozen=True)
class APIConfig:
    """API 配置值对象 — 描述被测 API 的全局默认配置。

    包括基础 URL、默认请求头、默认超时与可选的重试策略。
    """

    base_url: str = ""
    default_headers: Dict[str, str] = field(default_factory=dict)
    default_timeout: int = 30
    retry_config: Optional[Dict] = None
