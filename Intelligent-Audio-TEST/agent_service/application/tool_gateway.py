# -*- coding: utf-8 -*-
"""只读 ToolGateway（INT-2453，方案 §6.1 / §6.3）。

意图工具（31 个注册项；M0 启用 4 个，M1 各域卡按域追加只读工具——
当前含 audio_query / evaluation_query / algorithm_query / device_query /
testcase_query，以及本地只读推导工具 testcase_generate）→ 目标 REST；逐调用校验：

1. 用户 / 租户：身份来自网关注入，回源请求带同一 Authorization；
2. 权限：intent 工具声明 permissions（OR 语义，``*`` 通配），不满足返回
   模型可读的普通拒绝文本，不抛内部异常、不泄漏资源是否存在；
   ``device_query`` 跨 device / spl / digital_spl 三域，按 ``action`` 收窄；
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
import math
from typing import Any, Dict, Optional, Sequence

from agent_service.domain.enums import ToolRisk
from agent_service.domain.model.entities import ToolCallRequest, ToolResult
from agent_service.domain.ports.tool_gateway import (
    ToolDescriptor, ToolGateway, ToolInvocationContext,
)
from agent_service.domain.ports.tool_registry import (
    RunCredentialPort, ToolRegistryPort, ToolTransportPort,
)
from shared.agent_tools import testcase_tools as case_tools

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

# 404 语义是「这一轮没有参考参数 / 轮次不存在」而不是越权的只读工具：
# 沿用上游文案，避免模型把「未生成」回答成「无权访问」。
_NOT_FOUND_MESSAGE_TOOLS = frozenset({'testcase_round_ref_params'})

# 上游「业务未找到」的 code / 文案口径：部分只读接口对不存在的资源返回
# 400 + code 203（如播放设备详情），不是 404，也不是真正的参数错误。
_BUSINESS_NOT_FOUND_CODES = frozenset({203, 404})
_BUSINESS_NOT_FOUND_TERMS = ('未找到', '不存在', 'not found')

# 分组存在性校验的分页口径（分组数会超过单页默认值，不能只查第一页）
GROUP_LOOKUP_PER_PAGE = 200
GROUP_LOOKUP_MAX_PAGES = 50


def _business_not_found(result) -> bool:
    """上游以 400 + 业务 code / 文案表达「资源不存在」。"""
    payload = getattr(result, 'payload', None)
    if not isinstance(payload, dict):
        return False
    if payload.get('code') in _BUSINESS_NOT_FOUND_CODES:
        return True
    message = payload.get('message')
    if isinstance(message, str):
        text = message.strip().lower()
        return any(term in text for term in _BUSINESS_NOT_FOUND_TERMS)
    return False


def _granted(granted: Sequence[str], required: Sequence[str]) -> bool:
    """权限 OR 语义；``*`` 通配；required 为空表示仅需登录。"""
    if not required:
        return True
    perms = set(granted or ())
    if '*' in perms:
        return True
    return bool(perms & set(required))


def _upstream_message(result) -> Optional[str]:
    """取上游 JSON 的 ``message``（用于「读未命中」类 404 的原文透传）。"""
    payload = getattr(result, 'payload', None)
    if isinstance(payload, dict):
        message = payload.get('message')
        if isinstance(message, str) and message.strip():
            return message.strip()
    return None


def _envelope_items(payload: Optional[dict]):
    """取统一分页信封的 ``data.items``；结构不符返回 ``None``。"""
    if not isinstance(payload, dict):
        return None
    data = payload.get('data')
    if not isinstance(data, dict):
        return None
    items = data.get('items')
    return items if isinstance(items, list) else None


def _algorithm_values(payload: Optional[dict]):
    """取算法下拉选项的取值集合（``data.algorithms[].value``）。

    结构不符返回 ``None``（调用方按上游格式异常处理）；空列表是合法结果。
    """
    if not isinstance(payload, dict):
        return None
    data = payload.get('data')
    if not isinstance(data, dict):
        return None
    rows = data.get('algorithms')
    if not isinstance(rows, list):
        return None
    return {str(row['value']) for row in rows
            if isinstance(row, dict) and row.get('value') is not None}


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
        # 按调用参数解析权限：横跨多个权限域的工具（device_query）按 action
        # 收窄，其余工具等价于工具级声明；未知工具返回 None。
        required = self._bridge.permissions_for(name, arguments)
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
        # 纯只读推导（回源仅 GET，不落库）：标注 → 用例草案
        if name == 'testcase_generate':
            return self._run_testcase_generate(call, arguments, context)

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

    # ------------------------------------------------------- derive (read-only)

    def _run_testcase_generate(self, call: ToolCallRequest,
                               arguments: Dict[str, Any],
                               context: ToolInvocationContext) -> ToolResult:
        """标注 → 用例草案（INT-2460）。**只读推导**：全程只回源 GET。

        - 入参校验显式失败：`audio_ids` 必须是非空正整数列表、
          `device_type` / `dimension_round_scope` 必须合法、`dimension_ids`
          逐项合法（INT-2529/2531）、`spl` / `playback_device_id` 合法、条数不超上限；
        - 引用资源存在性校验（INT-2530：收 ID 必须验存在，失败显式报错，不静默
          忽略）：`algorithm_type`、`dimension_ids`、`playback_device_id`、
          `group_id`（分组分页查全，不只查第一页）；
        - 逐音频回源取详情（顺带完成行级可见性校验），不吞 403/404；
        - 最后交给纯函数 ``build_case_drafts`` 推导，不写任何表。
        """
        audio_ids = arguments.get('audio_ids')
        if not isinstance(audio_ids, list) or not audio_ids:
            return self._fail(call, INVALID_ARGUMENTS, 'audio_ids 不能为空')
        invalid = [value for value in audio_ids
                   if not isinstance(value, int) or isinstance(value, bool)
                   or value <= 0]
        if invalid:
            return self._fail(call, INVALID_ARGUMENTS,
                              f'audio_ids 必须是正整数：{invalid}')
        unique_ids = list(dict.fromkeys(audio_ids))
        if len(unique_ids) > case_tools.MAX_GENERATE_AUDIOS:
            return self._fail(
                call, INVALID_ARGUMENTS,
                f'audio_ids 单次最多 {case_tools.MAX_GENERATE_AUDIOS} 条，'
                f'当前 {len(unique_ids)} 条')

        device_type = arguments.get('device_type')
        normalized_device = case_tools.normalize_device_type(device_type)
        if normalized_device is None:
            return self._fail(
                call, INVALID_ARGUMENTS,
                f'device_type 取值非法：{device_type}')
        round_scope = arguments.get('dimension_round_scope') or 'single'
        if round_scope not in case_tools.ROUND_SCOPES:
            return self._fail(
                call, INVALID_ARGUMENTS,
                'dimension_round_scope 取值必须是 '
                f'{"/".join(case_tools.ROUND_SCOPES)} 之一')

        spl = arguments.get('spl')
        if spl is not None and (isinstance(spl, bool)
                                or not isinstance(spl, (int, float))
                                or not math.isfinite(spl) or spl < 0):
            return self._fail(call, INVALID_ARGUMENTS,
                              f'spl 必须是非负数值：{spl}')
        playback_device_id = arguments.get('playback_device_id')
        if playback_device_id is not None and not case_tools.is_positive_int(
                playback_device_id):
            return self._fail(call, INVALID_ARGUMENTS,
                              f'playback_device_id 必须是正整数：{playback_device_id}')
        dimension_error = case_tools.validate_dimension_ids(
            arguments.get('dimension_ids'))
        if dimension_error:
            return self._fail(call, INVALID_ARGUMENTS, dimension_error)
        dimensions = list(arguments.get('dimension_ids') or [])

        # ---- 引用资源存在性（全部先于草案推导，避免「草案带出不存在的 ID」）----
        algorithm_type = arguments.get('algorithm_type')
        case_params: list = []
        if algorithm_type:
            options_payload, failure = self._fetch_payload(
                call, 'algorithm_options', {}, context)
            if failure is not None:
                return failure
            available = _algorithm_values(options_payload)
            if available is None:
                return self._fail(call, UPSTREAM_ERROR,
                                  '算法下拉选项返回格式异常（缺少 data.algorithms）')
            if str(algorithm_type) not in available:
                return self._fail(
                    call, INVALID_ARGUMENTS,
                    f'algorithm_type={algorithm_type} 不存在，'
                    f'可选值：{"/".join(sorted(available)) or "（无）"}')
            payload, failure = self._fetch_payload(
                call, 'algorithm_query',
                {'action': 'case_params', 'algorithm_type': algorithm_type},
                context)
            if failure is not None:
                return failure
            items = _envelope_items(payload)
            if items is None:
                return self._fail(call, UPSTREAM_ERROR,
                                  '算法用例参数返回格式异常（缺少 data.items）')
            case_params = items

        missing_dimensions = []
        for dim in dimensions:
            dim_id = dim.get('id') if isinstance(dim, dict) else dim
            exists, failure = self._probe_exists(
                call, 'evaluation_dimension_get', {'dim_id': dim_id}, context)
            if failure is not None:
                return failure
            if not exists:
                missing_dimensions.append(dim_id)
        if missing_dimensions:
            return self._fail(
                call, INVALID_ARGUMENTS,
                f'dimension_ids 不存在或无权限：{missing_dimensions}，'
                '请先用 evaluation_query 的 dimensions 动作确认')

        if playback_device_id is not None:
            exists, failure = self._probe_exists(
                call, case_tools.PLAYBACK_DEVICE_GET_TOOL,
                {'device_id': playback_device_id}, context)
            if failure is not None:
                return failure
            if not exists:
                return self._fail(
                    call, INVALID_ARGUMENTS,
                    f'playback_device_id={playback_device_id} 不存在或无权限，'
                    '请先确认播放设备 ID')

        group_id = arguments.get('group_id')
        if group_id:
            exists, failure = self._group_exists(call, str(group_id), context)
            if failure is not None:
                return failure
            if not exists:
                return self._fail(
                    call, INVALID_ARGUMENTS,
                    f'group_id={group_id} 不存在或无权限，请先用 group_list 确认')

        audios: list = []
        for audio_id in unique_ids:
            payload, failure = self._fetch_payload(
                call, 'audio_query',
                {'action': 'detail', 'audio_id': audio_id}, context)
            if failure is not None:
                return failure
            detail = (payload or {}).get('data')
            if not isinstance(detail, dict):
                return self._fail(call, UPSTREAM_ERROR,
                                  f'音频 {audio_id} 详情返回格式异常')
            audios.append(detail)

        try:
            result = case_tools.build_case_drafts(
                audios=audios,
                case_params=case_params,
                algorithm_type=algorithm_type,
                device_type=normalized_device,
                dimensions=dimensions,
                dimension_round_scope=round_scope,
                group_id=group_id,
                spl=spl,
                playback_device_id=playback_device_id,
                inherit_tags=bool(arguments.get('inherit_tags', True)),
            )
        except Exception as exc:  # noqa: BLE001 - 推导失败要显式回给模型
            logger.warning('testcase_generate 推导失败', exc_info=True)
            return self._fail(call, INVALID_ARGUMENTS, f'草案推导失败：{exc}')

        payload = {'mode': 'draft', 'persisted': False, 'writes': 0, **result}
        return self._ok(call, json.dumps(payload, ensure_ascii=False))

    def _group_exists(self, call: ToolCallRequest, group_id: str,
                      context: ToolInvocationContext):
        """分页查全分组列表判断存在性（不能用单页默认值误判，INT-2530）。"""
        page = 1
        while page <= GROUP_LOOKUP_MAX_PAGES:
            payload, failure = self._fetch_payload(
                call, 'group_list',
                {'page': page, 'per_page': GROUP_LOOKUP_PER_PAGE}, context)
            if failure is not None:
                return None, failure
            items = _envelope_items(payload)
            if items is None:
                return None, self._fail(
                    call, UPSTREAM_ERROR, '分组列表返回格式异常（缺少 data.items）')
            if any(str(item.get('id')) == group_id for item in items):
                return True, None
            total_pages = 1
            data = (payload or {}).get('data') if isinstance(payload, dict) else None
            if isinstance(data, dict) and data.get('pages') is not None:
                try:
                    total_pages = int(data['pages'])
                except (TypeError, ValueError):
                    total_pages = 1
            if not items or page >= total_pages:
                return False, None
            page += 1
        return False, None

    def _probe_exists(self, call: ToolCallRequest, tool,
                      arguments: Dict[str, Any],
                      context: ToolInvocationContext):
        """回源 GET 单一资源探测存在性 → ``(是否存在, 失败结果)``。

        - 2xx：存在；404 或 400 + 业务未找到：不存在；
        - 401/403 统一收敛为 PERMISSION_DENIED（不泄漏存在性）；
        - 其它 4xx/5xx 与不可用：返回失败结果，由调用方原样透出。
        ``tool`` 可以是工具名（走注册表解析）或工具项（内部校验用）。
        """
        if isinstance(tool, str):
            resolved, merged, resolve_error = self._bridge.resolve_rest(
                tool, arguments)
            if resolve_error or resolved is None:
                return None, self._fail(
                    call, INVALID_ARGUMENTS, resolve_error or '工具映射不可用')
            tool, arguments = resolved, merged
        authorization = self._credentials.get(context.run_id)
        result = self._rest.call(
            tool, arguments, authorization=authorization,
            user_id=context.owner_id, tenant_id=context.tenant_id,
            permissions=context.permissions)
        if result.status == 0:
            return None, self._fail(
                call, UPSTREAM_UNAVAILABLE, f'目标服务不可用：{result.error}')
        if result.status in (401, 403):
            return None, self._fail(call, PERMISSION_DENIED, _DENIED_TEXT)
        if result.status == 404 or (result.status == 400
                                    and _business_not_found(result)):
            return False, None
        if result.status >= 400:
            logger.warning('ToolGateway 存在性探测失败 %s tool=%s',
                           result.status, tool['name'])
            return None, self._fail(
                call, UPSTREAM_ERROR,
                f'目标接口返回 {result.status}：{result.text}')
        return True, None

    def _fetch_payload(self, call: ToolCallRequest, name: str,
                       arguments: Dict[str, Any],
                       context: ToolInvocationContext):
        """按工具 / 动作名回源取 JSON：``(payload, None)`` 或 ``(None, 失败结果)``。"""
        tool, merged, resolve_error = self._bridge.resolve_rest(name, arguments)
        if resolve_error or tool is None:
            return None, self._fail(call, INVALID_ARGUMENTS,
                                    resolve_error or '工具映射不可用')
        authorization = self._credentials.get(context.run_id)
        result = self._rest.call(
            tool, merged, authorization=authorization,
            user_id=context.owner_id, tenant_id=context.tenant_id,
            permissions=context.permissions)
        failure = self._transport_failure(call, tool, result)
        if failure is not None:
            return None, failure
        return (result.payload if isinstance(result.payload, dict) else {}), None

    # ------------------------------------------------------------ rest

    def _call_rest(self, call: ToolCallRequest, tool: dict,
                   arguments: Dict[str, Any],
                   context: ToolInvocationContext) -> ToolResult:
        authorization = self._credentials.get(context.run_id)
        result = self._rest.call(
            tool, arguments, authorization=authorization,
            user_id=context.owner_id, tenant_id=context.tenant_id,
            permissions=context.permissions)
        failure = self._transport_failure(call, tool, result)
        if failure is not None:
            return failure
        return self._ok(call, result.text)

    def _transport_failure(self, call: ToolCallRequest, tool: dict,
                           result) -> Optional[ToolResult]:
        """把回源结果映射为失败结果；成功（2xx）返回 ``None``。"""
        name = tool['name']
        if result.status == 0:
            return self._fail(call, UPSTREAM_UNAVAILABLE,
                              f'目标服务不可用：{result.error}', ok=False)
        if result.status in (401, 403):
            return self._fail(call, PERMISSION_DENIED, _DENIED_TEXT)
        if result.status == 404:
            text = _NOT_FOUND_TEXT
            if name in _NOT_FOUND_MESSAGE_TOOLS:
                text = _upstream_message(result) or _NOT_FOUND_TEXT
            return self._fail(call, RESOURCE_NOT_FOUND, text)
        if result.status == 422:
            return self._fail(call, INVALID_ARGUMENTS,
                              f'目标接口参数校验失败：{result.text}')
        if result.status >= 400:
            logger.warning('ToolGateway 回源 %s 失败 tool=%s target=%s',
                           result.status, call.name, name)
            return self._fail(call, UPSTREAM_ERROR,
                              f'目标接口返回 {result.status}：{result.text}')
        return None

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
