# -*- coding: utf-8 -*-
"""唯一 Agent Loop（落地方案 §5 / §9）。

    解析供应商 → 组装上下文 → 调模型（流式）→ 工具调用批次并行
    → 按 tool_call_id 回灌 → 直到正常答复 / 取消 / 预算 / 连续失败。

硬规则：
- 一个模型、一个上下文窗口，不做 handoff；
- base_url / model / protocol / api_key 全部来自用户默认供应商（§6.4），
  无可用 Key 时 run 以 LLM_PROVIDER_NOT_CONFIGURED 失败且不发起模型请求；
- 预算与压缩阈值按有效窗口 W 计算（默认 2×W；单轮输出 ≤ min(8k, 10%×W)），
  不写死 128k；
- 工具调用并行执行，结果按 tool_call_id 回灌；
- 工具按 ``ToolDescriptor.sandbox_tier`` 分派：``T0_NONE`` 走 ToolGateway，
  ``T1_TRUSTED_SCRIPT`` 走沙箱（脚本在容器内，工具调用在沙箱外），T2 明确拒绝；
  沙箱失败按 ``FAILED`` / ``BUDGET_EXCEEDED`` 收口 run，不静默成功。
- 每个 step / tool call / event 都持久化，事件 sequence 严格递增；
- 只读工具自动执行；写操作一律「提案 → 审批 → 幂等执行」（INT-2466，
  WRITE / DESTRUCTIVE 生成 ``agent_approval`` 后 run 转 WAITING_APPROVAL，
  审批后经权限 / 注册表复核再执行，拒绝 / 过期不执行）；
- 任何模型 / 工具调用都计入 run 预算。
"""
import hashlib
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from agent_service.application.approval_service import ApprovalService
from agent_service.application.cancel_registry import CancelRegistry
from agent_service.application.context_assembler import ContextAssembler
from agent_service.application.sandbox_dispatch import (
    SandboxFailure, SandboxFailureLog, SandboxToolExecutor, disabled_executor,
)
from agent_service.application.sandbox_runner import (
    SandboxFailureReason, SandboxOutcome,
)
from agent_service.domain.enums import (
    ApprovalStatus, EventType, LlmMessageRole, RunStatus, SandboxTier,
    StepStatus, ToolCallStatus, ToolRisk,
)
from agent_service.domain.exceptions import (
    InvalidRunTransition, LlmConfigurationError, LlmInvocationError,
    LlmProviderNotConfigured, RunCancelled,
)
from agent_service.domain.model.budget import RunBudget
from agent_service.domain.model.context_budget import ContextBudget
from agent_service.domain.model.entities import (
    AgentApproval, AgentRun, AgentToolCall, LlmMessage, ToolCallRequest,
    ToolResult,
)
from agent_service.domain.ports.llm import (
    LlmFinished, LlmRequest, LlmTextDelta, LlmToolCalls, LlmUsage,
)
from agent_service.domain.ports.llm_provider import (
    LlmProviderResolver, ResolvedProvider,
)
from agent_service.domain.ports.run_wakeup import RunWakeup
from agent_service.domain.ports.side_effects import SideEffectChecker
from agent_service.domain.ports.tool_gateway import (
    ToolApproval, ToolDescriptor, ToolGateway, ToolInvocationContext,
)
from shared.agent_tools.intent_tools import (
    ALWAYS_AVAILABLE_TOOLS, redact_for_audit,
)
from agent_service.domain.repositories import (
    ArtifactRepository, EventRepository, RunRepository, SessionRepository,
    StepRepository, ToolCallRepository,
)
from agent_service.domain.services.context_budget_policy import (
    ContextBudgetPolicy,
)
from agent_service.domain.services.context_window_resolver import (
    ContextWindowResolver,
)
from agent_service.domain.services.state_machine import RunStateMachine
from shared.utils.time_utils import utcnow

logger = logging.getLogger(__name__)

# 注册表里查不到的工具不可信：按最高风险记账（fail-closed），并一律拒绝执行。
# 绝不把未知工具降级成 READ —— 那会让写操作绕过「提案 + 审批」门禁（§5.2 硬规则 5）。
_UNKNOWN_TOOL_RISK = ToolRisk.DESTRUCTIVE

# 写审批相关结果码（工具结果 / 审计 result_code 共用同一口径）
APPROVAL_REQUIRED = 'APPROVAL_REQUIRED'
APPROVAL_REJECTED = 'APPROVAL_REJECTED'
APPROVAL_EXPIRED = 'APPROVAL_EXPIRED'
APPROVAL_EXECUTION_DENIED = 'APPROVAL_EXECUTION_DENIED'

# L3 备忘的固定 schema 提示（§8.2）：只允许 JSON；事实必须带来源消息 ID。
_MEMO_SYSTEM_PROMPT = (
    '你是上下文压缩器。把给出的旧对话压缩成一个 JSON 对象，只输出 JSON，'
    '不要解释、不要 Markdown 代码块。固定 schema：'
    '{"goal": "目标", "constraints": ["约束"], '
    '"facts": [{"fact": "事实", "value": 原值, "source_id": "来源消息ID"}], '
    '"decisions": ["决策"], "artifacts": ["产物 URI"], '
    '"open_questions": ["未决问题"], "next_steps": ["下一步"]}。'
    '事实必须来自消息内容并带 source_id（消息的 message_id），不得编造数值；'
    '没有内容的字段用空字符串或空数组。'
)


def _parse_memo(text: str) -> Optional[Dict]:
    """解析 L3 备忘 JSON；非 JSON / 结构不符返回 None（调用方回退 L1）。"""
    raw = (text or '').strip()
    if not raw:
        return None
    if raw.startswith('```'):
        raw = raw.strip('`')
        if raw.lower().startswith('json'):
            raw = raw[4:]
        raw = raw.strip()
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        start, end = raw.find('{'), raw.rfind('}')
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(raw[start:end + 1])
        except (TypeError, ValueError):
            return None
    return data if isinstance(data, dict) else None


def _has_permission(granted: Sequence[str],
                    required: Sequence[str]) -> bool:
    """权限 OR 语义；``*`` 通配；required 为空表示仅需登录。"""
    if not required:
        return True
    perms = set(granted or ())
    if '*' in perms:
        return True
    return bool(perms & set(required))


def _as_sandbox_tier(value) -> Optional[SandboxTier]:
    """把 descriptor 的沙箱层级收敛成枚举；未知取值返回 ``None``。

    ``None`` 由沙箱分派层按 ``UNSUPPORTED_TIER`` 拒绝执行（不降级成 T0）。
    """
    if isinstance(value, SandboxTier):
        return value
    try:
        return SandboxTier(str(value))
    except ValueError:
        return None


@dataclass
class OrchestratorSettings:
    """Loop 行为参数（全部来自配置）。"""

    budget_defaults: Dict[str, int]
    max_consecutive_tool_failures: int = 3
    tool_max_concurrency: int = 8
    tool_result_max_chars: int = 8000
    temperature: float = 0.2
    max_output_tokens: int = 0
    cancel_db_check_every: int = 16
    event_scan_limit: int = 10000
    # 有效窗口 → 预算 / 压缩阈值（§8.3）
    token_budget_multiplier: int = 2
    auto_token_budget_multiplier: int = 4
    compaction_soft_ratio: float = 0.60
    compaction_hard_ratio: float = 0.80
    # 区段预算 / 软硬阈值统一由策略按有效窗口派生（INT-2454）
    budget_policy: Optional[ContextBudgetPolicy] = None
    # L3 备忘单轮输出上限（与主对话输出预留分开，避免占满上下文）；
    # 实际生效值 = min(本配置, 单轮输出预留 output_limit)
    memo_max_output_tokens: int = 2048


