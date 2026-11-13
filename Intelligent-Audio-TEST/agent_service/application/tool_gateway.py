# -*- coding: utf-8 -*-
"""只读 ToolGateway（INT-2453，方案 §6.1 / §6.3；INT-2461 扩诊断聚合）。

意图工具（31 个注册项；M0 启用 4 个，M1 各域卡按域追加只读工具——
当前含 ``task_query`` / ``task_diagnose`` / ``log_diagnose`` /
``dashboard_query``）→ 目标 REST；逐调用校验：

1. 用户 / 租户：身份来自网关注入，回源请求带同一 Authorization；
2. 权限：intent 工具声明 permissions（OR 语义，``*`` 通配），不满足返回
   模型可读的普通拒绝文本，不抛内部异常、不泄漏资源是否存在；
3. 参数 Schema：必填 / 类型 / 枚举 / 上下界先校验，目标端点仍做 pydantic
   二次校验；动作级参数白名单拦下「传了但不会生效」的组合；
4. 实时状态：目标 REST 的 403/404 统一收敛为「无权访问 / 资源不存在或无权访问」；
5. 预留工具（ui_tree / memory_* 等）返回 ``TOOL_NOT_ENABLED``；
6. 长尾 MCP 工具（tool_search 命中后直接调用）同样在此做权限与 Schema 校验；
7. 本地只读聚合（``task_diagnose`` / ``log_diagnose`` 的 diagnose 动作）：
   用同一份 MCP 定义组合多个只读接口，纯函数汇总在
   ``shared/agent_tools/diagnostics.py``；子接口失败按「降级 + 说明」处理，
   不静默忽略、不编造数值。

审计（run_id / tool / args_hash / decision / latency / result_code）由
RunOrchestrator 统一写 ``agent_tool_call``：本网关只返回结构化
``ToolResult``，不重复落库。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Sequence, Tuple

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

# 本地只读聚合工具名（INT-2461）
TASK_DIAGNOSE = 'task_diagnose'
LOG_DIAGNOSE = 'log_diagnose'
LOG_DIAGNOSE_ACTION = 'diagnose'
# log:read 是诊断拉日志的必需权限（task_diagnose 声明 OR，缺该码时降级）
LOG_READ_PERMISSION = 'log:read'

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
        # 本地只读聚合（INT-2461）：组合多个只读接口，纯函数汇总
        if name == TASK_DIAGNOSE:
            return self._run_task_diagnose(call, arguments, context)
        if name == LOG_DIAGNOSE and \
                arguments.get('action') == LOG_DIAGNOSE_ACTION:
            return self._run_log_diagnose(call, arguments, context)

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

    # ------------------------------------------------------------ diagnose

    def _run_task_diagnose(self, call: ToolCallRequest,
                           arguments: Dict[str, Any],
                           context: ToolInvocationContext) -> ToolResult:
        """任务失败诊断：任务详情 + 进度 + 统计 + 错误日志 → 带来源 ID 的聚合。

        - 任务详情是主来源，取不到直接失败（不返回半份诊断）；
        - 进度 / 统计 / 日志子接口失败按「降级 + 说明」处理（notes 写明），
          不静默当成「没有失败」；
        - 缺少 ``log:read`` 时跳过日志，明确写进 notes；
        - 归属校验不在这里重做：task_id / case_id 的租户与行级可见性由回源接口
          按同一份用户 Authorization 判定，403/404 统一收敛（不做本地两套口径）。
        """
        task_id = arguments.get('task_id')
        if task_id is None:
            return self._fail(call, INVALID_ARGUMENTS, '缺少必填参数：task_id')
        case_id = arguments.get('case_id')
        keyword = arguments.get('keyword')

        detail, error, status = self._fetch('task_get',
                                            {'task_id': task_id}, context)
        if error:
            return self._fail(call, self._code_for_status(status), error)

        progress, progress_error, _ = self._fetch(
            'task_get_progress', {'task_id': task_id}, context)
        stats, stats_error, _ = self._fetch(
            'task_get_stats', {'task_id': task_id}, context)

        log_filter: Dict[str, Any] = {
            'task_id': task_id,
            'level': ','.join(self._bridge.diagnosis_log_levels()),
        }
        if case_id:
            log_filter['test_case_id'] = case_id
        if keyword:
            log_filter['keyword'] = keyword

        logs_available = True
        log_denied = False
        log_error = None
        log_items = None
        log_total = None
        if _granted(context.permissions, (LOG_READ_PERMISSION,)):
            log_filter['per_page'] = self._bridge.diagnosis_sample_limit()
            log_data, log_error, _ = self._fetch(
                'log_list', dict(log_filter), context)
            if log_error:
                logs_available = False
            else:
                log_data = log_data or {}
                log_items = log_data.get('items') or []
                log_total = log_data.get('total')
        else:
            logs_available = False
            log_denied = True

        payload = self._bridge.diagnose_task({
            'task_id': task_id,
            'detail': detail,
            'progress': progress,
            'stats': stats,
            'log_items': log_items,
            'log_total': log_total,
            'case_id': case_id,
            'keyword': keyword,
            'logs_available': logs_available,
            'log_denied': log_denied,
            'log_error': log_error,
            'progress_error': progress_error,
            'stats_error': stats_error,
            'log_filter': log_filter,
        })
        return self._ok(call, json.dumps(payload, ensure_ascii=False))

    def _run_log_diagnose(self, call: ToolCallRequest,
                          arguments: Dict[str, Any],
                          context: ToolInvocationContext) -> ToolResult:
        """日志诊断：级别统计（接口原值）+ 指定级别样本按来源聚合。"""
        allowed = self._bridge.action_arguments(LOG_DIAGNOSE,
                                                LOG_DIAGNOSE_ACTION)
        if allowed is not None:
            unknown = sorted(key for key in arguments
                             if key not in allowed and key != 'action')
            if unknown:
                return self._fail(
                    call, INVALID_ARGUMENTS,
                    f'action={LOG_DIAGNOSE_ACTION} 不支持参数：'
                    f'{"、".join(unknown)}（网关会静默忽略这些参数）')

        raw_level = str(arguments.get('level') or '').strip().lower()
        if raw_level:
            levels: Sequence[str] = tuple(
                level.strip() for level in raw_level.split(',')
                if level.strip())
        else:
            levels = self._bridge.diagnosis_log_levels()
        limit = arguments.get('max_rows') or self._bridge.diagnosis_sample_limit()

        # 级别统计不带 level：保留完整 breakdown 才能判断样本覆盖率；
        # 样本按实际取样级别过滤。
        # ``/api/v1/logs/stats`` 没有 test_case_id（LogStatsQuery，INT-2461 P2）：
        # 该参数只作用于样本取样，进了 stats_filters 会让统计被误标成按用例
        # 口径；剔除后由 diagnostics 在 notes 里写明真实口径。
        base_filters = {key: value for key, value in arguments.items()
                        if key not in ('action', 'max_rows', 'level')}
        stats_unsupported_params = (
            self._bridge.log_diagnose_stats_unsupported())
        stats_unsupported = [
            key for key in stats_unsupported_params
            if base_filters.get(key) not in (None, '')]
        stats_filters = {key: value for key, value in base_filters.items()
                         if key not in stats_unsupported_params}
        list_filters = dict(base_filters, level=','.join(levels),
                            page=1, per_page=limit)

        stats, stats_error, stats_status = self._fetch(
            'log_stats', dict(stats_filters), context)
        data, list_error, list_status = self._fetch(
            'log_list', dict(list_filters), context)
        if stats_error and list_error:
            return self._fail(
                call, self._code_for_status(list_status or stats_status),
                f'日志诊断数据不可用：{stats_error}；{list_error}')

        items = None
        total = None
        if not list_error:
            data = data or {}
            items = data.get('items') or []
            total = data.get('total')

        payload = self._bridge.diagnose_logs({
            'stats_filters': stats_filters,
            'list_filters': list_filters,
            'stats_unsupported': stats_unsupported,
            'levels': levels,
            'stats': stats,
            'items': items,
            'total': total,
            'max_rows': limit,
            'stats_error': stats_error,
            'list_error': list_error,
        })
        return self._ok(call, json.dumps(payload, ensure_ascii=False))

    # ------------------------------------------------------------ rest

    def _fetch(self, name: str, arguments: Dict[str, Any],
               context: ToolInvocationContext
               ) -> Tuple[Optional[Any], Optional[str], int]:
        """按 MCP 定义发一次只读 REST，返回 ``(data, 错误文本, HTTP 状态)``。"""
        tool, merged, error = self._bridge.resolve_rest(name, arguments)
        if error or tool is None:
            return None, error or f'工具映射失效：{name}', 0
        result = self._rest.call(
            tool, merged,
            authorization=self._credentials.get(context.run_id),
            user_id=context.owner_id, tenant_id=context.tenant_id,
            permissions=context.permissions)
        if result.status == 0:
            return None, f'目标服务不可用：{result.error}', 0
        if result.status >= 400:
            return None, f'目标接口返回 {result.status}：{result.text}', \
                result.status
        if not isinstance(result.payload, dict):
            return None, '目标接口返回非 JSON 对象', result.status
        if result.payload.get('success') is False:
            return None, str(result.payload.get('message') or '目标接口返回失败'), \
                result.status
        return result.payload.get('data'), None, result.status

    @staticmethod
    def _code_for_status(status: int) -> str:
        """HTTP 状态 → 工具错误码（403/404 同一口径，不泄漏存在性）。"""
        if status == 0:
            return UPSTREAM_UNAVAILABLE
        if status in (401, 403):
            return PERMISSION_DENIED
        if status == 404:
            return RESOURCE_NOT_FOUND
        if status == 422:
            return INVALID_ARGUMENTS
        return UPSTREAM_ERROR

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
        if result.status >= 400:
            code = self._code_for_status(result.status)
            if code == PERMISSION_DENIED:
                return self._fail(call, code, _DENIED_TEXT)
            if code == RESOURCE_NOT_FOUND:
                return self._fail(call, code, _NOT_FOUND_TEXT)
            if code == INVALID_ARGUMENTS:
                return self._fail(call, code,
                                  f'目标接口参数校验失败：{result.text}')
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
    'INVALID_ARGUMENTS', 'LOG_DIAGNOSE', 'LOG_DIAGNOSE_ACTION',
    'LOG_READ_PERMISSION', 'PERMISSION_DENIED', 'RESOURCE_NOT_FOUND',
    'SharedToolGateway', 'TASK_DIAGNOSE', 'TOOL_NOT_ENABLED', 'UNKNOWN_TOOL',
    'UPSTREAM_ERROR', 'UPSTREAM_UNAVAILABLE',
]
