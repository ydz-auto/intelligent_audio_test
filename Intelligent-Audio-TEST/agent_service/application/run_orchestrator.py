# -*- coding: utf-8 -*-
"""唯一 Agent Loop（落地方案 §5 / §9）。

    组装上下文 → 调模型（流式）→ 工具调用批次并行 → 按 tool_call_id 回灌
    → 直到正常答复 / 取消 / 预算 / 连续失败。

硬规则：
- 一个模型、一个上下文窗口，不做 handoff；
- 工具调用并行执行，结果按 tool_call_id 回灌；
- 每个 step / tool call / event 都持久化，事件 sequence 严格递增；
- 只读工具自动执行；写操作在 M2 走审批，M0 一律拒绝；
- 任何模型 / 工具调用都计入 run 预算。
"""
import hashlib
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

from agent_service.application.cancel_registry import CancelRegistry
from agent_service.application.context_assembler import ContextAssembler
from agent_service.domain.enums import (
    EventType, RunStatus, StepStatus, ToolCallStatus, ToolRisk,
)
from agent_service.domain.exceptions import (
    InvalidRunTransition, LlmConfigurationError, LlmInvocationError, RunCancelled,
)
from agent_service.domain.model.budget import RunBudget
from agent_service.domain.model.entities import (
    AgentRun, AgentToolCall, ToolCallRequest, ToolResult,
)
from agent_service.domain.ports.llm import (
    LlmClient, LlmFinished, LlmRequest, LlmTextDelta, LlmToolCalls, LlmUsage,
)
from agent_service.domain.ports.run_wakeup import RunWakeup
from agent_service.domain.ports.side_effects import SideEffectChecker
from agent_service.domain.ports.tool_gateway import (
    ToolDescriptor, ToolGateway, ToolInvocationContext,
)
from agent_service.domain.repositories import (
    ArtifactRepository, EventRepository, RunRepository, SessionRepository,
    StepRepository, ToolCallRepository,
)
from agent_service.domain.services.state_machine import RunStateMachine
from shared.utils.time_utils import utcnow

logger = logging.getLogger(__name__)


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


