# -*- coding: utf-8 -*-
"""Auto 模式：目标驱动续跑与停止条件（INT-2474，方案 §9.3 / §9.4）。

Auto 不新增 agent / subagent，仍是同一条 Loop：区别只在「何时继续、何时
停、什么算完成」。本模块只放**纯决策**（不碰仓储、不调模型），便于单测把
预算边界与熔断阈值逐条钉死；Loop 的落地在 ``run_orchestrator``。

停止条件：

1. 硬预算（轮次 / 工具调用 / token / 时长 / 输出字节）→ 由 ``RunBudget``
   判定，统一收口 ``BUDGET_EXCEEDED``，已完成产物与事件保留（§9.3）；
2. 连续工具失败 ≥ 熔断阈值 → 停止自动重试，``FAILED``（§9.3）；
3. 连续工具失败 ≥ 暂停阈值 → 暂停（``WAITING_APPROVAL``）交用户决策（§9.4）；
4. 预算消耗 ≥ 暂停比例（默认 80%）→ 暂停交用户决策（§9.4）；用户「继续」
   后该维度不再暂停（硬预算仍生效）；
5. 模型输出完成标记 → 正常结束；没有标记又不调工具的连续空转达上限 →
   以 ``auto_idle_limit`` 结束（不把空转耗满预算）。

暂停 / 继续的事实全部落在事件流（``run_paused`` / ``run_resumed``）里：
重启后按同一份事件重建控制状态，不依赖进程内标志。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from agent_service.domain.enums import EventType, ToolCallStatus
from agent_service.domain.model.budget import RunBudget

# 进度事件（``auto_step``）的 phase 取值
PHASE_STEP = 'step'
PHASE_CONTINUE = 'continue'
PHASE_RESUME = 'resume'

# 暂停原因码（run_paused 事件 / 进度事件共用）
PAUSE_REASON_BUDGET = 'budget_threshold'
PAUSE_REASON_FAILURES = 'consecutive_tool_failures'

# 运行收口原因码（run_finished.payload.reason）
COMPLETE_REASON = 'auto_complete'
IDLE_REASON = 'auto_idle_limit'

# 预算维度键（与 RunBudget 一致，进度事件按同一口径上报）
_DIMENSION_KEYS = (
    'max_rounds', 'max_tool_calls', 'max_tokens',
    'max_duration_seconds', 'max_output_bytes',
)

# 出现这些事件说明「重启 / 继续」之后已经跑过内容，resume 提示不再补
_SUBSTANTIVE_EVENTS = frozenset({
    EventType.MESSAGE_DELTA, EventType.TOOL_CALL, EventType.TOOL_RESULT,
    EventType.ERROR, EventType.RUN_FINISHED,
})


@dataclass(frozen=True)
class AutoSettings:
    """Auto 模式参数（全部来自配置，代码里不写死阈值）。"""

    # 预算消耗到该比例（含）即暂停交用户决策（§9.4：默认 80%）
    pause_budget_ratio: float = 0.80
    # 连续工具失败到该值即暂停（§9.4：默认 2）
    pause_consecutive_failures: int = 2
    # 连续工具失败到该值即熔断（§9.3：停止自动重试，FAILED）
    max_consecutive_failures: int = 3
    # 「没有完成标记、也不调工具」的空转最多提示几次，超过即按完成收口
    max_idle_turns: int = 2
    # 模型宣告目标完成的标记（写进 Auto 系统提示，可配置）
    complete_marker: str = '[[AUTO_DONE]]'
    # scratchpad 里保留的计划摘要长度上限（字符）
    plan_max_chars: int = 800


class AutoAction(str, Enum):
    """一次决策的结果（Loop 只按这些取值分支）。"""

    CONTINUE = 'CONTINUE'
    COMPLETE = 'COMPLETE'
    COMPLETE_IDLE = 'COMPLETE_IDLE'
    PAUSE_BUDGET = 'PAUSE_BUDGET'
    PAUSE_FAILURES = 'PAUSE_FAILURES'
    FAIL_CIRCUIT = 'FAIL_CIRCUIT'


@dataclass(frozen=True)
class BudgetUsage:
    """某一时刻的预算水位（进度事件与决策共用同一份快照）。"""

    rounds: int = 0
    tool_calls: int = 0
    tokens: int = 0
    elapsed_seconds: float = 0.0
    output_bytes: int = 0
    limits: Dict[str, int] = field(default_factory=dict)
    consecutive_failures: int = 0

    def dimension(self, key: str) -> int:
        """单个维度的实际用量（``key`` 是 RunBudget 的键）。"""
        return int({
            'max_rounds': self.rounds,
            'max_tool_calls': self.tool_calls,
            'max_tokens': self.tokens,
            'max_duration_seconds': self.elapsed_seconds,
            'max_output_bytes': self.output_bytes,
        }[key])

    def ratios(self) -> Dict[str, float]:
        """每个已启用维度的消耗比（limit ≤ 0 表示该维度不启用，不参与）。"""
        ratios: Dict[str, float] = {}
        for key in _DIMENSION_KEYS:
            limit = int(self.limits.get(key) or 0)
            if limit <= 0:
                continue
            ratios[key] = float(self.dimension(key)) / float(limit)
        return ratios

    @property
    def max_ratio(self) -> float:
        """最高消耗比（暂停判定用；无启用维度时为 0）。"""
        ratios = self.ratios()
        return max(ratios.values()) if ratios else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'rounds': self.rounds,
            'tool_calls': self.tool_calls,
            'tokens': self.tokens,
            'elapsed_seconds': round(float(self.elapsed_seconds), 3),
            'output_bytes': self.output_bytes,
        }


@dataclass(frozen=True)
class AutoControlState:
    """从事件流重建的 Auto 控制状态（暂停 / 用户继续 / 空转次数）。

    - ``paused``：最后一条控制事件是 ``run_paused``（未被 ``run_resumed`` 覆盖）；
    - ``budget_pause_acked``：用户已对「预算暂停」点过继续 —— 本 run 不再因
      预算比例暂停，硬预算仍生效；
    - ``failures_acked``：继续时的连续失败数（同一失败连击不重复暂停）；
    - ``idle_nudges``：已经发出的「空转提示」次数（重启后继续累加）。
    """

    paused: bool = False
    pause_reason: str = ''
    budget_pause_acked: bool = False
    failures_acked: int = 0
    idle_nudges: int = 0
    # 用户刚点「继续」、此后还没跑过任何一轮：首轮要补一次 resume 提示
    pending_resume: bool = False

    @classmethod
    def from_events(cls, events: Sequence[Any]) -> 'AutoControlState':
        """按 sequence 顺序重放控制事件（``events`` 已是升序）。"""
        paused = False
        pause_reason = ''
        budget_acked = False
        failures_acked = 0
        nudges = 0
        pending_resume = False
        for event in events:
            payload = getattr(event, 'payload', None) or {}
            event_type = getattr(event, 'type', None)
            if event_type is EventType.RUN_PAUSED:
                paused = True
                pending_resume = False
                pause_reason = str(payload.get('reason') or '')
            elif event_type is EventType.RUN_RESUMED:
                paused = False
                # 用户点了「继续」：预算暂停点视为已确认（默认 True，
                # 恢复事件本身就是确认动作）。
                budget_acked = bool(payload.get('acked_budget_pause', True))
                failures_acked = max(
                    failures_acked, int(payload.get('consecutive_failures') or 0))
                pending_resume = True
            elif event_type is EventType.AUTO_STEP:
                if payload.get('phase') == PHASE_CONTINUE:
                    nudges += 1
                # 已经跑过一轮：resume 提示不再补（避免每轮都自称「刚继续」）
                pending_resume = False
            elif event_type in _SUBSTANTIVE_EVENTS:
                pending_resume = False
        return cls(paused=paused, pause_reason=pause_reason,
                   budget_pause_acked=budget_acked,
                   failures_acked=failures_acked, idle_nudges=nudges,
                   pending_resume=pending_resume)


class AutoModeController:
    """停止条件判定 + Auto 提示词 / 进度载荷生成（纯函数式）。"""

    def __init__(self, settings: Optional[AutoSettings] = None):
        self._settings = settings or AutoSettings()

    @property
    def settings(self) -> AutoSettings:
        return self._settings

    # ------------------------------------------------------------ 决策

    def preflight(self, *, usage: BudgetUsage,
                  control: AutoControlState) -> Optional[AutoAction]:
        """发起下一次模型调用前的判定（硬预算仍由 Loop 的 RunBudget 负责）。

        返回 ``None`` 表示可以继续；否则返回要执行的停止动作。
        """
        settings = self._settings
        failures = int(usage.consecutive_failures or 0)
        if settings.max_consecutive_failures > 0 \
                and failures >= settings.max_consecutive_failures:
            return AutoAction.FAIL_CIRCUIT
        if settings.pause_consecutive_failures > 0 \
                and failures >= settings.pause_consecutive_failures \
                and failures > control.failures_acked:
            return AutoAction.PAUSE_FAILURES
        if settings.pause_budget_ratio > 0 \
                and usage.max_ratio >= settings.pause_budget_ratio \
                and not control.budget_pause_acked:
            return AutoAction.PAUSE_BUDGET
        return None

    def after_turn(self, *, text: str, has_tool_calls: bool,
                   control: AutoControlState) -> AutoAction:
        """模型一轮结束后的判定：工具调用继续；纯文本看完成标记 / 空转。"""
        if has_tool_calls:
            return AutoAction.CONTINUE
        if self.is_complete(text):
            return AutoAction.COMPLETE
        if control.idle_nudges >= max(0, self._settings.max_idle_turns):
            return AutoAction.COMPLETE_IDLE
        return AutoAction.CONTINUE

    def is_complete(self, text: str) -> bool:
        marker = (self._settings.complete_marker or '').strip()
        return bool(marker) and marker in (text or '')

    def plan_digest(self, text: str) -> str:
        """把模型的一段文本压成计划摘要（scratchpad / 进度事件用）。"""
        raw = ' '.join(str(text or '').split())
        limit = max(0, int(self._settings.plan_max_chars))
        if limit and len(raw) > limit:
            return raw[:limit] + '…'
        return raw

    def idle_exhausted(self, control: AutoControlState) -> bool:
        return control.idle_nudges >= max(0, self._settings.max_idle_turns)

    # ------------------------------------------------------------ 提示词

    def system_prompt(self, budget: RunBudget) -> str:
        """Auto 模式的系统提示块（拼在基础 system_prompt 之后，永不压缩）。"""
        marker = self._settings.complete_marker
        return (
            '## Auto 模式（无人值守）\n'
            '- 用户消息里的任务就是目标：自主、连续推进直到完成，不要反问用户。\n'
            '- 第一步先给出简要计划（分步、可验证），之后每轮只推进当前步，'
            '并在需要时调用工具把结果落成真实数据。\n'
            '- 只依据工具返回的真实数据回答，不编造对象 ID、数值与指标。\n'
            '- 写操作会进入人工审批（WRITE 计划级批量、DESTRUCTIVE 单条）；'
            '等待审批不是失败，不要重复提交同一写操作。\n'
            f'- 目标全部达成时，在最后一条文本里单独输出完成标记 {marker}，'
            '并列出关键产物；没有该标记时系统会要求你继续。\n'
            f'- 预算：轮次 {budget.max_rounds} / 工具调用 {budget.max_tool_calls} / '
            f'时长 {budget.max_duration_seconds}s / 输出 {budget.max_output_bytes} 字节；'
            f'消耗到 {int(self._settings.pause_budget_ratio * 100)}% 或连续 '
            f'{self._settings.pause_consecutive_failures} 次工具失败时会被暂停，'
            '等待用户确认继续。'
        )

    def instruction(self, *, goal: str, step: int, usage: BudgetUsage,
                    phase: str = PHASE_CONTINUE,
                    pause_reason: str = '') -> str:
        """续跑提示（作为该轮 user 消息回灌，保证方向不漂移）。"""
        marker = self._settings.complete_marker
        head = (f'用户已确认继续（Auto 第 {step} 步）。'
                f'此前暂停原因：{pause_reason}。'
                if phase == PHASE_RESUME
                else f'继续推进目标（Auto 第 {step} 步）。')
        budget = (f'当前预算：轮次 {usage.rounds}/{usage.limits.get("max_rounds", 0)}、'
                  f'工具 {usage.tool_calls}/{usage.limits.get("max_tool_calls", 0)}、'
                  f'token {usage.tokens}/{usage.limits.get("max_tokens", 0)}、'
                  f'时长 {int(usage.elapsed_seconds)}s/'
                  f'{usage.limits.get("max_duration_seconds", 0)}s。')
        tail = (f'请从中断处继续：要么调用下一步工具，要么在目标已完成时输出 {marker} '
                '并列出产物。不要重复已完成的写操作。')
        return f'{head}\n目标：{goal}\n{budget}\n{tail}'

    # ------------------------------------------------------------ 进度

    def progress_payload(self, *, step: int, turn: int, phase: str,
                         goal: str, plan: str, usage: BudgetUsage,
                         artifacts: Sequence[Dict[str, Any]] = (),
                         instruction: Optional[str] = None,
                         pause_reason: str = '') -> Dict[str, Any]:
        """一条 ``auto_step`` 事件载荷（进度时间线 + 续跑提示合一）。"""
        ratios = usage.ratios()
        payload: Dict[str, Any] = {
            'mode': 'auto',
            'step': int(step),
            'turn': int(turn),
            'phase': phase,
            'goal': goal,
            'plan': plan,
            'usage': usage.to_dict(),
            'limits': dict(usage.limits),
            'ratios': {key: round(value, 4) for key, value in ratios.items()},
            'ratio': round(usage.max_ratio, 4),
            'consecutive_failures': int(usage.consecutive_failures or 0),
            'artifact_count': len(artifacts),
            'artifacts': list(artifacts),
        }
        if instruction:
            payload['instruction'] = instruction
        if pause_reason:
            payload['pause_reason'] = pause_reason
        return payload

    def scratchpad(self, *, goal: str, step: int, turn: int, plan: str,
                   usage: BudgetUsage, artifacts: Sequence[Dict[str, Any]] = (),
                   control: Optional[AutoControlState] = None) -> Dict[str, Any]:
        """计划 / 进度草稿（落 ``agent_step.plan_snapshot.scratchpad``）。

        长任务恢复时 L4_REBUILD 直接从这里读「当前计划」，不依赖模型复述。
        """
        control = control or AutoControlState()
        ratios = usage.ratios()
        return {
            'mode': 'auto',
            'goal': goal,
            'plan': plan,
            'step': int(step),
            'turn': int(turn),
            'usage': usage.to_dict(),
            'ratio': round(usage.max_ratio, 4),
            'slowest_dimension': (
                max(ratios, key=ratios.get) if ratios else ''),
            'consecutive_failures': int(usage.consecutive_failures or 0),
            'artifact_count': len(artifacts),
            'budget_pause_acked': bool(control.budget_pause_acked),
            'idle_nudges': int(control.idle_nudges),
        }


def consecutive_failures(tool_calls: Any, run_id: str, limit: int) -> int:
    """最近一段连续的失败 / 拒绝工具调用数（熔断与暂停共用同一口径）。

    ``limit`` 是熔断阈值：只回看 ``limit + 1`` 条就够了（再多也不会改变
    「是否达阈值」的结论），避免长 run 每次决策都扫全表。
    """
    count = 0
    for call in tool_calls.recent(run_id, max(1, int(limit)) + 1):
        if call.status in (ToolCallStatus.FAILED, ToolCallStatus.DENIED):
            count += 1
        else:
            break
    return count


def artifact_brief(artifacts: Sequence[Any], limit: int = 10) -> List[Dict[str, str]]:
    """产物的对外摘要（进度事件用；不含正文）。"""
    items: List[Dict[str, str]] = []
    for artifact in list(artifacts)[-max(1, limit):]:
        items.append({
            'id': str(getattr(artifact, 'id', '') or ''),
            'kind': str(getattr(artifact, 'kind', '') or ''),
            'uri': str(getattr(artifact, 'uri', '') or ''),
        })
    return items


__all__ = [
    'AutoAction', 'AutoControlState', 'AutoModeController', 'AutoSettings',
    'BudgetUsage', 'COMPLETE_REASON', 'IDLE_REASON', 'PAUSE_REASON_BUDGET',
    'PAUSE_REASON_FAILURES', 'PHASE_CONTINUE', 'PHASE_RESUME', 'PHASE_STEP',
    'artifact_brief', 'consecutive_failures',
]
