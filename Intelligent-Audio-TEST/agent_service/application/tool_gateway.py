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
5. 本地工具：``memory_search`` / ``memory_write``（INT-2490）走文件式长期记忆，
   身份由调用上下文给定、不经模型传路径；写操作只生成待审批提案；
   探索-生成层（``ui_tree`` / ``ui_action`` / ``api_spec``，INT-2492）：
   ``api_spec`` 是本地契约解析（不发真实请求）；``ui_tree`` / ``ui_action``
   经 ``ExplorationService`` 走设备租约 + 预算 + 首动作审批后的同计划放行，
   设备 UI 通道未接时返回 ``EXPLORATION_UNAVAILABLE``（不伪造树）；
   写路径（INT-2466）：WRITE / DESTRUCTIVE 只有在 ``context.approval``
   （服务端按 ``agent_approval`` 构造的已审批凭据）存在时才执行；提案本身
   由 Loop 的审批服务落地，网关不自行放行写操作；
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
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from agent_service.application.driver_proposal_service import (
    DRIVER_PROPOSE_TOOL, DriverProposalError, DriverProposalService,
)
from agent_service.application.exploration_service import (
    ExplorationError, ExplorationService,
)
from agent_service.application.memory_service import (
    APPROVAL_REQUIRED, MemoryService, tool_error_code,
)
from agent_service.domain.enums import ToolRisk
from agent_service.domain.exceptions import MemoryError
from agent_service.domain.model.entities import ToolCallRequest, ToolResult
from agent_service.domain.ports.tool_gateway import (
    ToolDescriptor, ToolGateway, ToolInvocationContext,
)
from agent_service.domain.ports.tool_registry import (
    RunCredentialPort, ToolRegistryPort, ToolTransportPort,
)
from shared.agent_tools import testcase_tools as case_tools
from shared.agent_tools import algorithm_tools
from shared.agent_tools import evaluation_tools
from shared.agent_tools import report_tools
from shared.agent_tools import ui_exploration
from shared.agent_tools.intent_tools import redact_for_audit
from shared.models.common_enums import ReportStudioSourceType, ReportType

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

# 默认不启用记忆工具（无记忆服务时按「未启用」fail-closed）
MEMORY_TOOLS = frozenset({'memory_search', 'memory_write'})