class RunOrchestrator:
    def __init__(self, *, sessions: SessionRepository, runs: RunRepository,
                 events: EventRepository, steps: StepRepository,
                 tool_calls: ToolCallRepository, artifacts: ArtifactRepository,
                 assembler: ContextAssembler, llm_factory: Callable[[], LlmClient],
                 tool_gateway: ToolGateway, side_effects: SideEffectChecker,
                 wakeup: RunWakeup, cancel_registry: CancelRegistry,
                 settings: OrchestratorSettings):
        self._sessions = sessions
        self._runs = runs
        self._events = events
        self._steps = steps
        self._tool_calls = tool_calls
        self._artifacts = artifacts
        self._assembler = assembler
        self._llm_factory = llm_factory
        self._tool_gateway = tool_gateway
        self._side_effects = side_effects
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
        budget = RunBudget.from_dict(run.budget or self._settings.budget_defaults)
        started_at = run.started_at or utcnow()
        rounds = self._steps.next_index(run_id)
        output_bytes = 0
        turn = self._next_turn(run_id)
        db_check_counter = 0
        # Skill 披露口径在发起 run 时固化（run_started）：权限用于 L1 过滤，
        # active_skill 决定是否注入 L2；恢复时读同一条事件，口径不变。
        permissions, active_skill = self._run_scope(run_id)

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
            elapsed = (utcnow() - started_at).total_seconds()
            if budget.check_duration(elapsed):
                self._finish(run_id, RunStatus.BUDGET_EXCEEDED,
                             reason='max_duration_seconds')
                return

            step = self._steps.create(
                run_id, self._steps.next_index(run_id),
                plan_snapshot={'turn': turn})
            text_parts: List[str] = []
            calls: Sequence[ToolCallRequest] = ()
            message_id = str(uuid.uuid4())
            budget_reason: Optional[str] = None

            try:
                llm = self._llm_factory()
                request = self._build_request(
                    run, turn, permissions=permissions,
                    active_skill=active_skill)
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

            results = self._execute_batch(run, step.id, calls, turn)
            if any(result.error_code == 'RESTART_WRITE_UNVERIFIED'
                   for result in results):
                self._finish(
                    run_id, RunStatus.FAILED,
                    error='RESTART_WRITE_UNVERIFIED: 中断的写操作需人工确认')
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

    def _build_request(self, run: AgentRun, turn: int, *,
                       permissions: Sequence[str] = (),
                       active_skill: Optional[str] = None) -> LlmRequest:
        messages = self._assembler.assemble(
            run.session_id, run, permissions=permissions,
            active_skill=active_skill)
        tools = tuple(self._tool_specs())
        return LlmRequest(
            messages=tuple(messages), tools=tools,
            model=run.model, temperature=self._settings.temperature,
            max_output_tokens=self._settings.max_output_tokens,
            metadata={'run_id': run.id, 'turn': turn},
        )

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

    def _tool_specs(self) -> List[Dict]:
        specs: List[Dict] = []
        try:
            descriptors = self._tool_gateway.all_tools()
        except Exception:  # noqa: BLE001 - 工具注册表异常不阻断文本答复
            logger.warning('读取工具注册表失败', exc_info=True)
            return specs
        for descriptor in descriptors:
            specs.append({
                'type': 'function',
                'function': {
                    'name': descriptor.name,
                    'description': descriptor.description,
                    'parameters': descriptor.parameters,
                },
            })
        return specs

    def _descriptor_map(self) -> Dict[str, ToolDescriptor]:
        try:
            return {d.name: d for d in self._tool_gateway.all_tools()}
        except Exception:  # noqa: BLE001
            return {}

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
                       turn: int) -> List[ToolResult]:
        workers = max(1, min(int(self._settings.tool_max_concurrency or 1),
                             len(calls)))
        # 已落库的 tool 事件每批查一次（定向查询，不整条 run 全扫）
        emitted = self._emitted_tool_events(run.id)
        results: List[ToolResult] = []
        if workers == 1:
            for call in calls:
                results.append(self._execute_one(
                    run, step_id, call, turn, emitted))
            return results
        with ThreadPoolExecutor(max_workers=workers,
                                thread_name_prefix='agent-tool') as pool:
            futures = {
                pool.submit(self._execute_one, run, step_id, call, turn,
                            emitted): call
                for call in calls
            }
            for future in as_completed(futures):
                call = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:  # noqa: BLE001
                    logger.exception('工具执行线程异常 tool=%s', call.name)
                    results.append(ToolResult(
                        tool_call_id=call.tool_call_id, tool=call.name,
                        ok=False, content=f'工具执行异常: {exc}',
                        error_code='TOOL_EXECUTION_ERROR'))
        return results

    def _execute_one(self, run: AgentRun, step_id: str,
                     call: ToolCallRequest, turn: int,
                     emitted: set) -> ToolResult:
        if self._cancel_registry.is_cancelled(run.id):
            return ToolResult(
                tool_call_id=call.tool_call_id, tool=call.name, ok=False,
                content='run 已取消，工具未执行', error_code='RUN_CANCELLED')
        descriptor = self._descriptor_map().get(call.name)
        risk = descriptor.risk if descriptor else ToolRisk.READ
        args_hash = self._args_hash(call.arguments)
        # 幂等键 = run + step + tool_call_id + tool + args_hash。card 口径是
        # run+step+tool+args_hash，但同一批并行且参数相同的两次调用会撞键，
        # 后者的结果被错误复用（实测只执行一次）；tool_call_id 由模型给出、
        # 重启后按同一轮次原样重建，加入后既不丢幂等也不会误合并。
        idempotency_key = (
            f'{run.id}:{step_id}:{call.tool_call_id}:'
            f'{call.name}:{args_hash}')[:255]

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
            self._ensure_tool_result_event(run.id, result, turn, emitted)
            return result

        if existing is None:
            record = AgentToolCall(
                id=str(uuid.uuid4()), run_id=run.id, step_id=step_id,
                tool_call_id=call.tool_call_id, tool=call.name,
                arguments=call.arguments, args_hash=args_hash, risk=risk,
                status=ToolCallStatus.PENDING,
                idempotency_key=idempotency_key,
                created_at=utcnow(), updated_at=utcnow(),
            )
            try:
                self._tool_calls.create(record)
            except Exception:  # noqa: BLE001 - 唯一键冲突：另一线程已建
                logger.debug('工具调用记录并发冲突，复用已有记录 tool_call_id=%s',
                             call.tool_call_id)
            self._events.append(run.id, EventType.TOOL_CALL, {
                'tool_call_id': call.tool_call_id,
                'tool': call.name,
                'arguments': call.arguments,
                'risk': risk.value,
                'turn': turn,
            })
            emitted.add((EventType.TOOL_CALL, call.tool_call_id))

        if risk.requires_approval:
            # M0 只读：写操作一律拒绝（审批链路 M2 落地）
            message = '写操作需要审批，M0 未启用审批执行'
            self._tool_calls.update(
                call.tool_call_id, run.id,
                status=ToolCallStatus.DENIED,
                permission_decision='approval_required',
                result={'ok': False, 'content': message,
                        'error_code': 'APPROVAL_REQUIRED'},
                error=message)
            result = ToolResult(
                tool_call_id=call.tool_call_id, tool=call.name,
                ok=False, content=message, error_code='APPROVAL_REQUIRED')
            self._append_tool_result(run.id, result, turn, emitted)
            return result

        self._tool_calls.update(call.tool_call_id, run.id,
                                status=ToolCallStatus.RUNNING)
        context = ToolInvocationContext(
            run_id=run.id, session_id=run.session_id, owner_id=run.owner_id,
            tenant_id=run.tenant_id, step_id=step_id, permissions=(),
            idempotency_key=idempotency_key,
        )
        started = utcnow()
        try:
            result = self._tool_gateway.execute(call, context)
        except Exception as exc:  # noqa: BLE001 - 工具失败回灌模型，不炸 Loop
            logger.exception('工具执行失败 tool=%s', call.name)
            result = ToolResult(
                tool_call_id=call.tool_call_id, tool=call.name,
                ok=False, content=f'工具执行失败: {exc}',
                error_code='TOOL_EXECUTION_ERROR')
        latency_ms = int((utcnow() - started).total_seconds() * 1000)
        content = result.content or ''
        if len(content) > self._settings.tool_result_max_chars > 0:
            content = content[:self._settings.tool_result_max_chars]
            result = ToolResult(
                tool_call_id=result.tool_call_id, tool=result.tool,
                ok=result.ok, content=content, error_code=result.error_code)
        self._tool_calls.update(
            call.tool_call_id, run.id,
            status=(ToolCallStatus.COMPLETED if result.ok
                    else ToolCallStatus.FAILED),
            result={'ok': result.ok, 'content': result.content,
                    'error_code': result.error_code},
            latency_ms=latency_ms,
            permission_decision='allow',
            error=None if result.ok else (result.error_code or 'TOOL_FAILED'))
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
    def _args_hash(arguments: Dict) -> str:
        canonical = json.dumps(arguments or {}, sort_keys=True,
                               ensure_ascii=False, default=str)
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    # ------------------------------------------------------------ finish

    def _append_error(self, run_id: str, code: str, message: str) -> None:
        self._events.append(run_id, EventType.ERROR, {
            'code': code, 'message': message})

    def _finish(self, run_id: str, status: RunStatus,
                *, error: Optional[str] = None,
                reason: Optional[str] = None) -> None:
        current = self._runs.get(run_id)
        if current is None or current.status.is_terminal:
            return
        RunStateMachine.assert_transition(current.status, status)
        hit = self._runs.transition_if(
            run_id, {current.status}, status, error=error,
            finished_at=utcnow())
        if not hit:
            return
        self._events.append(run_id, EventType.RUN_FINISHED, {
            'status': status.value,
            'reason': reason,
            'error': error,
        })
        self._wakeup.notify(run_id)


__all__ = ['RunOrchestrator', 'OrchestratorSettings']
