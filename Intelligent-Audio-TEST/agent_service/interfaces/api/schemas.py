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


class SkillIssueResponse(BaseModel):
    """一条装载问题（目录级失败 / frontmatter 校验），供看板与审计消费。"""

    code: str
    severity: str
    skill: str = ''
    path: str = ''
    message: str = ''


class SkillListResponse(BaseModel):
    items: list = Field(default_factory=list)
    # 装载总数（权限过滤前的 registry 结果）与问题摘要（INT-2506）
    skills_count: int = 0
    issues: list = Field(default_factory=list)
    issues_count: int = 0
    # L1 常驻预算量级（§8.3 system 区段 15%），供前端与审计核对
    l1_tokens: int = 0
    l1_budget_tokens: int = 0


# ---------------------------------------------------------------- providers

class CreateProviderRequest(BaseModel):
    name: str = ''
    protocol: str = 'OPENAI_COMPATIBLE'
    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    context_window: Optional[int] = None


class UpdateProviderRequest(BaseModel):
    """PUT 语义：未出现的字段不变；api_key 留空 / 不传表示不变。"""

    name: Optional[str] = None
    protocol: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    context_window: Optional[int] = None


class ProviderResponse(BaseModel):
    id: str
    owner_id: int
    tenant_id: str
    name: str
    protocol: str
    base_url: str
    model: str
    api_key_mask: str
    context_window: Optional[int] = None
    context_window_source: str
    effective_context_window: int
    catalog_context_window: Optional[int] = None
    catalog_max_output_tokens: Optional[int] = None
    context_window_warning: Optional[str] = None
    context_window_warning_message: Optional[str] = None
    is_default: bool = False
    status: str
    last_verified_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProviderListResponse(BaseModel):
    items: list = Field(default_factory=list)


class VerifyProviderResponse(BaseModel):
    provider_id: str
    ok: bool
    code: str
    message: str = ''
    status: str
    last_verified_at: Optional[str] = None