class RunOrchestrator:
    def __init__(self, *, sessions: SessionRepository, runs: RunRepository,
                 events: EventRepository, steps: StepRepository,
                 tool_calls: ToolCallRepository, artifacts: ArtifactRepository,
                 assembler: ContextAssembler,
                 provider_resolver: LlmProviderResolver,
                 tool_gateway: ToolGateway, side_effects: SideEffectChecker,
                 wakeup: RunWakeup, cancel_registry: CancelRegistry,
                 settings: OrchestratorSettings,
                 approvals: ApprovalService,
                 sandbox: Optional[SandboxToolExecutor] = None):
        self._sessions = sessions
        self._runs = runs
        self._events = events
        self._steps = steps
        self._tool_calls = tool_calls
        self._artifacts = artifacts
        self._assembler = assembler
        self._provider_resolver = provider_resolver
        self._tool_gateway = tool_gateway
        # 未装配执行器时 T1 调用显式失败（RUNNER_ERROR），绝不降级成 T0。
        self._sandbox = sandbox or disabled_executor(
            max_result_chars=settings.tool_result_max_chars)
        self._side_effects = side_effects
        self._approvals = approvals
        self._wakeup = wakeup
        self._cancel_registry = cancel_registry
        self._settings = settings

    # ------------------------------------------------------------ entry

    def execute(self, run_id: str) -> None:
        run = self._runs.get(run_id)
        if run is None:
            return
        if run.status.is_terminal:
            return
        if not self._claim(run):
            return
        self._cancel_registry.clear(run_id)
        try:
            self._loop(run_id)
        except InvalidRunTransition as exc:
            logger.error('Run 状态迁移冲突 run=%s: %s', run_id, exc)
        except Exception as exc:  # noqa: BLE001 - 未预期异常必须收口为 FAILED
            logger.exception('Run 执行异常 run=%s', run_id)
            self._append_error(run_id, 'WORKER_CRASH', str(exc))
            self._finish(run_id, RunStatus.FAILED, error=f'WORKER_CRASH: {exc}')

    def fail_run(self, run_id: str, message: str) -> None:
        self._append_error(run_id, 'WORKER_CRASH', message)
        self._finish(run_id, RunStatus.FAILED, error=message)

    # ------------------------------------------------------------ loop

    def _claim(self, run: AgentRun) -> bool:
        if run.status is RunStatus.QUEUED:
            return self._runs.transition_if(
                run.id, {RunStatus.QUEUED}, RunStatus.RUNNING,
                started_at=utcnow())
        if run.status is RunStatus.WAITING_APPROVAL:
            return self._runs.transition_if(
                run.id, {RunStatus.WAITING_APPROVAL}, RunStatus.RUNNING)
        if run.status is RunStatus.RUNNING:
            return True
        return False

    def _loop(self, run_id: str) -> None:
        run = self._runs.get(run_id)
        # §7 硬规则 5 的恢复口子：崩溃可能停在「沙箱失败已落库」与「run 收口」
        # 之间。重启后本方法会开新 step，模型新一轮给出的是新的 tool_call_id，
        # 已落库的失败调用不会再进 _execute_one —— 若不在进入模型循环前按落库
        # 原因码收口，模型回一段文本就会把 run 判 SUCCEEDED，沙箱失败静默丢失。
        persisted_step, persisted_failure = self._persisted_sandbox_failure(
            run_id)
        if persisted_failure is not None:
            self._finish_sandbox_failure(
                run_id, persisted_step, persisted_failure)
            return
        # §9.2 写审批：恢复 / 审批后重新进入 Loop 时，先把已决提案落实
        # （批准 → 幂等执行；拒绝 / 过期 → 记为拒绝结果），仍在等待则退出。
        if self._settle_approvals(run_id):
            return
        try:
            provider = self._provider_resolver.resolve_for_run(run)
        except LlmProviderNotConfigured as exc:
            # §6.4-4：无可用 Key 不发起任何模型请求，也不回退平台 Key
            self._append_error(run_id, LlmProviderNotConfigured.code, str(exc))
            self._finish(run_id, RunStatus.FAILED,
                         error=f'{LlmProviderNotConfigured.code}: {exc}')
            return
        window = provider.effective_context_window
        output_limit = provider.max_output_tokens or self._settings.max_output_tokens
        budget = self._effective_budget(run, window)
        # §8.3：预算区段与 60% / 80% 阈值统一按有效窗口派生（不写死 128k）
        context_budget = self._context_budget(provider, window, output_limit)
        soft_limit = context_budget.soft_threshold
        hard_limit = context_budget.hard_threshold
        started_at = run.started_at or utcnow()
        # §9.3：等人工审批的时长不计入执行预算（否则 TTL 内的正常审批会把
        # 15 分钟执行预算耗尽，run 在恢复时被判 BUDGET_EXCEEDED）。
        approval_wait = self._approval_wait_seconds(run_id)
        rounds = self._steps.next_index(run_id)
        output_bytes = 0
        turn = self._next_turn(run_id)
        db_check_counter = 0
        # Skill 披露口径在发起 run 时固化（run_started）：权限用于 L1 过滤，
        # active_skill 决定是否注入 L2；恢复时读同一条事件，口径不变。
        permissions, active_skill = self._run_scope(run_id)
        # §6.3 allowed-tools ∩ 用户权限：None = 未激活 Skill（不按 Skill 收窄）
        allowed_tools = self._assembler.allowed_tools(permissions, active_skill)
        # Skill 授权了 tool_search 时，检索到的长尾 MCP 工具允许在本次 run 执行；
        # 未激活 Skill 时同样允许（仅受用户权限约束）。
        allow_discovered = (allowed_tools is None
                            or 'tool_search' in allowed_tools)

        def cancel_check() -> bool:
            nonlocal db_check_counter
            if self._cancel_registry.is_cancelled(run_id):
                return True
            db_check_counter += 1
            if db_check_counter % max(1, self._settings.cancel_db_check_every) == 0:
                latest = self._runs.get(run_id)
                return bool(latest and (latest.cancel_requested
                                        or latest.status.is_terminal))
            return False

        while True:
            current = self._runs.get(run_id)
            if current is None or current.status.is_terminal:
                return
            if current.cancel_requested or self._cancel_registry.is_cancelled(run_id):
                self._finish(run_id, RunStatus.CANCELLED, reason='user_cancelled')
                return
            if budget.check_rounds(rounds):
                self._finish(run_id, RunStatus.BUDGET_EXCEEDED,
                             reason='max_rounds')
                return
            total_tokens = (current.token_in or 0) + (current.token_out or 0)
            if budget.check_tokens(total_tokens):
                self._finish(run_id, RunStatus.BUDGET_EXCEEDED,
                             reason='max_tokens')
                return
            elapsed = ((utcnow() - started_at).total_seconds()
                       - approval_wait)
            if budget.check_duration(elapsed):
                self._finish(run_id, RunStatus.BUDGET_EXCEEDED,
                             reason='max_duration_seconds')
                return

            step = self._steps.create(
                run_id, self._steps.next_index(run_id),
                plan_snapshot={
                    'turn': turn,
                    'provider_id': provider.provider_id,
                    'model': provider.model,
                    'context_window': window,
                    'context_window_source': provider.context_window_source.value,
                    'output_token_limit': output_limit,
                    'token_budget': budget.max_tokens,
                    'compaction_soft_tokens': soft_limit,
                    'compaction_hard_tokens': hard_limit,
                    'section_budgets': {
                        section.value: context_budget.section_limit(section)
                        for section in context_budget.sections
                    },
                })
            text_parts: List[str] = []
            calls: Sequence[ToolCallRequest] = ()
            message_id = str(uuid.uuid4())
            budget_reason: Optional[str] = None

            try:
                llm = self._provider_resolver.build_client(provider)
                request = self._build_request(
                    run, turn, provider, output_limit,
                    permissions=permissions, active_skill=active_skill,
                    allowed_tools=allowed_tools,
                    context_budget=context_budget,
                    memo_summarizer=self._memo_summarizer(
                        llm, provider, run_id, cancel_check,
                        output_limit=output_limit))
                stream = llm.stream(request, cancel_check=cancel_check)
                try:
                    for chunk in stream:
                        if isinstance(chunk, LlmTextDelta):
                            output_bytes += len(chunk.text.encode('utf-8'))
                            self._events.append(run_id, EventType.MESSAGE_DELTA, {
                                'message_id': message_id,
                                'delta': chunk.text,
                                'index': len(text_parts),
                                'turn': turn,
                            })
                            text_parts.append(chunk.text)
                            if budget.check_output_bytes(output_bytes):
                                budget_reason = 'max_output_bytes'
                                break
                        elif isinstance(chunk, LlmToolCalls):
                            calls = chunk.calls
                        elif isinstance(chunk, LlmUsage):
                            self._runs.update_tokens(
                                run_id, chunk.prompt_tokens,
                                chunk.completion_tokens)
                            latest = self._runs.get(run_id)
                            total = ((latest.token_in or 0) + (latest.token_out or 0)
                                     if latest else 0)
                            if budget.check_tokens(total):
                                budget_reason = 'max_tokens'
                                break
                        elif isinstance(chunk, LlmFinished):
                            continue
                finally:
                    # 预算/取消提前 break 时必须关闭上游流，释放 HTTP 连接
                    close_stream = getattr(stream, 'close', None)
                    if close_stream is not None:
                        close_stream()
            except RunCancelled:
                self._steps.finish(step.id, StepStatus.FAILED, 'cancelled')
                self._finish(run_id, RunStatus.CANCELLED, reason='user_cancelled')
                return
            except LlmProviderNotConfigured as exc:
                self._steps.finish(step.id, StepStatus.FAILED, str(exc))
                self._append_error(run_id, LlmProviderNotConfigured.code,
                                   str(exc))
                self._finish(run_id, RunStatus.FAILED,
                             error=f'{LlmProviderNotConfigured.code}: {exc}')
                return
            except LlmConfigurationError as exc:
                self._steps.finish(step.id, StepStatus.FAILED, str(exc))
                self._append_error(run_id, 'LLM_NOT_CONFIGURED', str(exc))
                self._finish(run_id, RunStatus.FAILED, error=str(exc))
                return
            except LlmInvocationError as exc:
                self._steps.finish(step.id, StepStatus.FAILED, str(exc))
                self._append_error(run_id, exc.code, str(exc))
                self._finish(run_id, RunStatus.FAILED, error=str(exc))
                return

            rounds += 1
            if budget_reason:
                self._steps.finish(step.id, StepStatus.FAILED, budget_reason)
                self._finish(run_id, RunStatus.BUDGET_EXCEEDED,
                             reason=budget_reason)
                return
            self._steps.finish(step.id, StepStatus.COMPLETED)

            if not calls:
                if not text_parts:
                    self._append_error(run_id, 'EMPTY_MODEL_RESPONSE',
                                       '模型既无文本也无工具调用')
                    self._finish(run_id, RunStatus.FAILED,
                                 error='EMPTY_MODEL_RESPONSE')
                    return
                self._finish(run_id, RunStatus.SUCCEEDED)
                return

            # 取消可能发生在模型流结束之后：后续工具批次不得再执行
            latest = self._runs.get(run_id)
            if latest is not None and (latest.cancel_requested
                                       or self._cancel_registry.is_cancelled(run_id)):
                self._finish(run_id, RunStatus.CANCELLED,
                             reason='user_cancelled')
                return

            executed = self._tool_calls.count_for_run(run_id)
            tool_limit = budget.max_tool_calls
            if tool_limit > 0 and executed + len(calls) > tool_limit:
                self._finish(run_id, RunStatus.BUDGET_EXCEEDED,
                             reason='max_tool_calls')
                return

            results, sandbox_failure = self._execute_batch(
                run, step.id, calls, turn, permissions=permissions,
                allowed_tools=allowed_tools,
                allow_discovered=allow_discovered)
            if sandbox_failure is not None:
                # §7 硬规则 5：沙箱失败不得让 run 静默成功。step 判失败，
                # run 按 outcome 收口为 FAILED / BUDGET_EXCEEDED，事件带原因码。
                self._finish_sandbox_failure(run_id, step.id, sandbox_failure)
                return
            if any(result.error_code == 'RESTART_WRITE_UNVERIFIED'
                   for result in results):
                self._finish(
                    run_id, RunStatus.FAILED,
                    error='RESTART_WRITE_UNVERIFIED: 中断的写操作需人工确认')
                return
            if self._has_unsettled_write(run_id):
                # 写操作已生成提案但还没有结果：本批不写 tool_result（会让
                # 模型误以为已完成）。先结算「本批执行期间已被批准的」提案，
                # 仍有未决则把 run 转 WAITING_APPROVAL 并退出。
                if self._settle_approvals(run_id):
                    return
                if self._has_unsettled_write(run_id):
                    self._enter_waiting_approval(run_id)
                    return
            if self._consecutive_failures(run_id) >= \
                    self._settings.max_consecutive_tool_failures > 0:
                self._append_error(
                    run_id, 'CONSECUTIVE_TOOL_FAILURES',
                    '连续工具失败达到阈值，停止自动重试')
                self._finish(run_id, RunStatus.FAILED,
                             error='CONSECUTIVE_TOOL_FAILURES')
                return
            turn += 1

    # ------------------------------------------------------------ helpers

    def _build_request(self, run: AgentRun, turn: int,
                       provider: ResolvedProvider, output_limit: int, *,
                       permissions: Sequence[str] = (),
                       active_skill: Optional[str] = None,
                       allowed_tools: Optional[frozenset] = None,
                       context_budget: Optional[ContextBudget] = None,
                       memo_summarizer=None) -> LlmRequest:
        messages = self._assembler.assemble(
            run.session_id, run, permissions=permissions,
            active_skill=active_skill, budget=context_budget,
            memo_summarizer=memo_summarizer)
        tools = tuple(self._tool_specs(permissions, allowed_tools))
        return LlmRequest(
            messages=tuple(messages), tools=tools,
            model=provider.model or run.model,
            temperature=self._settings.temperature,
            max_output_tokens=output_limit,
            metadata={'run_id': run.id, 'turn': turn,
                      'provider_id': provider.provider_id},
        )

    def _context_budget(self, provider: ResolvedProvider, window: int,
                        output_limit: int) -> ContextBudget:
        """按有效窗口 W 构造区段预算；缺省策略时按默认比例兜底。"""
        policy = self._settings.budget_policy
        if policy is None:
            policy = ContextBudgetPolicy(
                ContextWindowResolver.from_dict({'models': []}),
                soft_ratio=self._settings.compaction_soft_ratio,
                hard_ratio=self._settings.compaction_hard_ratio,
                token_budget_multiplier=self._settings.token_budget_multiplier)
        return policy.build(
            window, output_limit,
            window_source=provider.context_window_source.value,
            token_budget_multiplier=self._settings.token_budget_multiplier)

    def _memo_summarizer(self, llm, provider: ResolvedProvider,
                         run_id: str, cancel_check,
                         output_limit: int = 0):
        """L3 备忘生成器：用同一供应商调一次无工具模型，失败返回 None。

        备忘调用也是一次单轮输出，上限按 ``min(配置上限, 单轮输出预留)``
        收敛（§8.3：单轮输出 ≤ min(8k, 10%×W)），小窗口下不申请超额输出。
        """
        memo_limit = self._settings.memo_max_output_tokens
        if output_limit > 0:
            memo_limit = (min(memo_limit, output_limit)
                          if memo_limit > 0 else output_limit)

        def summarize(messages) -> Optional[Dict]:
            transcript = [
                {'message_id': item.get('message_id'),
                 'role': item.get('role'),
                 'tool': item.get('tool'),
                 'content': (item.get('content') or '')[:4000]}
                for item in messages
            ]
            request = LlmRequest(
                messages=(
                    LlmMessage(
                        role=LlmMessageRole.SYSTEM.value,
                        content=_MEMO_SYSTEM_PROMPT),
                    LlmMessage(
                        role=LlmMessageRole.USER.value,
                        content=json.dumps(transcript, ensure_ascii=False)),
                ),
                tools=(),
                model=provider.model or '',
                temperature=0.0,
                max_output_tokens=memo_limit,
                metadata={'run_id': run_id, 'purpose': 'context_memo'},
            )
            parts: List[str] = []
            for chunk in llm.stream(request, cancel_check=cancel_check):
                if isinstance(chunk, LlmTextDelta):
                    parts.append(chunk.text)
                elif isinstance(chunk, LlmUsage):
                    # 压缩调用同样计入 run 预算（§5.2）
                    self._runs.update_tokens(
                        run_id, chunk.prompt_tokens, chunk.completion_tokens)
            return _parse_memo(''.join(parts))
        return summarize

    def _run_scope(self, run_id: str) -> tuple:
        """从 run_started 取本次 run 固化的权限与激活 Skill。"""
        try:
            events = self._events.list_by_types(
                run_id, (EventType.RUN_STARTED,), 1)
        except Exception:  # noqa: BLE001 - 读取失败按「无 Skill 上下文」处理
            logger.warning('读取 run_started 失败 run=%s', run_id, exc_info=True)
            return (), None
        if not events:
            return (), None
        payload = events[0].payload or {}
        return (tuple(payload.get('permissions') or ()),
                payload.get('active_skill') or None)

    def _effective_budget(self, run: AgentRun, window: int) -> RunBudget:
        """总 token 上限按有效窗口重算（默认 2×W）。

        - ``max_tokens`` 配置为 0（默认）= 完全按 W 派生；
        - 显式正数 = 运营方硬上限，取 ``min(硬上限, 2×W)``；
        - Auto 4×W 的乘数已由配置给出（``auto_token_budget_multiplier``），
          但 run 的 Auto 模式属 M1（INT-2477），M0 没有该字段，先按默认乘数。
        换供应商后同会话下一次 run 会重新解析 W 并重算，不沿用旧阈值。
        """
        base = RunBudget.from_dict(
            run.budget or self._settings.budget_defaults)
        derived = ContextWindowResolver.token_budget(
            window, self._settings.token_budget_multiplier)
        if base.max_tokens > 0:
            derived = min(derived, base.max_tokens)
        return base.with_max_tokens(derived)

    def _tool_specs(self, permissions: Sequence[str] = (),
                    allowed_tools: Optional[frozenset] = None) -> List[Dict]:
        """本轮暴露给模型的意图工具（§6.3）。

        - 用户权限不满足的工具不装配；
        - 激活 Skill 时只装配其 ``allowed-tools`` 声明过的工具（交集）。
        """
        specs: List[Dict] = []
        try:
            descriptors = self._tool_gateway.all_tools()
        except Exception:  # noqa: BLE001 - 工具注册表异常不阻断文本答复
            logger.warning('读取工具注册表失败', exc_info=True)
            return specs
        for descriptor in descriptors:
            if allowed_tools is not None and descriptor.name not in allowed_tools:
                continue
            if not _has_permission(permissions, descriptor.permissions):
                continue
            specs.append({
                'type': 'function',
                'function': {
                    'name': descriptor.name,
                    'description': descriptor.description,
                    'parameters': descriptor.parameters,
                },
            })
        return specs

    def _descriptor_map(self) -> Optional[Dict[str, ToolDescriptor]]:
        """读取意图工具注册表；读取失败返回 ``None``（调用方整批拒绝）。

        长尾 MCP 工具天然不在意图注册表里，执行期改由 ``risk_of`` 判定是否
        已注册（两份注册表都查不到 = 未注册，见 ``_execute_one``）。

        绝不返回 ``{}``：空映射会让所有工具都「查不到」，若再降级成 READ 就把
        未知工具当只读自动执行。异常由调用方转为整批拒绝（fail-closed）。
        """
        try:
            return {d.name: d for d in self._tool_gateway.all_tools()}
        except Exception:  # noqa: BLE001 - 注册表异常必须显式上抛给调用方
            logger.exception('读取工具注册表失败，本批工具调用全部拒绝执行')
            return None

    def _scope_denial(self, name: str, descriptor: Optional[ToolDescriptor],
                      allowed_tools: Optional[frozenset],
                      allow_discovered: bool) -> Optional[tuple]:
        """执行期工具范围校验（§6.3）。

        意图工具：激活 Skill 时只允许其 ``allowed-tools``；
        长尾 MCP 工具（descriptor 为 None，tool_search 命中）：仅当未激活
        Skill，或 Skill 明确声明了 ``tool_search`` 时开放。
        """
        if name in ALWAYS_AVAILABLE_TOOLS:
            return None
        if descriptor is not None:
            if allowed_tools is not None and name not in allowed_tools:
                return ('SKILL_TOOL_DENIED',
                        f'工具 {name} 未对当前激活 Skill 开放，请改用声明过的工具。',
                        'deny')
            return None
        if not allow_discovered:
            return ('SKILL_TOOL_DENIED',
                    '当前激活 Skill 未声明 tool_search，长尾工具未开放。', 'deny')
        return None

    def _next_turn(self, run_id: str) -> int:
        max_turn = -1
        for event in self._events.list_after(
                run_id, 0, self._settings.event_scan_limit):
            turn = (event.payload or {}).get('turn')
            if isinstance(turn, int) and turn > max_turn:
                max_turn = turn
        return max_turn + 1

    def _consecutive_failures(self, run_id: str) -> int:
        limit = max(1, int(self._settings.max_consecutive_tool_failures)) + 1
        count = 0
        for call in self._tool_calls.recent(run_id, limit):
            if call.status in (ToolCallStatus.FAILED, ToolCallStatus.DENIED):
                count += 1
            else:
                break
        return count

    # ------------------------------------------------------------ tools

    def _execute_batch(self, run: AgentRun, step_id: str,
                       calls: Sequence[ToolCallRequest],
                       turn: int, *,
                       permissions: Sequence[str] = (),
                       allowed_tools: Optional[frozenset] = None,
                       allow_discovered: bool = True
                       ) -> Tuple[List[ToolResult], Optional[SandboxFailure]]:
        workers = max(1, min(int(self._settings.tool_max_concurrency or 1),
                             len(calls)))
        # 已落库的 tool 事件每批查一次（定向查询，不整条 run 全扫）
        emitted = self._emitted_tool_events(run.id)
        # 沙箱失败按批次收集：同一批并行执行，结束后取唯一一条收口 run。
        failures = SandboxFailureLog()
        # 注册表每批只读一次：一次读取失败 → 整批拒绝，不留「逐条降级」的口子
        descriptors = self._descriptor_map()
        if descriptors is None:
            results = [self._execute_one(
                run, step_id, call, turn, emitted, None, failures)
                for call in calls]
            return results, failures.winner()
        results: List[ToolResult] = []
        if workers == 1:
            for call in calls:
                results.append(self._execute_one(
                    run, step_id, call, turn, emitted, descriptors,
                    failures, permissions=permissions,
                    allowed_tools=allowed_tools,
                    allow_discovered=allow_discovered))
            return results, failures.winner()
        with ThreadPoolExecutor(max_workers=workers,
                                thread_name_prefix='agent-tool') as pool:
            futures = {
                pool.submit(self._execute_one, run, step_id, call, turn,
                            emitted, descriptors, failures,
                            permissions=permissions,
                            allowed_tools=allowed_tools,
                            allow_discovered=allow_discovered): call
                for call in calls
            }
            for future in as_completed(futures):
                # 工具自身失败已在 _execute_one 内转成结果；这里冒出来的都是
                # 落库等内部错误，必须上抛让 execute() 收口 FAILED，不能吞掉
                # 后照常执行（§9.2 每个 tool call 必须持久化 / §13.5 可审计）。
                results.append(future.result())
        return results, failures.winner()

    def _execute_one(self, run: AgentRun, step_id: str,
                     call: ToolCallRequest, turn: int,
                     emitted: set,
                     descriptors: Optional[Dict[str, ToolDescriptor]],
                     failures: SandboxFailureLog,
                     *, permissions: Sequence[str] = (),
                     allowed_tools: Optional[frozenset] = None,
                     allow_discovered: bool = True) -> ToolResult:
        if self._cancel_registry.is_cancelled(run.id):
            return ToolResult(
                tool_call_id=call.tool_call_id, tool=call.name, ok=False,
                content='run 已取消，工具未执行', error_code='RUN_CANCELLED')
        args_hash = self._args_hash(call.arguments)
        # 幂等键 = run + step + tool_call_id + tool + args_hash。card 口径是
        # run+step+tool+args_hash，但同一批并行且参数相同的两次调用会撞键，
        # 后者的结果被错误复用（实测只执行一次）；tool_call_id 由模型给出、
        # 重启后按同一轮次原样重建，加入后既不丢幂等也不会误合并。
        idempotency_key = self._idempotency_key(
            run.id, step_id, call, args_hash)

        existing = self._tool_calls.find(run.id, call.tool_call_id)
        if existing is None:
            existing = self._tool_calls.find_by_idempotency_key(idempotency_key)
        if existing is not None:
            # 崩溃可能发生在「落库 tool call」与「写 tool_call 事件」之间：
            # 补事件，保证上下文重建时 assistant tool_calls 不丢
            self._ensure_tool_call_event(run.id, existing, turn, emitted)
        if existing is not None and existing.status is ToolCallStatus.COMPLETED:
            # 断点恢复 / 重复投递：直接复用已落库结果，不再执行
            result = self._result_from_record(existing)
            self._ensure_tool_result_event(run.id, result, turn, emitted)
            return result
        if existing is not None and existing.status is ToolCallStatus.RUNNING:
            if not self._side_effects.can_replay(existing):
                message = '进程重启前的中断写操作需人工确认，禁止自动重放'
                self._tool_calls.update(
                    existing.tool_call_id, run.id,
                    status=ToolCallStatus.FAILED,
                    permission_decision='restart_write_unverified',
                    error=message)
                result = ToolResult(
                    tool_call_id=call.tool_call_id, tool=call.name,
                    ok=False, content=message,
                    error_code='RESTART_WRITE_UNVERIFIED')
                self._append_error(run.id, 'RESTART_WRITE_UNVERIFIED', message)
                self._append_tool_result(run.id, result, turn, emitted)
                return result
            self._tool_calls.update(existing.tool_call_id, run.id,
                                    status=ToolCallStatus.PENDING)
        elif existing is not None and existing.status in (
                ToolCallStatus.FAILED, ToolCallStatus.DENIED):
            # 上一次已判失败 / 被拒（例如上游抖动、审批缺失）：保留结果，不重试。
            # PENDING 表示「落库后还没开始执行」（含进程重启后重置的只读调用），
            # 必须继续执行，不能拿空结果冒充已完成。
            result = self._result_from_record(existing)
            # 崩溃可能发生在「沙箱失败落库」与「run 收口」之间：复用失败结果时
            # 仍要把 run 级信号补回，否则重启会让沙箱失败静默变成成功。
            self._recover_sandbox_failure(existing, failures)
            self._ensure_tool_result_event(run.id, result, turn, emitted)
            return result

        # 执行前必须确认风险等级：注册表不可读 → 整批拒绝；两份注册表都
        # 查不到 → 单条拒绝。绝不把「查不到」当成 READ（那会绕过写操作审批门禁）。
        if descriptors is None:
            return self._reject_unregistered(
                run, step_id, call, turn, emitted,
                status=ToolCallStatus.FAILED,
                decision='tool_registry_unavailable',
                error_code='TOOL_REGISTRY_UNAVAILABLE',
                message='工具注册表不可用，本批工具调用全部拒绝执行')
        # 意图注册表命中即用其声明风险；否则查 MCP 注册表（tool_search 命中的
        # 长尾工具），风险由网关按 HTTP 方法推导（GET=READ、其余=WRITE）。
        # 两份注册表都查不到才算未注册（fail-closed，INT-2500）。
        descriptor = descriptors.get(call.name)
        if descriptor is not None:
            # 动作级风险优先：写意图工具的删除类动作是 DESTRUCTIVE（INT-2468），
            # 工具级声明是 WRITE；审批单 / 审计记录动作级值。
            risk = (self._tool_gateway.risk_for(call.name, call.arguments)
                    or descriptor.risk)
        else:
            risk = self._tool_gateway.risk_of(call.name)
            if risk is None:
                return self._reject_unregistered(
                    run, step_id, call, turn, emitted,
                    status=ToolCallStatus.DENIED,
                    decision='tool_not_registered',
                    error_code='TOOL_NOT_REGISTERED',
                    message=f'工具未注册，拒绝执行: {call.name}')

        if existing is None:
            record = AgentToolCall(
                id=str(uuid.uuid4()), run_id=run.id, step_id=step_id,
                tool_call_id=call.tool_call_id, tool=call.name,
                # 审计不落记忆正文（INT-2490 §8.6）：memory_write 的 content
                # 以 sha256 + 长度代替，args_hash 仍按原始参数计算。
                arguments=redact_for_audit(call.name, call.arguments),
                args_hash=args_hash, risk=risk,
                status=ToolCallStatus.PENDING,
                idempotency_key=idempotency_key,
                created_at=utcnow(), updated_at=utcnow(),
            )
            # 并发唯一键冲突由仓储层收口成「复用已有记录」；其余 DB 错误
            # （连接失败、值超长等）直接上抛，由 execute() 收口 FAILED。
            self._tool_calls.create(record)
            self._events.append(run.id, EventType.TOOL_CALL, {
                'tool_call_id': call.tool_call_id,
                'tool': call.name,
                'arguments': redact_for_audit(call.name, call.arguments),
                'risk': risk.value,
                'turn': turn,
            })
            emitted.add((EventType.TOOL_CALL, call.tool_call_id))

        # §6.3 allowed-tools ∩ 用户权限：装配时收窄，执行时再校验一次 ——
        # 模型可能调用未装配的工具（幻觉 / 旧上下文），不能只靠 exposure。
        scope_error = self._scope_denial(call.name, descriptor,
                                         allowed_tools, allow_discovered)
        if scope_error is not None:
            code, message, decision = scope_error
            self._tool_calls.update(
                call.tool_call_id, run.id,
                status=ToolCallStatus.DENIED,
                permission_decision=decision,
                result={'ok': False, 'content': message, 'error_code': code},
                result_code=code,
                error=message)
            result = ToolResult(
                tool_call_id=call.tool_call_id, tool=call.name,
                ok=False, content=message, error_code=code)
            self._append_tool_result(run.id, result, turn, emitted)
            return result

        # 预留意图工具（M1 / M2 实现）：返回明确的「未启用」错误码，
        # 不按写操作审批语义处理（否则会被误读为「平台不支持」）。
        if descriptor is not None and not descriptor.enabled:
            message = f'工具 {call.name} 尚未启用（当前阶段为预留 Schema）'
            self._tool_calls.update(
                call.tool_call_id, run.id,
                status=ToolCallStatus.DENIED,
                permission_decision='not_enabled',
                result={'ok': False, 'content': message,
                        'error_code': 'TOOL_NOT_ENABLED'},
                result_code='TOOL_NOT_ENABLED',
                error=message)
            result = ToolResult(
                tool_call_id=call.tool_call_id, tool=call.name,
                ok=False, content=message, error_code='TOOL_NOT_ENABLED')
            self._append_tool_result(run.id, result, turn, emitted)
            return result

        if risk.requires_approval and not self._tool_gateway.proposal_capable(
                call.name):
            # 通用写审批（INT-2466）：WRITE / DESTRUCTIVE 一律先提案，不执行。
            # 自带提案原语的工具（memory_write，INT-2490）沿用网关原地提案。
            return self._propose_write(
                run, step_id, call, turn, emitted, risk,
                idempotency_key, args_hash, permissions)

        self._tool_calls.update(call.tool_call_id, run.id,
                                status=ToolCallStatus.RUNNING)
        context = ToolInvocationContext(
            run_id=run.id, session_id=run.session_id, owner_id=run.owner_id,
            tenant_id=run.tenant_id, step_id=step_id,
            permissions=tuple(permissions),
            idempotency_key=idempotency_key,
        )
        started = utcnow()
        sandbox_failure: Optional[SandboxFailure] = None
        # §7 硬规则 1：业务工具调用在沙箱外（ToolGateway），脚本在沙箱内；
        # 按 descriptor 的沙箱层级分派，T1 不经过 ToolGateway。
        # descriptor 为 None 表示 tool_search 动态发现的长尾 MCP 工具，未编入
        # Skill 装配表（INT-2500）：没有沙箱层级可依，按 T0_NONE 走 ToolGateway。
        if descriptor is None:
            tier = SandboxTier.T0_NONE
        else:
            tier = _as_sandbox_tier(descriptor.sandbox_tier)
        try:
            if tier is SandboxTier.T0_NONE:
                result = self._tool_gateway.execute(call, context)
            else:
                result, sandbox_failure = self._sandbox.execute(
                    call, descriptor.sandbox_tier)
        except Exception as exc:  # noqa: BLE001 - 工具失败回灌模型，不炸 Loop
            logger.exception('工具执行失败 tool=%s', call.name)
            result = ToolResult(
                tool_call_id=call.tool_call_id, tool=call.name,
                ok=False, content=f'工具执行失败: {exc}',
                error_code='TOOL_EXECUTION_ERROR')
            if tier is not SandboxTier.T0_NONE:
                # 沙箱分派本身出异常也不能让 run 静默继续：按 RUNNER_ERROR 收口。
                sandbox_failure = SandboxFailure(
                    outcome=SandboxOutcome.FAILED,
                    reason=SandboxFailureReason.RUNNER_ERROR,
                    tool_call_id=call.tool_call_id,
                    detail=f'沙箱分派异常：{exc}')
        latency_ms = int((utcnow() - started).total_seconds() * 1000)
        content = result.content or ''
        if len(content) > self._settings.tool_result_max_chars > 0:
            content = content[:self._settings.tool_result_max_chars]
            result = ToolResult(
                tool_call_id=result.tool_call_id, tool=result.tool,
                ok=result.ok, content=content, error_code=result.error_code)
        if result.ok:
            final_status = ToolCallStatus.COMPLETED
        elif result.error_code in ('PERMISSION_DENIED', 'APPROVAL_REQUIRED'):
            final_status = ToolCallStatus.DENIED
        else:
            final_status = ToolCallStatus.FAILED
        stored_result = {'ok': result.ok, 'content': result.content,
                         'error_code': result.error_code}
        if sandbox_failure is not None:
            # 落库 outcome/reason 供断点恢复时重建 run 级失败信号（见
            # _recover_sandbox_failure），不给沙箱留「重启后静默成功」的口子。
            stored_result['sandbox_outcome'] = sandbox_failure.outcome.value
            stored_result['sandbox_reason'] = sandbox_failure.reason.value
        self._tool_calls.update(
            call.tool_call_id, run.id,
            status=final_status,
            result=stored_result,
            latency_ms=latency_ms,
            permission_decision=(
                'deny' if result.error_code == 'PERMISSION_DENIED'
                else 'approval_required'
                if result.error_code == 'APPROVAL_REQUIRED' else 'allow'),
            result_code=result.error_code or ('OK' if result.ok else 'TOOL_FAILED'),
            error=None if result.ok else (result.error_code or 'TOOL_FAILED'))
        self._append_tool_result(run.id, result, turn, emitted)
        if sandbox_failure is not None:
            failures.record(sandbox_failure)
        return result

    # ------------------------------------------------------- write approvals

    def _propose_write(self, run: AgentRun, step_id: str,
                       call: ToolCallRequest, turn: int, emitted: set,
                       risk: ToolRisk, idempotency_key: str,
                       args_hash: str,
                       permissions: Sequence[str]) -> ToolResult:
        """WRITE / DESTRUCTIVE 提案路径（§5.2 硬规则 5 / §9.4）。

        - 提案前按**当前**权限与参数校验：无权用户不能生成提案；
        - 提案落 ``agent_approval``（一次 tool call 一张单，重复提交幂等）；
        - 工具调用状态置 ``WAITING_APPROVAL``，**不写 tool_result**：写操作
          还没有结果，回灌会让模型把「待审批」当成「已完成」；
        - run 由调用方在本批结束后转 ``WAITING_APPROVAL``，不做任何副作用。
        """
        required = self._tool_gateway.required_permissions(
            call.name, call.arguments)
        if required is None:
            return self._write_rejection(
                run, call, turn, emitted,
                code='TOOL_NOT_REGISTERED', decision='tool_not_registered',
                message=f'工具未注册，拒绝提案：{call.name}')
        if not _has_permission(permissions, required):
            return self._write_rejection(
                run, call, turn, emitted,
                code='PERMISSION_DENIED', decision='deny',
                message='无权发起该写操作，未生成提案。')
        validation = self._tool_gateway.validate_call(
            call.name, call.arguments)
        if validation:
            return self._write_rejection(
                run, call, turn, emitted,
                code='INVALID_ARGUMENTS', decision='deny', message=validation)

        approval, _created = self._approvals.propose(
            run, step_id=step_id, call=call, risk=risk, turn=turn,
            idempotency_key=idempotency_key, args_hash=args_hash)
        # 崩溃可能发生在「落库 tool call」与「写 tool_call 事件」之间：补事件
        existing = self._tool_calls.find(run.id, call.tool_call_id)
        if existing is not None:
            self._ensure_tool_call_event(run.id, existing, turn, emitted)
        message = '已生成待审批提案（未执行、无副作用）；批准后才会执行。'
        self._tool_calls.update(
            call.tool_call_id, run.id,
            status=ToolCallStatus.WAITING_APPROVAL,
            permission_decision='approval_required',
            result={
                'ok': False,
                'content': message,
                'error_code': APPROVAL_REQUIRED,
                'approval_id': approval.id,
                'expires_at': (approval.expires_at.isoformat()
                               if approval.expires_at else None),
            },
            result_code=APPROVAL_REQUIRED,
            error=None)
        return ToolResult(
            tool_call_id=call.tool_call_id, tool=call.name, ok=False,
            content=message, error_code=APPROVAL_REQUIRED)

    def _write_rejection(self, run: AgentRun, call: ToolCallRequest,
                         turn: int, emitted: set, *,
                         code: str, decision: str,
                         message: str) -> ToolResult:
        """提案前置校验失败：记账 + 回灌失败结果，绝不生成提案。"""
        self._tool_calls.update(
            call.tool_call_id, run.id,
            status=ToolCallStatus.DENIED,
            permission_decision=decision,
            result={'ok': False, 'content': message, 'error_code': code},
            result_code=code, error=message)
        result = ToolResult(
            tool_call_id=call.tool_call_id, tool=call.name,
            ok=False, content=message, error_code=code)
        self._append_tool_result(run.id, result, turn, emitted)
        return result

    def _settle_approvals(self, run_id: str) -> bool:
        """进入模型循环前处置本 run 的写调用与审批单。

        返回 ``True`` 表示本次不应发起模型请求：
        - 仍有未决提案 → run 转 WAITING_APPROVAL；
        - 审批通过但执行前复核失败 → run 已收口 FAILED。

        崩溃窗口兜底：写调用已落库但提案还没落（进程在最窄的窗口被杀）时，
        按落库记录重建提案（幂等），不让 run 卡在「无提案的 PENDING 写」上。
        """
        run = self._runs.get(run_id)
        if run is None or run.status.is_terminal:
            return False
        records = [record for record in self._tool_calls.list_by_run(run_id)
                   if record.risk is not ToolRisk.READ
                   # 自带提案原语的工具（memory_write）不走通用审批表
                   and not self._tool_gateway.proposal_capable(record.tool)
                   and record.status in (ToolCallStatus.PENDING,
                                         ToolCallStatus.WAITING_APPROVAL)]
        if not records:
            return False
        approvals = {}
        for item in self._approvals.list_for_run(run_id):
            # §3.1 CQRS：列表只读，到点结算放在命令侧。本轮 Loop 恢复时先
            # 把过期的 PENDING 落 EXPIRED，下面按 EXPIRED 分支回灌模型，
            # 避免「无人决策 + TTL 到点」把 run 永远挂在 WAITING_APPROVAL。
            if item.status is ApprovalStatus.PENDING:
                item = self._approvals.settle(item)
            approvals[item.tool_call_id] = item
        emitted = self._emitted_tool_events(run_id)
        waiting = False
        for record in records:
            approval = approvals.get(record.tool_call_id)
            if approval is None:
                turn = self._turn_for_call(run_id, record.tool_call_id)
                self._repropose_write(run, record, turn, emitted)
                waiting = True
                continue
            turn = int((approval.proposal or {}).get('turn') or 0)
            if approval.status is ApprovalStatus.PENDING:
                waiting = True
                continue
            if approval.status is ApprovalStatus.REJECTED:
                self._settle_write_denied(
                    run, record, turn, emitted, APPROVAL_REJECTED,
                    '审批未通过，写操作未执行。', 'approval_rejected')
                continue
            if approval.status is ApprovalStatus.EXPIRED:
                self._settle_write_denied(
                    run, record, turn, emitted, APPROVAL_EXPIRED,
                    '审批已过期，写操作未执行。', 'approval_expired')
                continue
            if self._execute_approved(run, record, approval, turn, emitted):
                return True
        if waiting:
            self._enter_waiting_approval(run_id)
            return True
        return False

    def _repropose_write(self, run: AgentRun, record: AgentToolCall,
                         turn: int, emitted: set) -> AgentApproval:
        """按落库记录重建提案（崩溃窗口兜底；propose 本身幂等）。"""
        call = ToolCallRequest(
            tool_call_id=record.tool_call_id, name=record.tool,
            arguments=record.arguments or {})
        approval, _created = self._approvals.propose(
            run, step_id=record.step_id, call=call, risk=record.risk,
            turn=turn,
            idempotency_key=record.idempotency_key or '',
            args_hash=record.args_hash)
        self._ensure_tool_call_event(run.id, record, turn, emitted)
        self._tool_calls.update(
            record.tool_call_id, run.id,
            status=ToolCallStatus.WAITING_APPROVAL,
            permission_decision='approval_required',
            result={
                'ok': False,
                'content': '已生成待审批提案（未执行、无副作用）；批准后才会执行。',
                'error_code': APPROVAL_REQUIRED,
                'approval_id': approval.id,
                'expires_at': (approval.expires_at.isoformat()
                               if approval.expires_at else None),
            },
            result_code=APPROVAL_REQUIRED,
            error=None)
        return approval

    def _approval_wait_seconds(self, run_id: str) -> float:
        """等待人工审批的累计时长（秒）：不计入 §9.3 执行时长预算。

        按审批单 ``created_at → decided_at`` 累计；未决单算到当前时刻，过期
        单算到 ``expires_at``（取消作废的单有 decided_at）。
        """
        now = utcnow()
        total = 0.0
        for approval in self._approvals.list_for_run(run_id):
            if approval.created_at is None:
                continue
            end = approval.decided_at
            if end is None:
                if approval.status is ApprovalStatus.PENDING:
                    end = now
                else:
                    end = approval.expires_at or approval.updated_at or now
            total += max(0.0, (end - approval.created_at).total_seconds())
        return total

    def _turn_for_call(self, run_id: str, tool_call_id: str) -> int:
        """从 tool_call 事件取调用所属轮次（崩溃恢复补事件分组用）。"""
        for event in self._events.list_by_types(
                run_id, (EventType.TOOL_CALL,), self._settings.event_scan_limit):
            payload = event.payload or {}
            if payload.get('tool_call_id') == tool_call_id:
                return int(payload.get('turn') or 0)
        return 0

    def _settle_write_denied(self, run: AgentRun, record: AgentToolCall,
                             turn: int, emitted: set, code: str,
                             message: str, decision: str) -> ToolResult:
        """拒绝 / 过期：记失败结果并回灌模型（无任何副作用）。"""
        self._tool_calls.update(
            record.tool_call_id, run.id,
            status=ToolCallStatus.DENIED,
            permission_decision=decision,
            result={'ok': False, 'content': message, 'error_code': code},
            result_code=code, error=message)
        result = ToolResult(
            tool_call_id=record.tool_call_id, tool=record.tool, ok=False,
            content=message, error_code=code)
        self._append_tool_result(run.id, result, turn, emitted)
        return result

    def _execute_approved(self, run: AgentRun, record: AgentToolCall,
                          approval: AgentApproval, turn: int,
                          emitted: set) -> bool:
        """执行一条已批准的写调用；返回 ``True`` 表示 run 已收口、停止循环。

        幂等 / 并发：先做 DB 条件迁移（WAITING_APPROVAL → RUNNING），抢不到
        说明别的执行者已接手，本线程不再执行（同一 Idempotency-Key 只落一次）。
        """
        call = ToolCallRequest(
            tool_call_id=record.tool_call_id, name=record.tool,
            arguments=record.arguments or {})
        failure = self._approvals.check_execution(approval, record)
        if failure is not None:
            code, message = failure
            self._tool_calls.update(
                record.tool_call_id, run.id,
                status=ToolCallStatus.FAILED,
                permission_decision='deny',
                result={'ok': False, 'content': message, 'error_code': code,
                        'approval': self._approval_audit(approval)},
                result_code=code, error=message)
            result = ToolResult(
                tool_call_id=record.tool_call_id, tool=record.tool,
                ok=False, content=message, error_code=code)
            self._append_tool_result(run.id, result, turn, emitted)
            self._append_error(
                run.id, APPROVAL_EXECUTION_DENIED,
                f'{code}: {message}')
            self._finish(
                run.id, RunStatus.FAILED,
                error=f'{APPROVAL_EXECUTION_DENIED}: {code}')
            return True

        if not self._tool_calls.claim(
                run.id, record.tool_call_id,
                (ToolCallStatus.WAITING_APPROVAL, ToolCallStatus.PENDING),
                ToolCallStatus.RUNNING):
            # 已被并发执行者抢到（重复决策 / 重复恢复）：不重复产生副作用
            return False

        context = ToolInvocationContext(
            run_id=run.id, session_id=run.session_id, owner_id=run.owner_id,
            tenant_id=run.tenant_id, step_id=record.step_id,
            permissions=tuple(approval.decision_permissions or ()),
            idempotency_key=record.idempotency_key or '',
            approval=ToolApproval(
                approval_id=approval.id,
                risk=record.risk,
                proposal=dict(approval.proposal or {}),
                diff=approval.diff),
        )
        started = utcnow()
        try:
            result = self._tool_gateway.execute(call, context)
        except Exception as exc:  # noqa: BLE001 - 工具失败回灌模型，不炸 Loop
            logger.exception('审批后写操作执行失败 tool=%s', call.name)
            result = ToolResult(
                tool_call_id=call.tool_call_id, tool=call.name, ok=False,
                content=f'工具执行失败: {exc}',
                error_code='TOOL_EXECUTION_ERROR')
        latency_ms = int((utcnow() - started).total_seconds() * 1000)
        if result.ok:
            final_status = ToolCallStatus.COMPLETED
        elif result.error_code in ('PERMISSION_DENIED', 'APPROVAL_REQUIRED'):
            final_status = ToolCallStatus.DENIED
        else:
            final_status = ToolCallStatus.FAILED
        self._tool_calls.update(
            record.tool_call_id, run.id,
            status=final_status,
            result={'ok': result.ok, 'content': result.content,
                    'error_code': result.error_code,
                    'approval': self._approval_audit(approval)},
            latency_ms=latency_ms,
            # 审计三问：谁发起（run.owner_id）、谁批准（decided_by）、
            # 产生什么副作用（result / result_code）
            permission_decision='approved',
            result_code=result.error_code or ('OK' if result.ok else 'TOOL_FAILED'),
            error=None if result.ok else (result.error_code or 'TOOL_FAILED'))
        self._append_tool_result(run.id, result, turn, emitted)
        return False

    @staticmethod
    def _approval_audit(approval: AgentApproval) -> Dict[str, Any]:
        return {
            'approval_id': approval.id,
            'decided_by': approval.decided_by,
            'decided_at': (approval.decided_at.isoformat()
                           if approval.decided_at else None),
        }

    def _has_unsettled_write(self, run_id: str) -> bool:
        """本 run 是否还有「没有结果」的通用写调用（PENDING / WAITING_APPROVAL）。"""
        for record in self._tool_calls.list_by_run(run_id):
            if record.risk is ToolRisk.READ:
                continue
            if self._tool_gateway.proposal_capable(record.tool):
                continue
            if record.status in (ToolCallStatus.PENDING,
                                 ToolCallStatus.WAITING_APPROVAL):
                return True
        return False

    def _enter_waiting_approval(self, run_id: str) -> None:
        current = self._runs.get(run_id)
        if current is None or current.status.is_terminal:
            return
        if current.status is RunStatus.WAITING_APPROVAL:
            return
        RunStateMachine.assert_transition(
            current.status, RunStatus.WAITING_APPROVAL)
        if self._runs.transition_if(
                run_id, {current.status}, RunStatus.WAITING_APPROVAL):
            self._wakeup.notify(run_id)

    def _reject_unregistered(self, run: AgentRun, step_id: str,
                             call: ToolCallRequest, turn: int, emitted: set,
                             *, status: ToolCallStatus, decision: str,
                             error_code: str, message: str) -> ToolResult:
        """未注册 / 注册表不可用：记账并拒绝执行，绝不产生副作用。

        仍落一条 ``agent_tool_call``（§9.2 每个 tool call 持久化 / §13.5 可审计），
        风险按最高等级 ``DESTRUCTIVE`` 记录（fail-closed），并补 TOOL_CALL /
        TOOL_RESULT 事件，保证模型侧 tool_calls 与结果成对、上下文可重建。
        """
        args_hash = self._args_hash(call.arguments)
        idempotency_key = self._idempotency_key(
            run.id, step_id, call, args_hash)
        stored_result = {
            'ok': False, 'content': message, 'error_code': error_code}
        existing = self._tool_calls.find(run.id, call.tool_call_id)
        if existing is None:
            existing = self._tool_calls.find_by_idempotency_key(idempotency_key)
        if existing is None:
            record = AgentToolCall(
                id=str(uuid.uuid4()), run_id=run.id, step_id=step_id,
                tool_call_id=call.tool_call_id, tool=call.name,
                arguments=redact_for_audit(call.name, call.arguments),
                args_hash=args_hash,
                risk=_UNKNOWN_TOOL_RISK, status=status,
                result=stored_result, permission_decision=decision,
                error=message, idempotency_key=idempotency_key,
                created_at=utcnow(), updated_at=utcnow(),
            )
            self._tool_calls.create(record)
            self._events.append(run.id, EventType.TOOL_CALL, {
                'tool_call_id': call.tool_call_id,
                'tool': call.name,
                'arguments': redact_for_audit(call.name, call.arguments),
                'risk': _UNKNOWN_TOOL_RISK.value,
                'rejected': error_code,
                'turn': turn,
            })
            emitted.add((EventType.TOOL_CALL, call.tool_call_id))
        else:
            self._tool_calls.update(
                existing.tool_call_id, run.id, status=status,
                permission_decision=decision, result=stored_result,
                error=message)
            self._ensure_tool_call_event(run.id, existing, turn, emitted)
        result = ToolResult(
            tool_call_id=call.tool_call_id, tool=call.name,
            ok=False, content=message, error_code=error_code)
        self._append_tool_result(run.id, result, turn, emitted)
        return result

    def _emitted_tool_events(self, run_id: str) -> set:
        """已落库的 tool 事件集合 ``{(EventType, tool_call_id)}``。

        按 (run_id, type) 定向查询，只碰 tool 事件，不整条 run 全扫。
        """
        emitted = set()
        for event in self._events.list_by_types(
                run_id, (EventType.TOOL_CALL, EventType.TOOL_RESULT),
                self._settings.event_scan_limit):
            call_id = (event.payload or {}).get('tool_call_id')
            if call_id:
                emitted.add((event.type, call_id))
        return emitted

    def _ensure_tool_call_event(self, run_id: str, record: AgentToolCall,
                                turn: int, emitted: set) -> None:
        key = (EventType.TOOL_CALL, record.tool_call_id)
        if key in emitted:
            return
        self._events.append(run_id, EventType.TOOL_CALL, {
            'tool_call_id': record.tool_call_id,
            'tool': record.tool,
            'arguments': record.arguments or {},
            'risk': record.risk.value,
            'turn': turn,
        })
        emitted.add(key)

    def _ensure_tool_result_event(self, run_id: str, result: ToolResult,
                                  turn: int, emitted: set) -> None:
        if (EventType.TOOL_RESULT, result.tool_call_id) in emitted:
            return
        self._append_tool_result(run_id, result, turn, emitted)

    def _append_tool_result(self, run_id: str, result: ToolResult,
                            turn: int, emitted: set) -> None:
        self._events.append(run_id, EventType.TOOL_RESULT, {
            'tool_call_id': result.tool_call_id,
            'tool': result.tool,
            'ok': result.ok,
            'content': result.content,
            'error_code': result.error_code,
            'turn': turn,
        })
        emitted.add((EventType.TOOL_RESULT, result.tool_call_id))

    @staticmethod
    def _result_from_record(record: AgentToolCall) -> ToolResult:
        stored = record.result or {}
        return ToolResult(
            tool_call_id=record.tool_call_id, tool=record.tool,
            ok=bool(stored.get('ok')),
            content=str(stored.get('content') or ''),
            error_code=stored.get('error_code'),
        )

    @staticmethod
    def _idempotency_key(run_id: str, step_id: str, call: ToolCallRequest,
                         args_hash: str) -> str:
        """幂等键口径（§9.2 演进裁定：并入 tool_call_id，见模型列注释）。"""
        return (f'{run_id}:{step_id}:{call.tool_call_id}:'
                f'{call.name}:{args_hash}')[:255]

    @staticmethod
    def _args_hash(arguments: Dict) -> str:
        canonical = json.dumps(arguments or {}, sort_keys=True,
                               ensure_ascii=False, default=str)
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    # ------------------------------------------------------------ finish

    def _recover_sandbox_failure(self, record: AgentToolCall,
                                 failures: SandboxFailureLog) -> None:
        """断点恢复：把已落库的沙箱失败信号补回本批次（不重跑容器）。"""
        failure = self._sandbox_failure_from_record(record)
        if failure is not None:
            failures.record(failure)

    def _persisted_sandbox_failure(
            self, run_id: str) -> Tuple[Optional[str],
                                        Optional[SandboxFailure]]:
        """读取本 run 已落库的沙箱失败记录，供 Loop 入口补回收口。

        正常路径上沙箱失败会立即收口 run；只有「失败落库后、run 收口前」
        进程崩溃，run 才会带着失败记录重新进入 Loop。此时新 step 拿到的是
        模型新一轮调用（新的 tool_call_id），旧失败不会再进 ``_execute_one``，
        必须在发起任何模型轮次前按落库原因码收口，否则会被静默当成成功。
        返回 ``(失败记录所属 step_id, 失败信号)``；无失败时 ``(None, None)``。
        """
        try:
            records = self._tool_calls.list_by_run(run_id)
        except Exception:  # noqa: BLE001 - 读取失败不阻断 Loop 正常执行
            logger.warning('读取 run 工具记录失败 run=%s', run_id, exc_info=True)
            return None, None
        failures = SandboxFailureLog()
        step_by_call: Dict[str, Optional[str]] = {}
        for record in records:
            failure = self._sandbox_failure_from_record(record)
            if failure is None:
                continue
            failures.record(failure)
            step_by_call[record.tool_call_id] = record.step_id
        winner = failures.winner()
        if winner is None:
            return None, None
        return step_by_call.get(winner.tool_call_id), winner

    def _sandbox_failure_from_record(
            self, record: AgentToolCall) -> Optional[SandboxFailure]:
        """从已落库的 tool_call 重建沙箱失败信号（未知原因码按无信号处理）。"""
        stored = record.result or {}
        outcome = stored.get('sandbox_outcome')
        reason = stored.get('sandbox_reason')
        if not outcome or not reason:
            return None
        try:
            sandbox_outcome = SandboxOutcome(outcome)
            sandbox_reason = SandboxFailureReason(reason)
        except ValueError:
            logger.warning('恢复沙箱失败信号遇到未知原因码：%s/%s',
                           outcome, reason)
            return None
        return SandboxFailure(
            outcome=sandbox_outcome, reason=sandbox_reason,
            tool_call_id=record.tool_call_id,
            detail=self._sandbox_detail_from_record(record),
        )

    @staticmethod
    def _sandbox_detail_from_record(record: AgentToolCall) -> str:
        """从落库的 tool_result 还原人读的失败详情（与首次收口文案对齐）。"""
        stored = record.result or {}
        try:
            payload = json.loads(str(stored.get('content') or '{}'))
        except (TypeError, ValueError):
            payload = None
        if isinstance(payload, dict):
            detail = payload.get('detail')
            if detail:
                return str(detail)
        return record.error or str(stored.get('content') or '')

    def _finish_sandbox_failure(self, run_id: str, step_id: Optional[str],
                                failure: SandboxFailure) -> None:
        """沙箱失败收口：step FAILED + run FAILED / BUDGET_EXCEEDED + 原因码。"""
        reason = failure.reason.value
        detail = failure.detail or reason
        message = f'{reason}: {detail}'
        self._append_error(run_id, reason, message)
        if step_id:
            self._steps.finish(step_id, StepStatus.FAILED, message)
        target = (RunStatus.BUDGET_EXCEEDED
                  if failure.outcome is SandboxOutcome.BUDGET_EXCEEDED
                  else RunStatus.FAILED)
        self._finish(run_id, target, reason=reason, error=message,
                     reason_code=reason)

    def _append_error(self, run_id: str, code: str, message: str) -> None:
        self._events.append(run_id, EventType.ERROR, {
            'code': code, 'message': message})

    def _finish(self, run_id: str, status: RunStatus,
                *, error: Optional[str] = None,
                reason: Optional[str] = None,
                reason_code: Optional[str] = None) -> None:
        current = self._runs.get(run_id)
        if current is None or current.status.is_terminal:
            return
        RunStateMachine.assert_transition(current.status, status)
        hit = self._runs.transition_if(
            run_id, {current.status}, status, error=error,
            finished_at=utcnow())
        if not hit:
            return
        payload = {
            'status': status.value,
            'reason': reason,
            'error': error,
        }
        if reason_code:
            payload['reason_code'] = reason_code
        self._events.append(run_id, EventType.RUN_FINISHED, payload)
        # run 收口后未决提案一律作废（不执行；已完成的写不回滚，§9.2-4）
        try:
            self._approvals.cancel_pending(run_id, current.owner_id)
        except Exception:  # noqa: BLE001 - 收尾失败不掩盖 run 的最终状态
            logger.warning('run 收口时作废未决审批失败 run=%s', run_id,
                           exc_info=True)
        self._wakeup.notify(run_id)


__all__ = ['RunOrchestrator', 'OrchestratorSettings']
