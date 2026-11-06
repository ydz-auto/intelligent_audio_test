# -*- coding: utf-8 -*-
"""系统选项请求/响应 schema（INT-620）。

对位 newAPI `/api/option/` PUT 单键契约 `{ key, value }`。
"""
from __future__ import annotations

from typing import List, Union

from pydantic import Field

from api_gateway.schemas.base import APIModel

# 选项值类型（与前端 domain/models/option.ts SystemOptionValue 对齐）
SystemOptionValue = Union[str, int, float, bool, List[str]]


class SystemOptionUpdateRequest(APIModel):
    """PUT /api/option/ 请求体：单键写入。"""

    key: str = Field(..., min_length=1, max_length=255, description='选项键（域.分区.字段）')
    value: SystemOptionValue = Field(..., description='选项值（string/number/boolean/string[]）')
