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
    # 预算只由服务端配置（agent_defaults.json + AGENT_MAX_* 环境变量）给定，
    # 请求体不接受覆盖：任何调用方都不能把 token / 时长 / 轮次 / 输出字节
    # 的上限关掉。未知字段按 pydantic 默认忽略，不报错、也不生效。
    message: str = Field(min_length=1)
    # 可选：发起本轮时切换会话激活的 Skill（落库 agent_session.active_skill）
    active_skill: Optional[str] = None


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


class SkillResponse(BaseModel):
    """当前用户可见的 Skill（§11 GET /api/v1/agent/skills）。"""

    name: str
    description: str
    version: str = ''
    owner: str = ''
    allowed_tools: list = Field(default_factory=list)
    permissions: list = Field(default_factory=list)
    budgets: Dict[str, Any] = Field(default_factory=dict)


class SkillListResponse(BaseModel):
    items: list = Field(default_factory=list)
    # L1 常驻预算量级（§8.3 system 区段 15%），供前端与审计核对
    l1_tokens: int = 0
    l1_budget_tokens: int = 0
