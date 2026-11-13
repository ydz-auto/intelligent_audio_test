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
from typing import Any, Dict, List, Optional, Sequence, Tuple

from agent_service.domain.enums import ToolRisk
from agent_service.domain.model.entities import ToolCallRequest, ToolResult
from agent_service.domain.ports.tool_gateway import (
    ToolDescriptor, ToolGateway, ToolInvocationContext,
)
from agent_service.domain.ports.tool_registry import (
    RunCredentialPort, ToolRegistryPort, ToolTransportPort,
)
from shared.models.common_enums import ReportType

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

# report_compare 组合实现用到的只读 MCP 工具（共享注册表里的 1:1 映射）
REPORT_DETAIL_TOOL = 'report_get'
REPORT_TREND_TOOL = 'report_statistics_trend'

# 二次对比只接受「对比 / 二次对比」报告（平台语义：对已有对比结论再做一次对比）
REPORT_COMPARABLE_TYPES = frozenset({
    ReportType.COMPARISON.value, ReportType.SECONDARY_COMPARISON.value})

# 并排返回的字段：全部是 GET /reports/{id} 的原文数值，工具层不重算、不聚合。
# 刻意不含 raw_data（逐用例原始取值，体量大且对比不需要）与 cases（用例明细
# 走 report_query 的 cases / cases_search 动作按需取）。
_REPORT_SUMMARY_FIELDS = (
    'total_cases', 'completed_cases', 'failed_cases', 'pass_rate')
_REPORT_MATRIX_FIELDS = (
    'resources', 'resource_headers', 'all_metrics', 'metric_data',
    'tag_metric_data', 'case_type_stats', 'device_stats', 'api_stats')


