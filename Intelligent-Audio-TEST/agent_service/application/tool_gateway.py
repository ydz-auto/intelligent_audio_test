# -*- coding: utf-8 -*-
"""只读 ToolGateway（INT-2453，方案 §6.1 / §6.3；INT-2461 扩诊断聚合）。

意图工具（31 个注册项；M0 启用 4 个，M1 各域卡按域追加只读工具——
当前含 audio_query / evaluation_query / algorithm_query / device_query /
testcase_query / task_query / task_diagnose / log_diagnose / dashboard_query，
以及本地只读推导工具 testcase_generate）→ 目标 REST；逐调用校验：

1. 用户 / 租户：身份来自网关注入，回源请求带同一 Authorization；
2. 权限：intent 工具声明 permissions（OR 语义，``*`` 通配），不满足返回
   模型可读的普通拒绝文本，不抛内部异常、不泄漏资源是否存在；
   ``device_query`` 跨 device / spl / digital_spl 三域，按 ``action`` 收窄；
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
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from agent_service.domain.enums import ToolRisk
from agent_service.domain.model.entities import ToolCallRequest, ToolResult
from agent_service.domain.ports.tool_gateway import (
    ToolDescriptor, ToolGateway, ToolInvocationContext,
)
from agent_service.domain.ports.tool_registry import (
    RunCredentialPort, ToolRegistryPort, ToolTransportPort,
)
from shared.agent_tools import testcase_tools as case_tools
from shared.models.common_enums import ReportType

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


def _upstream_message(result) -> Optional[str]:
    """取上游 JSON 的 ``message``（用于「读未命中」类 404 的原文透传）。"""
    payload = getattr(result, 'payload', None)
    if isinstance(payload, dict):
        message = payload.get('message')
        if isinstance(message, str) and message.strip():
            return _plain_upstream_text(message.strip())
    return None


# 上游把内部实现细节写进响应（驱动异常、SQL 原文、PG 错误位置）时，模型
# 上下文只该看到普通失败文案：psycopg2 异常 + SQL + HINT 回灌会让模型照着
# 内部实现编造，也把库结构暴露给用户（INT-2523 P2-1 同型教训）。
_INTERNAL_ERROR_PATTERN = re.compile(
    r'psycopg2|sqlalchemy|operator does not exist|syntax error at or near'
    r'|traceback \(most recent call last\)|(?:^|\n)\s*(?:LINE \d+:|HINT:)',
    re.IGNORECASE)
_INTERNAL_ERROR_TEXT = '服务内部错误，请稍后重试或联系管理员。'
# 普通上游正文的长度上界：错误信息只需帮模型判断「该改参数还是该换接口」
_MAX_UPSTREAM_TEXT = 500


def _plain_upstream_text(text: Optional[str]) -> str:
    """上游正文脱敏：内部实现细节收敛为普通文案，普通正文截断到可读长度。"""
    body = (text or '').strip()
    if _INTERNAL_ERROR_PATTERN.search(body):
        return _INTERNAL_ERROR_TEXT
    return body[:_MAX_UPSTREAM_TEXT]


def _upstream_error_text(status: int, text: Optional[str]) -> str:
    """``目标接口返回 <status>：<脱敏后的上游正文>`` 的统一拼装。"""
    plain = _plain_upstream_text(text)
    return f'目标接口返回 {status}：{plain}' if plain else f'目标接口返回 {status}'


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

        # 本地工具（不访问 REST 或自行组合只读 REST）
        if name == 'tool_search':
            return self._run_tool_search(call, arguments, context)
        if name == 'platform_contract':
            return self._run_platform_contract(call, arguments)
        # 纯只读推导（回源仅 GET，不落库）：标注 → 用例草案
        if name == 'testcase_generate':
            return self._run_testcase_generate(call, arguments, context)
        # 本地只读聚合（INT-2461）：组合多个只读接口，纯函数汇总
        if name == TASK_DIAGNOSE:
            return self._run_task_diagnose(call, arguments, context)
        if name == LOG_DIAGNOSE and \
                arguments.get('action') == LOG_DIAGNOSE_ACTION:
            return self._run_log_diagnose(call, arguments, context)
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
                _upstream_error_text(result.status, result.text))
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
            return None, _upstream_error_text(result.status, result.text), \
                result.status
        if not isinstance(result.payload, dict):
            return None, '目标接口返回非 JSON 对象', result.status
        if result.payload.get('success') is False:
            return None, _plain_upstream_text(
                str(result.payload.get('message') or '目标接口返回失败')), \
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
                              f'目标接口参数校验失败：'
                              f'{_plain_upstream_text(result.text)}')
        if result.status >= 400:
            logger.warning('ToolGateway 回源 %s 失败 tool=%s target=%s',
                           result.status, call.name, name)
            return self._fail(call, UPSTREAM_ERROR,
                              _upstream_error_text(result.status, result.text))
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
    'INVALID_ARGUMENTS', 'LOG_DIAGNOSE', 'LOG_DIAGNOSE_ACTION',
    'LOG_READ_PERMISSION', 'PERMISSION_DENIED', 'REPORT_COMPARABLE_TYPES',
    'REPORT_DETAIL_TOOL', 'REPORT_TREND_TOOL', 'RESOURCE_NOT_FOUND',
    'SharedToolGateway', 'TASK_DIAGNOSE', 'TOOL_NOT_ENABLED', 'UNKNOWN_TOOL',
    'UPSTREAM_ERROR', 'UPSTREAM_UNAVAILABLE',
]
