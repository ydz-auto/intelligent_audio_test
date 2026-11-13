# -*- coding: utf-8 -*-
"""工具层基础设施适配器（INT-2453）。

- ``RunCredentialRegistry``：按 run 暂存调用方 Authorization（网关转发而来），
  供 ToolGateway 以用户身份回源 REST；只放内存、不落库、不进事件。
- ``RestToolClient``：按共享注册表的 method/path/query/body 构造规则调用网关
  REST（与外部 MCP tools/call 同一套构造，不复制 Schema）。
- ``SharedToolRegistryBridge``：把 ``shared/agent_tools`` 适配为 domain 端口
  （意图工具描述 / 风险 / Schema 校验 / tool_search / platform_contract）。

分层：application 只依赖 ``domain/ports/tool_registry.py`` 的抽象，本模块
在组合根注入。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional, Sequence, Tuple

import httpx

from agent_service.domain.enums import SandboxTier, ToolRisk
from agent_service.domain.ports.tool_gateway import ToolDescriptor
from agent_service.domain.ports.tool_registry import (
    RunCredentialPort, ToolRegistryPort, ToolTransportPort, ToolTransportResult,
)
from shared.agent_tools import diagnostics, evaluation_tools, intent_tools, mcp_registry

logger = logging.getLogger(__name__)

# 凭证缓存默认 TTL：只在 run 执行窗口内需要
_CREDENTIAL_TTL_SECONDS = 3600

# 兼容别名（测试与旧调用方使用 RestResult）
RestResult = ToolTransportResult


class RunCredentialRegistry(RunCredentialPort):
    """run_id → Authorization 头 的进程内暂存（线程安全）。"""

    def __init__(self, ttl_seconds: int = _CREDENTIAL_TTL_SECONDS):
        self._ttl = int(ttl_seconds)
        self._lock = threading.Lock()
        self._store: Dict[str, Tuple[str, float]] = {}

    def put(self, run_id: str, authorization: Optional[str]) -> None:
        if not run_id or not authorization:
            return
        with self._lock:
            self._store[run_id] = (authorization, time.time() + self._ttl)

    def get(self, run_id: str) -> Optional[str]:
        with self._lock:
            item = self._store.get(run_id)
            if item is None:
                return None
            authorization, expires_at = item
            if expires_at < time.time():
                self._store.pop(run_id, None)
                return None
            return authorization

    def clear(self, run_id: str) -> None:
        with self._lock:
            self._store.pop(run_id, None)


class RestToolClient(ToolTransportPort):
    """把注册表工具定义发成网关 REST 请求。"""

    def __init__(self, base_url: str, *, timeout_seconds: float = 30.0):
        self._base = (base_url or '').rstrip('/')
        self._timeout = float(timeout_seconds)

    def call(self, tool: dict, arguments: Dict[str, Any], *,
             authorization: Optional[str] = None,
             user_id: int = 0, tenant_id: str = '',
             permissions: Sequence[str] = ()) -> ToolTransportResult:
        path = mcp_registry.build_path(tool, arguments)
        body = mcp_registry.build_body(tool, arguments)
        url = f'{self._base}{path}'
        headers = {}
        if authorization:
            headers['Authorization'] = authorization
        if user_id:
            headers['X-User-Id'] = str(user_id)
        if tenant_id:
            headers['X-Tenant-Id'] = tenant_id
        if permissions:
            headers['X-User-Permissions'] = ','.join(permissions)
        try:
            response = httpx.request(tool['method'], url, json=body,
                                     headers=headers, timeout=self._timeout)
        except httpx.HTTPError as exc:
            logger.warning('ToolGateway 回源失败 tool=%s url=%s: %s',
                           tool['name'], url, exc)
            return ToolTransportResult(status=0, error=f'目标服务不可用: {exc}')
        try:
            payload = response.json()
            text = _json_dumps(payload)
        except ValueError:
            payload = None
            text = (response.text or '')[:2000]
        return ToolTransportResult(status=response.status_code, payload=payload,
                                   text=text)


def _json_dumps(payload: Any) -> str:
    import json
    from datetime import date, datetime
    from decimal import Decimal

    def default(obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        return str(obj)

    return json.dumps(payload, ensure_ascii=False, default=default)


class SharedToolRegistryBridge(ToolRegistryPort):
    """共享工具注册表适配层（agent_service 视角）。"""

    def descriptors(self) -> Tuple[ToolDescriptor, ...]:
        return tuple(
            ToolDescriptor(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
                risk=ToolRisk(tool.risk),
                sandbox_tier=SandboxTier.T0_NONE,
                permissions=tuple(tool.permissions),
                enabled=tool.enabled,
            )
            for tool in intent_tools.INTENT_TOOLS
        )

    def describe(self, name: str) -> Optional[ToolDescriptor]:
        tool = intent_tools.INTENT_TOOL_BY_NAME.get(name)
        if tool is None:
            return None
        return ToolDescriptor(
            name=tool.name, description=tool.description,
            parameters=tool.parameters, risk=ToolRisk(tool.risk),
            sandbox_tier=SandboxTier.T0_NONE,
            permissions=tuple(tool.permissions), enabled=tool.enabled)

    def permissions_of(self, name: str) -> Optional[Tuple[str, ...]]:
        tool = intent_tools.INTENT_TOOL_BY_NAME.get(name)
        if tool is not None:
            return tuple(tool.permissions)
        # 宿主语境专用工具（如 audio_get_by_ids，INT-2530）不在 Agent 通道：
        # 返回 None 让网关按「工具不存在」fail-closed，不回源。
        if name in intent_tools.AGENT_UNEXPOSED_MCP_TOOLS:
            return None
        mcp = mcp_registry.get_tool(name)
        if mcp is None:
            return None
        return tuple(mcp['permissions'])

    def permissions_for(self, name: str,
                        arguments: Optional[Dict[str, Any]] = None
                        ) -> Optional[Tuple[str, ...]]:
        """按 action 收窄的权限（``device_query`` 跨 device / spl / digital_spl）。"""
        return intent_tools.permissions_for(name, arguments)

    def is_mcp_tool(self, name: str) -> bool:
        return mcp_registry.get_tool(name) is not None

    def risk_of(self, name: str) -> Optional[ToolRisk]:
        value = intent_tools.risk_of(name)
        return ToolRisk(value) if value else None

    def risk_for(self, name: str,
                 arguments: Optional[Dict[str, Any]] = None
                 ) -> Optional[ToolRisk]:
        """动作级风险（写意图工具的删除类动作 → DESTRUCTIVE）。"""
        value = intent_tools.risk_for(name, arguments)
        return ToolRisk(value) if value else None

    def validate(self, name: str, arguments: Any) -> Optional[str]:
        """意图工具用自身 Schema；长尾 MCP 工具用共享 MCP Schema。

        ``report_compare`` 是本地组合工具（INT-2463）：除 Schema 外还要校验
        跨参数规则（报告 ID 数量 / 正负 / 去重、trend 动作只收趋势参数），
        否则会把「1 个报告」「负数 ID」这类调用当成合法对比发给模型。
        """
        tool = intent_tools.INTENT_TOOL_BY_NAME.get(name)
        if tool is not None:
            schema_error = intent_tools.validate_arguments(
                tool.parameters, arguments)
            if schema_error:
                return schema_error
            if name in intent_tools.WRITE_ACTION_TOOL_NAMES:
                # 写工具（INT-2467）：动作白名单 / 跨字段规则与执行期同源，
                # 提案阶段就拦下注定 422 的调用。
                return intent_tools.validate_write_arguments(name, arguments)
            if name == 'report_compare':
                return intent_tools.validate_report_compare(
                    str((arguments or {}).get('action') or ''), arguments or {})
            if name == 'evaluation_manage':
                # 动作级必填 / body 字段白名单 / 可见性与重评估取值：Schema
                # 表达不了，留到执行期才发现会让审批人批一条注定失败的提案。
                return evaluation_tools.validate_arguments(arguments or {})
            if name in intent_tools.WRITE_RESOLVERS:
                # 写意图工具的动作级校验（必填 / 参数白名单 / body 注入）：
                # 提案前就要拦下不可能执行成功的请求，不能等审批通过后才发现。
                _, _, resolve_error = intent_tools.resolve_rest_call(
                    name, dict(arguments or {}))
                return resolve_error
            return None
        mcp = mcp_registry.get_tool(name)
        if mcp is None:
            return f'未知工具：{name}'
        return intent_tools.validate_arguments(mcp['inputSchema'], arguments)

    def resolve_rest(self, name: str, arguments: Dict[str, Any]):
        return intent_tools.resolve_rest_call(name, arguments)

    def search(self, query: str, permissions: Sequence[str],
               limit: int) -> dict:
        return intent_tools.tool_search(query, tuple(permissions), limit=limit)

    def platform_contract(self, query: str, section: str) -> dict:
        return intent_tools.platform_contract(query, section)

    def diagnosis_log_levels(self) -> Tuple[str, ...]:
        return tuple(diagnostics.DIAGNOSIS_LOG_LEVELS)

    def diagnosis_sample_limit(self) -> int:
        return int(diagnostics.DEFAULT_LOG_ROWS)

    def action_arguments(self, name: str, action: str
                         ) -> Optional[Tuple[str, ...]]:
        return intent_tools.action_params(name, action)

    def log_diagnose_stats_unsupported(self) -> Tuple[str, ...]:
        return tuple(intent_tools.LOG_DIAGNOSE_STATS_UNSUPPORTED_PARAMS)

    def diagnose_task(self, sources: Dict[str, Any]) -> Dict[str, Any]:
        return diagnostics.build_task_diagnosis(**sources)

    def diagnose_logs(self, sources: Dict[str, Any]) -> Dict[str, Any]:
        return diagnostics.build_log_diagnosis(**sources)

    def index_size(self) -> int:
        return len(intent_tools.TOOL_INDEX)


__all__ = [
    'RestResult', 'RestToolClient', 'RunCredentialRegistry',
    'SharedToolRegistryBridge',
]