# 探索-生成层工具（INT-2492）：ui_tree / ui_action 需要设备通道与租约，
# api_spec 是本地契约解析。设备通道未接时按 EXPLORATION_UNAVAILABLE 拒绝，
# 不返回伪造的 UI 树（卡面「不写 mock 糊过去」）。
EXPLORATION_TOOLS = frozenset({'ui_tree', 'ui_action', 'api_spec'})

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
                 credentials: RunCredentialPort,
                 memory: Optional[MemoryService] = None,
                 driver_proposals: Optional[DriverProposalService] = None,
                 exploration: Optional[ExplorationService] = None):
        self._bridge = bridge
        self._rest = rest
        self._credentials = credentials
        self._memory = memory
        self._driver_proposals = driver_proposals
        self._exploration = exploration

    # ------------------------------------------------------------ catalog

    def all_tools(self) -> Sequence[ToolDescriptor]:
        return self._bridge.descriptors()

    def describe(self, names: Sequence[str]) -> Sequence[ToolDescriptor]:
        wanted = set(names or ())
        return tuple(t for t in self.all_tools() if t.name in wanted)

    def proposal_capable(self, name: str) -> bool:
        """工具是否自带提案原语（当前仅 memory_write，INT-2490）。

        返回 ``True`` 的工具由网关原地生成「待审批提案」（文件式，审批前
        不产生副作用），Loop 不为其建 ``agent_approval``；其余 WRITE /
        DESTRUCTIVE 工具走 INT-2466 的通用审批表。
        """
        return name == 'memory_write' and self._memory is not None

    def approval_waived(self, name: str,
                        arguments: Optional[Dict[str, Any]] = None, *,
                        run_id: str = '', session_id: str = '',
                        permissions: Sequence[str] = ()) -> bool:
        """本调用是否可以跳过「新建审批单」（INT-2492 探索计划放行）。

        - ``ui_action`` 的 ``dry_run`` / ``validate`` 只做预演或校验、不下发设备
          动作，不产生副作用，因此不进审批；
        - 同一探索计划（同 run + 同设备）首个动作已审批后，后续动作自动放行
          （卡面「首个动作需审批，后续在同一探索计划内自动放行」）。放行只覆盖
          这一个设备计划，其他写工具 / 其他设备仍逐条审批。
        """
        if self._exploration is None or name != 'ui_action':
            return False
        args = dict(arguments or {})
        if args.get('dry_run') or args.get('validate'):
            return True
        return self._exploration.plan_approved(run_id, args.get('device_id'))

    def release_exploration(self, run_id: str, *, status: Any = None,
                            error: Optional[str] = None) -> None:
        """run 收口时结束探索会话（释放设备租约、落最后一版 ui_trace）。

        ``status`` / ``error`` 是 run 的终态与失败原因：取消记
        ``USER_CANCEL``、预算超限记 ``BUDGET``，失败时把原因写进轨迹，
        不能让所有收口都记成 ``DONE``。
        """
        if self._exploration is None:
            return
        try:
            self._exploration.close_run(run_id, status=status, error=error)
        except Exception:  # noqa: BLE001 - 收尾失败不掩盖 run 状态
            logger.warning('探索会话收尾失败 run=%s', run_id, exc_info=True)

    def required_permissions(self, name: str,
                             arguments: Optional[Dict[str, Any]] = None
                             ) -> Optional[Sequence[str]]:
        """写调用所需权限（按 action 收窄）；未注册返回 ``None``。

        提案阶段与审批后执行阶段都调它：前者防止无权用户生成提案，后者
        重新校验「审批后权限是否还在」（§9.4）。
        """
        return self._bridge.permissions_for(name, arguments)

    def validate_call(self, name: str,
                      arguments: Optional[Dict[str, Any]]) -> Optional[str]:
        """执行前实时校验注册状态与参数 Schema（审批期间注册表可能变化）。"""
        required = self._bridge.permissions_for(name, arguments)
        if required is None:
            return f'工具不存在：{name}'
        if self.risk_of(name) is None:
            return f'工具不存在：{name}'
        schema_error = self._bridge.validate(name, arguments or {})
        if schema_error:
            return schema_error
        if name == DRIVER_PROPOSE_TOOL and self._driver_proposals is not None:
            # 材料 / 能力画像在提案阶段就校验（缺材料不生成提案）
            return self._driver_proposals.validate(arguments or {})
        if name in ('ui_tree', 'ui_action') and (
                self._exploration is None or not self._exploration.available):
            # 设备 UI 通道未接入：提案阶段就拒绝，不生成一条注定执行不了的审批单
            return '设备 UI 通道未接入，无法读取 UI 树 / 执行 UI 动作'
        return None

    def proposal_diff(self, name: str,
                      arguments: Optional[Dict[str, Any]]
                      ) -> Optional[Dict[str, Any]]:
        """写工具的变更预览（审批人可见）。

        - REST 写工具：方法 + 路径 + 脱敏参数；
        - ``driver_propose``：提案目标 + 材料清单（代码在审批通过后才生成）；
        - ``DESTRUCTIVE`` 工具额外带 ``second_confirmation``（INT-2467）：
          审批端必须二次确认，批准请求要显式带 ``confirm=true``。
        """
        # 评估域写（INT-2469）：字段级预览（目标对象 / 变更字段 / 重评估范围 /
        # 软删语义），比裸 REST 请求更能让审批人判断影响面。
        if name == 'evaluation_manage':
            diff = evaluation_tools.proposal_diff(dict(arguments or {}))
            if diff is not None:
                return diff
        # 算法域写（INT-2470）：动作 / 目标表 / 变更字段（子实体只给条数）/
        # 软删或热重载的影响面；热重载不改数据，删除可追溯。
        if name == 'algorithm_manage':
            diff = algorithm_tools.proposal_diff(dict(arguments or {}))
            if diff is not None:
                return diff
        # 报告域写（INT-2471）：生成 / 重生成 / Studio 起草·编辑·恢复的字段级
        # 预览（目标对象、正文长度、版本、影响面）；导出给固定版本 + 格式 + 主题。
        if name == 'report_generate':
            diff = report_tools.proposal_diff(dict(arguments or {}))
            if diff is not None:
                return diff
        if name == 'report_export':
            diff = report_tools.proposal_diff_export(dict(arguments or {}))
            if diff is not None:
                return diff
        args = dict(arguments or {})
        if name == DRIVER_PROPOSE_TOOL:
            preview: Dict[str, Any] = {
                'kind': 'driver_proposal',
                'target_kind': args.get('target_kind'),
                'materials': sorted(key for key in args if args[key] is not None),
                'arguments': redact_for_audit(name, args),
            }
            self._mark_destructive(preview, name)
            return preview
        tool, merged, error = self._bridge.resolve_rest(name, args)
        if error or tool is None:
            return None
        preview = {
            'kind': 'rest_request',
            'method': tool.get('method'),
            'path': tool.get('path'),
            'arguments': redact_for_audit(name, merged),
        }
        self._mark_destructive(preview, name)
        return preview

    def _mark_destructive(self, preview: Dict[str, Any], name: str) -> None:
        """破坏性操作标记：审批端据此要求二次确认（决策接口 confirm=true）。"""
        risk = self.risk_of(name)
        if risk is ToolRisk.DESTRUCTIVE:
            preview['second_confirmation'] = {
                'required': True,
                'risk': risk.value,
                'confirm_field': 'confirm',
                'reason': '该动作不可回滚（设备重启 / 关机 / 安装 / 卸载 / '
                          '批量控制），需要二次确认后才执行。',
            }

    def risk_of(self, name: str) -> Optional[ToolRisk]:
        """工具风险（意图工具 + tool_search 命中的长尾 MCP 工具）。

        两份注册表都查不到返回 ``None``；绝不把未知工具降级成 READ —— 那会让
        写操作绕过 M0 只读门禁（INT-2487 / INT-2500）。
        """
        return self._bridge.risk_of(name)

    def risk_for(self, name: str,
                 arguments: Optional[Dict[str, Any]] = None
                 ) -> Optional[ToolRisk]:
        """动作级风险（INT-2468）：写意图工具的删除类动作是 DESTRUCTIVE。

        审批单 / 审计 / 执行期门禁用这一个口径；非写工具回落到工具级风险。
        """
        return self._bridge.risk_for(name, arguments or {})

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

        # 本地记忆工具（不访问 REST）：记忆服务未装配时按「未启用」拒绝，
        # 绝不放行成「空结果 / 无副作用成功」。
        if name in MEMORY_TOOLS:
            return self._run_memory_tool(call, name, arguments, context)

        # 写 / 破坏性工具：只有携带「已审批」凭据（服务端按 agent_approval
        # 构造，模型无法伪造）才允许产生副作用。Loop 在提案阶段不会调用本方法；
        # 这里再做一次防御，避免绕过审批直接 execute。
        # 两份注册表都查不到（None）按未知工具拒绝，不降级成 READ。
        # 动作级风险优先（写意图工具的删除类动作是 DESTRUCTIVE），门禁相同。
        risk = self.risk_for(name, arguments) or self.risk_of(name)
        if risk is None:
            return self._fail(call, UNKNOWN_TOOL, f'工具不存在：{name}')
        if risk is not ToolRisk.READ and context.approval is None and not \
                self.approval_waived(
                    name, arguments, run_id=context.run_id,
                    session_id=context.session_id,
                    permissions=context.permissions):
            return self._fail(
                call, 'APPROVAL_REQUIRED',
                '写操作需要审批，未携带审批凭据不执行。')

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
        # 驱动提案（INT-2467）：本地工具（确定性代码生成 + T2 验证），
        # 只在审批通过后执行；不注册、不发布。
        if name == DRIVER_PROPOSE_TOOL:
            return self._run_driver_propose(call, arguments, context)
        # 报告写（INT-2471）：动作 → 目标 REST；导出行内编排异步作业
        if name == 'report_generate':
            return self._run_report_generate(call, arguments, context)
        if name == 'report_export':
            return self._run_report_export(call, arguments, context)
        # 探索-生成层（INT-2492）：ui_tree / ui_action 走设备端口与租约，
        # api_spec 是本地契约解析（不发任何真实请求）。
        if name in EXPLORATION_TOOLS:
            return self._run_exploration(call, arguments, context)

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

    # ------------------------------------------------------------ report write

    def _run_report_generate(self, call: ToolCallRequest,
                             arguments: Dict[str, Any],
                             context: ToolInvocationContext) -> ToolResult:
        """``report_generate``（INT-2471）：动作 → 平台既有写接口。

        - ``generate`` / ``regenerate`` 复用报告服务既有幂等语义（已有报告返回
          ``exists``、正在生成返回 ``generating``），工具层不新建报告、不重算指标；
        - ``studio_draft`` 的 ``agent_session_id`` 由服务端按 run 注入：Studio
          据此记 AI 编辑快照来源与审计关联，**模型不可传**（避免伪造归属）；
        - 其余动作参数由 ``report_tools.resolve_call`` 校验并折成目标 REST 请求。
        """
        tool, merged, error = report_tools.resolve_call(dict(arguments or {}))
        if error or tool is None:
            return self._fail(call, INVALID_ARGUMENTS, error or '工具映射不可用')
        if arguments.get('action') == 'studio_draft' and context.session_id:
            body = merged.get('body')
            if isinstance(body, dict):
                body['agent_session_id'] = context.session_id
        return self._call_rest(call, tool, merged, context)

    def _run_report_export(self, call: ToolCallRequest,
                           arguments: Dict[str, Any],
                           context: ToolInvocationContext) -> ToolResult:
        """``report_export``（INT-2471）：Studio 文档异步导出的行内编排。

        1. 定位文档（``doc_id`` 优先，否则按 ``report_id`` 取最近更新的平台文档）；
           同时回源读文档详情（归属校验 + 当前版本 / 标题）；
        2. 固定 ``docId + version + format`` 建导出作业；服务端对同参数的
           进行中 / 已完成作业复用（重复导出不产生第二个文件）；
        3. 短轮询至终态，返回作业状态与鉴权下载引用；未完成如实返回 ``pending``，
           由模型告诉用户稍后重试（同入参再次调用即复用 / 查询同一作业）。
        """
        args = dict(arguments or {})
        error = report_tools.validate_export(args)
        if error:
            return self._fail(call, INVALID_ARGUMENTS, error)

        doc, failure = self._resolve_studio_document(call, args, context)
        if failure is not None:
            return failure
        version = args.get('version') or doc.get('current_version')
        if not isinstance(version, int) or isinstance(version, bool) or version <= 0:
            return self._fail(
                call, UPSTREAM_ERROR,
                f'Studio 文档 {doc.get("doc_id")} 缺少有效版本号，无法导出')

        body: Dict[str, Any] = {'version': version, 'format': args['format']}
        if args.get('theme'):
            body['theme'] = args['theme']
        create_tool, create_args, resolve_error = self._bridge.resolve_rest(
            report_tools.EXPORT_CREATE_TOOL,
            {'doc_id': doc['doc_id'], 'body': body})
        if resolve_error or create_tool is None:
            return self._fail(call, INVALID_ARGUMENTS,
                              resolve_error or '工具映射不可用')
        result = self._transport_call(create_tool, create_args, context)
        failure = self._transport_failure(call, create_tool, result)
        if failure is not None:
            return failure
        job = self._payload_data(result)
        if not job.get('export_id'):
            return self._fail(call, UPSTREAM_ERROR,
                              '导出作业创建返回格式异常（缺少 export_id）')
        job = self._poll_export_job(call, job, context)

        status = str(job.get('status') or '')
        note = {
            'done': '导出完成，产物通过鉴权下载引用获取。',
            'failed': f'导出失败：{job.get("error") or "未知原因"}',
        }.get(status, '导出作业已提交（异步渲染中）；稍后用同一入参再次调用即可'
                      '复用/查询该作业。')
        payload = {
            'doc_id': doc.get('doc_id'),
            'report_id': doc.get('report_id'),
            'version': job.get('version') if job.get('version') else version,
            'format': job.get('format') or args['format'],
            'theme': job.get('theme'),
            'export_id': job.get('export_id'),
            'status': status,
            'progress': job.get('progress'),
            'error': job.get('error'),
            'download_ref': job.get('download_ref'),
            'reused': bool(job.get('reused')),
            'note': note,
        }
        return self._ok(call, json.dumps(payload, ensure_ascii=False))

    def _resolve_studio_document(self, call: ToolCallRequest,
                                 args: Dict[str, Any],
                                 context: ToolInvocationContext):
        """定位 Studio 文档并回源读详情 → ``(文档 data, 失败结果)``。"""
        doc_id = args.get('doc_id')
        if not doc_id:
            list_tool = report_tools.get_tool(report_tools.DOCUMENTS_LIST_TOOL)
            result = self._transport_call(list_tool, {
                'report_id': args['report_id'],
                'source_type': ReportStudioSourceType.PLATFORM_REPORT.value,
                'limit': 1, 'offset': 0,
            }, context)
            failure = self._transport_failure(call, list_tool, result)
            if failure is not None:
                return None, failure
            items = (self._payload_data(result).get('items') or [])
            if not items:
                return None, self._fail(
                    call, RESOURCE_NOT_FOUND,
                    f'报告 {args["report_id"]} 还没有 Studio 文档；请先用 '
                    'report_generate 的 studio_draft 动作起草后再导出。')
            doc_id = items[0].get('doc_id')
            if not doc_id:
                return None, self._fail(
                    call, UPSTREAM_ERROR,
                    'Studio 文档列表返回格式异常（缺少 doc_id）')

        get_tool, get_args, resolve_error = self._bridge.resolve_rest(
            'report_studio_get_document', {'doc_id': doc_id})
        if resolve_error or get_tool is None:
            return None, self._fail(call, INVALID_ARGUMENTS,
                                    resolve_error or '工具映射不可用')
        result = self._transport_call(get_tool, get_args, context)
        failure = self._transport_failure(call, get_tool, result)
        if failure is not None:
            return None, failure
        doc = self._payload_data(result)
        if not doc.get('doc_id'):
            return None, self._fail(
                call, UPSTREAM_ERROR, 'Studio 文档详情返回格式异常（缺少 doc_id）')
        return doc, None

    def _poll_export_job(self, call: ToolCallRequest, job: Dict[str, Any],
                         context: ToolInvocationContext) -> Dict[str, Any]:
        """轮询导出作业至终态（有界）；轮询失败保留最后一次已知作业状态。"""
        tool = report_tools.get_tool(report_tools.EXPORT_JOB_TOOL)
        status = str(job.get('status') or '')
        for _ in range(report_tools.EXPORT_POLL_MAX_ATTEMPTS):
            if status in report_tools.EXPORT_TERMINAL_STATUSES:
                return job
            time.sleep(report_tools.EXPORT_POLL_INTERVAL_SECONDS)
            result = self._transport_call(
                tool, {'export_id': job['export_id']}, context)
            if self._transport_failure(call, tool, result) is not None:
                return job
            latest = self._payload_data(result)
            if not latest:
                return job
            # 复用语义（服务端标记）要保留：轮询回来的作业本身不带 reused
            latest['reused'] = bool(job.get('reused'))
            job = latest
            status = str(job.get('status') or '')
        return job

    @staticmethod
    def _payload_data(result) -> Dict[str, Any]:
        payload = getattr(result, 'payload', None)
        if not isinstance(payload, dict):
            return {}
        data = payload.get('data')
        return dict(data) if isinstance(data, dict) else {}

    def _transport_call(self, tool: dict, arguments: Dict[str, Any],
                        context: ToolInvocationContext):
        """按工具项直接发一次 REST（本地编排用，权限已在入口校验）。"""
        return self._rest.call(
            tool, arguments,
            authorization=self._credentials.get(context.run_id),
            user_id=context.owner_id, tenant_id=context.tenant_id,
            permissions=context.permissions)

    def _run_memory_tool(self, call: ToolCallRequest, name: str,
                         arguments: Dict[str, Any],
                         context: ToolInvocationContext) -> ToolResult:
        """记忆工具：路径由服务端身份构造，模型只能传关键词 / 区段。"""
        if self._memory is None:
            return self._fail(
                call, TOOL_NOT_ENABLED,
                f'工具 {name} 需要记忆服务，当前未装配。')
        try:
            if name == 'memory_search':
                payload = self._memory.search(
                    tenant_id=context.tenant_id, owner_id=context.owner_id,
                    run_id=context.run_id,
                    query=str(arguments.get('query') or '').strip(),
                    scope=str(arguments.get('scope') or 'USER'),
                    project_id=(str(arguments['project_id'])
                                if arguments.get('project_id') else None),
                    limit=(int(arguments['limit'])
                           if arguments.get('limit') is not None else None))
                return self._ok(call, json.dumps(payload, ensure_ascii=False))
            payload = self._memory.propose_write(
                tenant_id=context.tenant_id, owner_id=context.owner_id,
                run_id=context.run_id,
                section=str(arguments.get('section') or ''),
                content=str(arguments.get('content') or ''),
                project_id=(str(arguments['project_id'])
                            if arguments.get('project_id') else None),
                reason=str(arguments.get('reason') or ''))
            # 提案不携带正文预览：模型拿到的只是审批单号与目标路径，
            # 真正的内容在审批端可见，且审计不落正文。
            payload['message'] = '已生成待审批提案（未落盘）；批准后才会写入长期记忆。'
            return ToolResult(
                tool_call_id=call.tool_call_id, tool=call.name, ok=False,
                content=json.dumps(payload, ensure_ascii=False),
                error_code=APPROVAL_REQUIRED)
        except MemoryError as exc:
            return self._fail(call, tool_error_code(exc.code), str(exc))
        except (TypeError, ValueError) as exc:
            return self._fail(call, INVALID_ARGUMENTS, f'记忆工具参数非法：{exc}')

    # ------------------------------------------------------------ exploration

    def _run_exploration(self, call: ToolCallRequest,
                         arguments: Dict[str, Any],
                         context: ToolInvocationContext) -> ToolResult:
        """探索工具分派：``api_spec`` 本地解析；``ui_tree`` / ``ui_action`` 走设备。

        设备通道 / 租约在 ``ExplorationService``：租约 fail-closed、预算
        （30 动作 / 5 分钟）、首个动作审批后的同计划放行、破坏性动作与登录 /
        验证码页交回都在那里；网关只负责权限、Schema 与错误码映射。
        """
        if call.name == 'api_spec':
            return self._run_api_spec(call, arguments)
        if self._exploration is None or not self._exploration.available:
            return self._fail(
                call, 'EXPLORATION_UNAVAILABLE',
                '设备 UI 通道未接入：无法读取 UI 树 / 执行 UI 动作。'
                '本工具不返回伪造的树，请先接入设备侧 UI 探索通道。')
        try:
            if call.name == 'ui_tree':
                payload = self._exploration.ui_tree(arguments, context)
                return self._ok(call, json.dumps(payload, ensure_ascii=False))
            approval_id = (context.approval.approval_id
                           if context.approval is not None else None)
            payload = self._exploration.ui_action(
                arguments, context, approval_id=approval_id)
            return self._ok(call, json.dumps(payload, ensure_ascii=False))
        except ExplorationError as exc:
            payload = dict(exc.payload or {})
            payload.setdefault('message', str(exc))
            return self._fail(call, exc.code,
                              json.dumps(payload, ensure_ascii=False))

    def _run_api_spec(self, call: ToolCallRequest,
                      arguments: Dict[str, Any]) -> ToolResult:
        """契约解析（OpenAPI / proto / WS）：只解析，不做任何真实调用。"""
        content = arguments.get('content')
        if content is None or not str(content).strip():
            return self._fail(
                call, INVALID_ARGUMENTS,
                '缺少必填参数：content（契约内容，JSON / YAML / proto 文本）')
        try:
            spec = ui_exploration.parse_api_spec(
                content, kind=arguments.get('kind'),
                endpoint=arguments.get('endpoint'))
        except ui_exploration.SpecParseError as exc:
            return self._fail(call, INVALID_ARGUMENTS, f'契约解析失败：{exc}')
        payload = dict(spec)
        payload['summary'] = ui_exploration.summarize_spec(spec)
        payload['source_ref'] = arguments.get('source_ref')
        payload['called'] = False
        return self._ok(call, json.dumps(payload, ensure_ascii=False))

    def _run_driver_propose(self, call: ToolCallRequest,
                            arguments: Dict[str, Any],
                            context: ToolInvocationContext) -> ToolResult:
        """``driver_propose``：校验材料 → 生成提案 → 静态检查 → T2 验证。

        服务未装配时按未启用拒绝（不伪造空提案）；输入非法 / 材料不齐返回
        ``INVALID_ARGUMENTS``，不产生任何可发布产物。
        """
        if self._driver_proposals is None:
            return self._fail(
                call, TOOL_NOT_ENABLED,
                '驱动提案服务未装配（缺少 T2 验证通道），不生成提案。')
        try:
            payload = self._driver_proposals.generate(
                arguments, run_id=context.run_id)
        except DriverProposalError as exc:
            return self._fail(call, INVALID_ARGUMENTS, str(exc))
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
        # 语义校验（INT-2470 打回项 P2）：算法热重载的外层信封恒为 success，
        # 真正结果在内层 data；只看 HTTP 状态会把「缓存没重建」报成成功。
        # 动作取自原始调用参数（merged 已剔除 action）。
        if call.name == 'algorithm_manage':
            action = (call.arguments or {}).get('action')
            semantic_error = algorithm_tools.validate_result(
                str(action or ''), result.payload)
            if semantic_error:
                logger.warning('ToolGateway 回源语义失败 tool=%s action=%s',
                               call.name, action)
                return self._fail(call, UPSTREAM_ERROR, semantic_error)
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