def _project_report(report_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """把报告详情压成对比需要的权威字段（数值原样搬运）。"""
    summary = data.get('summary') if isinstance(data.get('summary'), dict) else {}
    projected: Dict[str, Any] = {
        'report_id': data.get('id') or report_id,
        'name': data.get('name'),
        'type': data.get('type') or data.get('report_type'),
        'status': data.get('status'),
        'task_id': data.get('task_id'),
        'task_name': data.get('task_name'),
        'created_at': data.get('created_at'),
        'visibility': data.get('visibility'),
        'summary': {name: summary.get(name) for name in _REPORT_SUMMARY_FIELDS},
    }
    for name in _REPORT_MATRIX_FIELDS:
        projected[name] = summary.get(name) if summary.get(name) is not None else []
    # 二次对比报告：源任务集合来自 summaries[].metadata.task_ids
    source_task_ids: List[Any] = []
    for item in data.get('summaries') or ():
        metadata = item.get('metadata') if isinstance(item, dict) else None
        if isinstance(metadata, dict) and metadata.get('task_ids'):
            source_task_ids = list(metadata['task_ids'])
            break
    if source_task_ids:
        projected['source_task_ids'] = source_task_ids
    return projected


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

        # 本地工具（不访问 REST 或自行组合只读 REST）
        if name == 'tool_search':
            return self._run_tool_search(call, arguments, context)
        if name == 'platform_contract':
            return self._run_platform_contract(call, arguments)
        if name == 'report_compare':
            return self._run_report_compare(call, arguments, context)

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

    # ------------------------------------------------------------ composite

    def _run_report_compare(self, call: ToolCallRequest,
                            arguments: Dict[str, Any],
                            context: ToolInvocationContext) -> ToolResult:
        """``report_compare`` 只读组合实现（INT-2463）。

        平台的对比接口（``POST /reports/compare`` / ``secondary-compare``）会
        **落库生成新报告**，属写操作，不能挂在只读工具背后；这里改为逐报告读
        ``GET /reports/{id}`` 的权威字段并排返回，对比结论由模型基于返回原文
        叙述，数值不重算、不落报告。大结果由上下文压缩落 ``context_tool_result``
        artifact（§8.5），不进下一轮常驻上下文。
        """
        action = str(arguments.get('action') or '').strip()
        if action == 'trend':
            return self._run_report_trend(call, arguments, context)
        return self._run_report_matrix(call, action, arguments, context)

    def _run_report_trend(self, call: ToolCallRequest,
                          arguments: Dict[str, Any],
                          context: ToolInvocationContext) -> ToolResult:
        """趋势序列：单次 GET，参数由 Schema 校验保证只含 trend 字段。"""
        params = {name: value for name, value in arguments.items()
                  if name != 'action' and value is not None}
        mcp_tool, merged, error = self._bridge.resolve_rest(
            REPORT_TREND_TOOL, params)
        if error or mcp_tool is None:
            return self._fail(call, INVALID_ARGUMENTS, error or '工具映射不可用')
        return self._call_rest(call, mcp_tool, merged, context)

    def _run_report_matrix(self, call: ToolCallRequest, action: str,
                           arguments: Dict[str, Any],
                           context: ToolInvocationContext) -> ToolResult:
        report_ids = [int(value) for value in arguments.get('report_ids') or ()]
        reports: List[Dict[str, Any]] = []
        failures: List[Dict[str, Any]] = []
        incompatible: List[str] = []
        for report_id in report_ids:
            status, payload, error_text = self._fetch_report(report_id, context)
            if status != 200 or not isinstance(payload, dict):
                failures.append({
                    'report_id': report_id,
                    'status': status,
                    'message': error_text or _NOT_FOUND_TEXT,
                })
                continue
            data = payload.get('data')
            if payload.get('success') is False or not isinstance(data, dict):
                failures.append({
                    'report_id': report_id,
                    'status': status,
                    'message': str(payload.get('message') or _NOT_FOUND_TEXT),
                })
                continue
            report_type = str(data.get('type') or data.get('report_type') or '')
            if action == 'secondary_compare' and \
                    report_type not in REPORT_COMPARABLE_TYPES:
                incompatible.append(f'{report_id}({report_type or "unknown"})')
                continue
            reports.append(_project_report(report_id, data))

        # 类型不符比「取不到」更具体：先给出可行动的报错，不要退化成「不存在」
        if incompatible:
            return self._fail(
                call, INVALID_ARGUMENTS,
                'action=secondary_compare 只接受对比 / 二次对比报告，以下报告类型'
                f'不符：{"、".join(incompatible)}；对任务报告请用 action=compare')

        if not reports:
            return self._report_compare_failure(call, failures)

        payload = {
            'action': action,
            'report_count': len(reports),
            'reports': reports,
            'missing': failures,
        }
        return self._ok(call, json.dumps(payload, ensure_ascii=False))

    def _fetch_report(self, report_id: int,
                      context: ToolInvocationContext
                      ) -> Tuple[int, Any, Optional[str]]:
        """读一份报告详情，返回 ``(status, payload, 统一文案)``。

        403 / 404 一律收敛为同一句「不存在或无权访问」，不泄漏资源存在性。
        """
        mcp_tool, merged, error = self._bridge.resolve_rest(
            REPORT_DETAIL_TOOL, {'report_id': report_id})
        if error or mcp_tool is None:
            return 0, None, error or '工具映射不可用'
        result = self._rest.call(
            mcp_tool, merged,
            authorization=self._credentials.get(context.run_id),
            user_id=context.owner_id, tenant_id=context.tenant_id,
            permissions=context.permissions)
        if result.status == 0:
            return 0, None, f'目标服务不可用：{result.error}'
        if result.status in (401, 403):
            return result.status, None, _DENIED_TEXT
        if result.status == 404:
            return result.status, None, _NOT_FOUND_TEXT
        if result.status >= 400:
            return result.status, None, f'目标接口返回 {result.status}'
        return result.status, result.payload, None

    def _report_compare_failure(self, call: ToolCallRequest,
                                failures: Sequence[Dict[str, Any]]) -> ToolResult:
        """全部报告都取不到时按失败原因收敛错误码（不返回空对比）。"""
        statuses = {item.get('status') for item in failures}
        if statuses and statuses <= {401, 403}:
            return self._fail(call, PERMISSION_DENIED, _DENIED_TEXT)
        if 0 in statuses:
            return self._fail(
                call, UPSTREAM_UNAVAILABLE, '目标服务不可用：报告详情读取失败',
                ok=False)
        return self._fail(
            call, RESOURCE_NOT_FOUND,
            '参与对比的报告均不可访问（不存在或无权访问）')

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
    'INVALID_ARGUMENTS', 'PERMISSION_DENIED', 'REPORT_COMPARABLE_TYPES',
    'REPORT_DETAIL_TOOL', 'REPORT_TREND_TOOL', 'RESOURCE_NOT_FOUND',
    'SharedToolGateway', 'TOOL_NOT_ENABLED', 'UNKNOWN_TOOL', 'UPSTREAM_ERROR',
    'UPSTREAM_UNAVAILABLE',
]
