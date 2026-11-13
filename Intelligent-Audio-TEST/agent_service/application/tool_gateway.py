# -*- coding: utf-8 -*-
"""只读 ToolGateway（INT-2453，方案 §6.1 / §6.3）。

意图工具（31 个注册项；M0 启用 4 个，M1 各域卡按域追加只读工具——
当前含 ``algorithm_query``）→ 目标 REST；逐调用校验：

1. 用户 / 租户：身份来自网关注入，回源请求带同一 Authorization；
2. 权限：intent 工具声明 permissions（OR 语义，``*`` 通配），不满足返回
   模型可读的普通拒绝文本，不抛内部异常、不泄漏资源是否存在；
3. 参数 Schema：必填 / 类型 / 枚举先校验，目标端点仍做 pydantic 二次校验；
4. 实时状态：目标 REST 的 403/404 统一收敛为「无权访问 / 资源不存在或无权访问」；
5. 预留工具（ui_tree / memory_* 等）返回 ``TOOL_NOT_ENABLED``；
6. 长尾 MCP 工具（tool_search 命中后直接调用）同样在此做权限与 Schema 校验。

审计（run_id / tool / args_hash / decision / latency / result_code）由
RunOrchestrator 统一写 ``agent_tool_call``：本网关只返回结构化
``ToolResult``，不重复落库。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Sequence

from agent_service.domain.enums import ToolRisk
from agent_service.domain.model.entities import ToolCallRequest, ToolResult
from agent_service.domain.ports.tool_gateway import (
    ToolDescriptor, ToolGateway, ToolInvocationContext,
)
from agent_service.domain.ports.tool_registry import (
    RunCredentialPort, ToolRegistryPort, ToolTransportPort,
)

logger = logging.getLogger(__name__)

PERMISSION_DENIED = 'PERMISSION_DENIED'
INVALID_ARGUMENTS = 'INVALID_ARGUMENTS'
TOOL_NOT_ENABLED = 'TOOL_NOT_ENABLED'
UNKNOWN_TOOL = 'UNKNOWN_TOOL'
RESOURCE_NOT_FOUND = 'NOT_FOUND'
UPSTREAM_ERROR = 'UPSTREAM_ERROR'
UPSTREAM_UNAVAILABLE = 'UPSTREAM_UNAVAILABLE'

# 不泄漏存在性的统一文案（403/404 同一口径）
_DENIED_TEXT = '无权访问该资源，或该资源不存在。'
_NOT_FOUND_TEXT = '资源不存在或无权访问。'


def _granted(granted: Sequence[str], required: Sequence[str]) -> bool:
    """权限 OR 语义；``*`` 通配；required 为空表示仅需登录。"""
    if not required:
        return True
    perms = set(granted or ())
    if '*' in perms:
        return True
    return bool(perms & set(required))


class SharedToolGateway(ToolGateway):
    """基于 ``shared/agent_tools`` 的只读工具网关。"""

    def __init__(self, *, bridge: ToolRegistryPort,
                 rest: ToolTransportPort,
                 credentials: RunCredentialPort):
        self._bridge = bridge
        self._rest = rest
        self._credentials = credentials

    # ------------------------------------------------------------ catalog

    def all_tools(self) -> Sequence[ToolDescriptor]:
        return self._bridge.descriptors()

    def describe(self, names: Sequence[str]) -> Sequence[ToolDescriptor]:
        wanted = set(names or ())
        return tuple(t for t in self.all_tools() if t.name in wanted)

    def risk_of(self, name: str) -> Optional[ToolRisk]:
        """工具风险（意图工具 + tool_search 命中的长尾 MCP 工具）。

        两份注册表都查不到返回 ``None``；绝不把未知工具降级成 READ —— 那会让
        写操作绕过 M0 只读门禁（INT-2487 / INT-2500）。
        """
        return self._bridge.risk_of(name)

    # ------------------------------------------------------------ execute

    def execute(self, call: ToolCallRequest,
                context: ToolInvocationContext) -> ToolResult:
        name = call.name
        arguments: Dict[str, Any] = call.arguments or {}
        descriptor = self._bridge.describe(name)
        required = self._bridge.permissions_of(name)
        if required is None:
            return self._fail(call, UNKNOWN_TOOL, f'工具不存在：{name}')

        if not _granted(context.permissions, required):
            return self._fail(call, PERMISSION_DENIED, _DENIED_TEXT)

        validation_error = self._bridge.validate(name, arguments)
        if validation_error:
            return self._fail(call, INVALID_ARGUMENTS, validation_error)

        # 预留工具：返回明确的「未启用」错误码（风险高低都一样）。
        if descriptor is not None and not descriptor.enabled:
            return self._fail(
                call, TOOL_NOT_ENABLED,
                f'工具 {name} 尚未启用（当前阶段为预留 Schema），请改用已启用工具。')

        # M0 只读：写 / 破坏性工具在网关层也拒绝（Loop 层已先行拦截，
        # 这里再做一次防御，避免绕过 Loop 直接调用时执行写操作）。
        # 两份注册表都查不到（None）按未知工具拒绝，不降级成 READ。
        risk = self.risk_of(name)
        if risk is None:
            return self._fail(call, UNKNOWN_TOOL, f'工具不存在：{name}')
        if risk is not ToolRisk.READ:
            return self._fail(
                call, 'APPROVAL_REQUIRED',
                '写操作需要审批，M0 未启用审批执行。')

        # 本地工具（不访问 REST）
        if name == 'tool_search':
            return self._run_tool_search(call, arguments, context)
        if name == 'platform_contract':
            return self._run_platform_contract(call, arguments)

        mcp_tool, merged, resolve_error = self._bridge.resolve_rest(
            name, arguments)
        if resolve_error or mcp_tool is None:
            return self._fail(call, INVALID_ARGUMENTS,
                              resolve_error or '工具映射不可用')
        return self._call_rest(call, mcp_tool, merged, context)

    # ------------------------------------------------------------ local

    def _run_tool_search(self, call: ToolCallRequest,
                         arguments: Dict[str, Any],
                         context: ToolInvocationContext) -> ToolResult:
        query = str(arguments.get('query') or '').strip()
        if not query:
            return self._fail(call, INVALID_ARGUMENTS, '缺少必填参数：query')
        try:
            limit = int(arguments.get('limit') or 10)
        except (TypeError, ValueError):
            limit = 10
        payload = self._bridge.search(query, context.permissions, limit)
        return self._ok(call, json.dumps(payload, ensure_ascii=False))

    def _run_platform_contract(self, call: ToolCallRequest,
                               arguments: Dict[str, Any]) -> ToolResult:
        payload = self._bridge.platform_contract(
            str(arguments.get('query') or '').strip(),
            str(arguments.get('section') or 'all').strip() or 'all')
        return self._ok(call, json.dumps(payload, ensure_ascii=False))

    # ------------------------------------------------------------ rest

    def _call_rest(self, call: ToolCallRequest, tool: dict,
                   arguments: Dict[str, Any],
                   context: ToolInvocationContext) -> ToolResult:
        authorization = self._credentials.get(context.run_id)
        result = self._rest.call(
            tool, arguments, authorization=authorization,
            user_id=context.owner_id, tenant_id=context.tenant_id,
            permissions=context.permissions)
        if result.status == 0:
            return self._fail(call, UPSTREAM_UNAVAILABLE,
                              f'目标服务不可用：{result.error}', ok=False)
        if result.status in (401, 403):
            return self._fail(call, PERMISSION_DENIED, _DENIED_TEXT)
        if result.status == 404:
            return self._fail(call, RESOURCE_NOT_FOUND, _NOT_FOUND_TEXT)
        if result.status == 422:
            return self._fail(call, INVALID_ARGUMENTS,
                              f'目标接口参数校验失败：{result.text}')
        if result.status >= 400:
            logger.warning('ToolGateway 回源 %s 失败 tool=%s target=%s',
                           result.status, call.name, tool['name'])
            return self._fail(call, UPSTREAM_ERROR,
                              f'目标接口返回 {result.status}：{result.text}')
        return self._ok(call, result.text)

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _ok(call: ToolCallRequest, content: str) -> ToolResult:
        return ToolResult(tool_call_id=call.tool_call_id, tool=call.name,
                          ok=True, content=content, error_code='OK')

    @staticmethod
    def _fail(call: ToolCallRequest, code: str, content: str,
              ok: bool = False) -> ToolResult:
        return ToolResult(tool_call_id=call.tool_call_id, tool=call.name,
                          ok=ok, content=content, error_code=code)


__all__ = [
    'INVALID_ARGUMENTS', 'PERMISSION_DENIED', 'RESOURCE_NOT_FOUND',
    'SharedToolGateway', 'TOOL_NOT_ENABLED', 'UNKNOWN_TOOL', 'UPSTREAM_ERROR',
    'UPSTREAM_UNAVAILABLE',
]
