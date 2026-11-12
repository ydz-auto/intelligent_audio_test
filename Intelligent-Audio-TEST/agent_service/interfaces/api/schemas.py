# -*- coding: utf-8 -*-
"""接口层请求 / 响应模型。

camelCase 只在前端 infrastructure 层转换；服务端对外保持与现有网关一致的
snake_case 契约（方案 §11）。
"""
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    title: str = ''
    active_skill: Optional[str] = None
    model: str = ''


class CreateRunRequest(BaseModel):
    message: str = Field(min_length=1)
    budget: Optional[Dict[str, Any]] = None


class SessionResponse(BaseModel):
    id: str
    owner_id: int
    tenant_id: str
    title: str
    active_skill: Optional[str] = None
    model: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class RunResponse(BaseModel):
    id: str
    session_id: str
    owner_id: int
    tenant_id: str
    status: str
    model: str
    budget: Dict[str, Any] = Field(default_factory=dict)
    token_in: int = 0
    token_out: int = 0
    error: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class CreateRunResponse(BaseModel):
    run: RunResponse
    created: bool


class SessionDetailResponse(BaseModel):
    session: SessionResponse
    messages: list = Field(default_factory=list)
    runs: list = Field(default_factory=list)
