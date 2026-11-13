# -*- coding: utf-8 -*-
"""上下文组装 + 无感压缩 L1–L3（落地方案 §5.1 / §8）。

数据来源是 ``agent_run_event``（唯一事实源），因此进程重启后可以原样重建：

- ``run_started.payload.user_message`` → user 消息
- ``message_delta``（按 message_id 拼接）→ assistant 文本
- ``tool_call`` / ``tool_result``（按 tool_call_id 配对）→ assistant tool_calls + tool 消息

只回灌**完整轮次**（有 tool_call 的轮次必须所有结果都已落库）；中断时未产生
结果的轮次整段丢弃，由模型重新规划 —— 这样恢复时不会把已执行的工具再跑一遍。

压缩层级（§8.2）：

- ``L1_TRIM``：工具结果统一为「摘要 + 关键字段 + artifact 引用」，超限截断，
  大结果落对象存储（``ArtifactStore``，生产实现复用 OSS 客户端）；
- ``L2_DEDUPE``：相同查询去重，列表只留计数 + TopN + 查询入口；
- ``L3_MEMO``：旧对话压成固定 schema（目标 / 约束 / 已确认事实带来源 ID /
  决策 / 产物 / 未决问题 / 下一步），调用 LLM；失败回退 L1。

永不压缩清单（§8.4）：系统不变量与安全规则、当前激活 Skill 正文、计划与用户
约束（user 消息）、审批状态、artifact 索引、最近 N 轮原文。压缩只影响模型
上下文，数据库事件始终完整（§8.1）。

每次实际压缩写一条 ``agent_context_snapshot``（版本 / token 数 / 被裁消息 ID /
备忘 / 触发层级），并追加 ``context_compacted`` 事件；调试模式会在事件里带上
完整的被裁消息 ID 与备忘，供回放。
"""
import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from agent_service.application.skill_registry import SkillRegistry
from agent_service.domain.enums import (
    CompactionLevel, EventType, LlmMessageRole,
)
from agent_service.domain.exceptions import RunCancelled
from agent_service.domain.model.context_budget import ContextBudget, ContextSection
from agent_service.domain.model.entities import (
    AgentArtifact, AgentContextSnapshot, AgentRun, LlmMessage,
)
from agent_service.domain.ports.artifact_store import (
    ArtifactStore, NullArtifactStore,
)
from agent_service.domain.repositories import (
    ArtifactRepository, ContextSnapshotRepository, EventRepository,
    RunRepository,
)
from agent_service.domain.services.token_estimator import estimate_message_tokens
from shared.utils.time_utils import utcnow

logger = logging.getLogger(__name__)

# L3 备忘的固定 schema（§8.2）；模型必须按这些键输出
MEMO_KEYS = (
    'goal', 'constraints', 'facts', 'decisions', 'artifacts',
    'open_questions', 'next_steps',
)

# 备忘 / 摘要消息的标题前缀（同时用于调试识别）
MEMO_PREFIX = '[上下文备忘 L3]'
L1_PREFIX = '[L1 摘要]'
L2_PREFIX = '[L2 去重]'
LIST_NOTE_KEY = 'list_compaction'

TOOL_RESULT_ARTIFACT_KIND = 'context_tool_result'

# 列表结果里可能承载数据的键（按顺序取第一个命中）
_LIST_KEYS = ('items', 'results', 'data', 'list', 'rows')

MemoSummarizer = Callable[[Sequence[Dict[str, Any]]], Optional[Dict[str, Any]]]


@dataclass
class CompactionSettings:
    """压缩行为参数（全部来自配置，不在代码里写死）。"""

    enabled: bool = True
    keep_recent_turns: int = 3
    tool_summary_chars: int = 600
    max_summary_chars: int = 2400
    artifact_threshold_chars: int = 4000
    list_top_n: int = 5
    list_trim_threshold_chars: int = 1200
    max_key_fields: int = 24
    # L3 防抖动：可压缩消息不足时不重复调模型（超过模型窗口时强制压缩）
    memo_min_candidates: int = 6
    approval_error_codes: Tuple[str, ...] = ('APPROVAL_REQUIRED',)
    # 对象存储上传的有界等待：OSS 不可用时快速降级为截断，不拖住模型 Loop
    artifact_store_timeout_seconds: float = 10.0
    debug: bool = False


@dataclass
class ContextMessage:
    """带身份与来源的模型消息（压缩需要消息 ID / 工具名 / 参数）。"""

    message_id: str
    run_id: str
    turn: int
    role: str
    content: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Tuple[Dict[str, Any], ...] = ()
    tool: Optional[str] = None
    tool_arguments: Optional[Dict[str, Any]] = None
    approval: bool = False
    pinned: bool = False

    @property
    def token_count(self) -> int:
        return estimate_message_tokens(
            self.content,
            list(self.tool_calls) if self.tool_calls else None)

    def to_llm(self) -> LlmMessage:
        return LlmMessage(
            role=self.role, content=self.content,
            tool_call_id=self.tool_call_id, tool_calls=self.tool_calls)


@dataclass
class CompactionOutcome:
    """一次压缩的结果（事件 / 快照 / 测试共用）。"""

    level: CompactionLevel
    tokens_before: int
    tokens_after: int
    dropped_ids: List[str] = field(default_factory=list)
    memo: Dict[str, Any] = field(default_factory=dict)
    version: Optional[int] = None


@dataclass
class _Turn:
    number: int
    deltas: List[tuple] = field(default_factory=list)   # (index, message_id, text)
    calls: Dict[str, dict] = field(default_factory=dict)  # tool_call_id -> payload
    results: Dict[str, dict] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        if self.calls:
            return set(self.calls) <= set(self.results)
        return bool(self.deltas)


class ContextAssembler:
    def __init__(self, events: EventRepository, runs: RunRepository, *,
                 system_prompt: str = '', max_runs: int = 20,
                 max_messages: int = 120, event_fetch_limit: int = 10000,
                 skills: Optional[SkillRegistry] = None,
                 snapshots: Optional[ContextSnapshotRepository] = None,
                 artifacts: Optional[ArtifactRepository] = None,
                 artifact_store: Optional[ArtifactStore] = None,
                 settings: Optional[CompactionSettings] = None):
        self._events = events
        self._runs = runs
        self._system_prompt = system_prompt or ''
        self._max_runs = max(1, int(max_runs))
        self._max_messages = max(4, int(max_messages))
        self._event_fetch_limit = max(1, int(event_fetch_limit))
        self._skills = skills
        self._snapshots = snapshots
        self._artifacts = artifacts
        self._artifact_store = artifact_store or NullArtifactStore()
        self._settings = settings or CompactionSettings()
        # run_id -> {artifact_id: uri}：避免每轮重建上下文时重复上传同一结果
        self._artifact_cache: Dict[str, Dict[str, str]] = {}

    # ------------------------------------------------------------ public

    def allowed_tools(self, permissions: Iterable[str],
                      active_skill: Optional[str]) -> Optional[frozenset]:
        """当前 run 的 Skill 工具白名单（§6.3 allowed-tools 交集）。

        - 未激活 Skill：返回 ``None``，表示不按 Skill 收窄（仅受用户权限约束）；
        - 激活 Skill 且可见：返回其 ``allowed-tools`` 集合（空集合 = 不装配工具）；
        - 激活 Skill 但不可见（未注册 / 权限不足）：返回空集合，不泄漏 Skill 内容。
        """
        if not active_skill or self._skills is None:
            return None
        skill = self._skills.get_visible(active_skill, permissions)
        if skill is None:
            return frozenset()
        return frozenset(skill.meta.allowed_tools)

    def assemble(self, session_id: str, run: AgentRun, *,
                 permissions: Iterable[str] = (),
                 active_skill: Optional[str] = None,
                 budget: Optional[ContextBudget] = None,
                 memo_summarizer: Optional[MemoSummarizer] = None
                 ) -> List[LlmMessage]:
        """组装本次模型调用的完整消息列表（system + 历史 + 当前轮）。

        ``budget`` 为空时不启用 token 压缩（仅按消息条数兜底），供 GET session
        展示等非模型调用路径复用。``memo_summarizer`` 为空时 L3 降级为 L1。
        """
        history_runs = self._runs.list_session_runs(session_id, self._max_runs)
        if run.id not in {r.id for r in history_runs}:
            history_runs.append(run)
        messages, system_content = self._collect(
            history_runs, permissions, active_skill)
        # 快照回放：L3 已把旧对话压成备忘，重建上下文时直接复用它，
        # 不再每次重新摘要（否则每轮都要调一次摘要模型）。
        replay = self._latest_memo_snapshot(history_runs)
        if replay is not None:
            dropped = set(replay.dropped_ids or ())
            messages = [m for m in messages if m.message_id not in dropped]
            if replay.memo:
                memo_text = f'{MEMO_PREFIX}\n' + json.dumps(
                    replay.memo, ensure_ascii=False, indent=1)
                system_content = (f'{system_content}\n\n{memo_text}'
                                  if system_content else memo_text)
        if system_content:
            messages.insert(0, ContextMessage(
                message_id='system', run_id=run.id, turn=-1,
                role=LlmMessageRole.SYSTEM.value,
                content=system_content, pinned=True))
        self._mark_pinned(messages)

        outcome = self._compact(
            messages, run, budget=budget, memo_summarizer=memo_summarizer)
        if outcome is not None:
            if (outcome.level is CompactionLevel.L3_MEMO
                    and replay is not None):
                # L3 快照的 dropped_ids 必须是累计值，才能单条回放
                outcome.dropped_ids = _dedupe_ids(
                    list(replay.dropped_ids or []) + outcome.dropped_ids)
            self._record_compaction(run, outcome)

        if budget is None:
            return self._trim([m.to_llm() for m in messages])
        return [m.to_llm() for m in messages]

    def recent_messages(self, session_id: str, run: Optional[AgentRun],
                        limit: int) -> List[dict]:
        """会话最近消息（GET session 展示用，不含 system；永不压缩）。"""
        if run is None:
            return []
        runs = self._runs.list_session_runs(session_id, self._max_runs)
        return self.recent_session_messages(runs, limit)

    def recent_session_messages(self, runs, limit: int) -> List[dict]:
        """跨 run 汇总最近消息（会话历史由 DB 保证完整，§8.1）。"""
        messages: List[LlmMessage] = []
        for item in runs[-self._max_runs:]:
            messages.extend(self._messages_for_run(item, 0)[0])
        return [
            {'role': m.role, 'content': m.content,
             'tool_call_id': m.tool_call_id}
            for m in (item.to_llm() for item in messages[-max(1, limit):])
        ]

    # ------------------------------------------------------------ assemble

    def _collect(self, history_runs: Sequence[AgentRun],
                 permissions: Iterable[str],
                 active_skill: Optional[str]
                 ) -> Tuple[List[ContextMessage], str]:
        messages: List[ContextMessage] = []
        next_turn = 0
        for item in history_runs:
            produced, next_turn = self._messages_for_run(item, next_turn)
            messages.extend(produced)
        system = self._system_content(permissions, active_skill, history_runs)
        return messages, system

    def _system_content(self, permissions: Iterable[str],
                        active_skill: Optional[str],
                        history_runs: Sequence[AgentRun] = ()) -> str:
        parts: List[str] = []
        if self._system_prompt:
            parts.append(self._system_prompt)
        if self._skills is not None:
            section = self._skills.system_section(permissions, active_skill)
            if section:
                parts.append(section)
        index = self._artifact_index(history_runs)
        if index:
            parts.append(index)
        return '\n\n'.join(parts)

    def _artifact_index(self, history_runs: Sequence[AgentRun]) -> str:
        """Artifact 索引（§8.4 永不压缩清单 5）：带来源 ID 与 URI。"""
        if self._artifacts is None or not history_runs:
            return ''
        lines: List[str] = []
        for item in history_runs:
            try:
                records = self._artifacts.list_by_run(item.id)
            except Exception:  # noqa: BLE001 - 索引读取失败不影响主流程
                logger.warning('读取 artifact 索引失败 run=%s', item.id,
                               exc_info=True)
                continue
            for artifact in records:
                lines.append(
                    f'- {artifact.id} | {artifact.kind} | {artifact.uri}')
        if not lines:
            return ''
        return '## 产物索引（永不压缩）\n' + '\n'.join(lines)

    # ------------------------------------------------------------ compaction

    def _compact(self, messages: List[ContextMessage], run: AgentRun, *,
                 budget: Optional[ContextBudget],
                 memo_summarizer: Optional[MemoSummarizer]
                 ) -> Optional[CompactionOutcome]:
        if not self._settings.enabled or budget is None:
            return None
        tokens_before = self._total_tokens(messages)
        if not budget.exceeds_soft(tokens_before):
            return None

        dropped: List[str] = []
        level: Optional[CompactionLevel] = None
        memo: Dict[str, Any] = {}
        l3_throttled = False

        # 先跑无 LLM 的 L2 / L1：工具结果收敛成「摘要 + 关键字段 + artifact」，
        # L3 摘要模型看到的就是紧凑文本，成本更低、关键字段不会因截断丢失。
        changed_l2, dropped_l2 = self._apply_l2(messages)
        if changed_l2:
            level = CompactionLevel.L2_DEDUPE
            dropped.extend(dropped_l2)
        changed_l1, dropped_l1 = self._apply_l1(messages, budget)
        if changed_l1:
            level = level or CompactionLevel.L1_TRIM
            dropped.extend(dropped_l1)

        # 硬触发再压 L3（旧对话成备忘）；失败回退 L1/L2
        if budget.exceeds_hard(self._total_tokens(messages)) \
                and memo_summarizer is not None:
            candidates = [m for m in messages
                          if not m.pinned
                          and m.role != LlmMessageRole.SYSTEM.value]
            force = tokens_before > budget.window
            if force or len(candidates) >= self._settings.memo_min_candidates:
                memo, dropped_l3 = self._apply_l3(messages, memo_summarizer)
                if memo is not None:
                    level = CompactionLevel.L3_MEMO
                    dropped.extend(dropped_l3)
            else:
                # 刚压过、增量太少：不重复调模型，等可压缩内容积累
                l3_throttled = True

        # L3 不可用 / 失败且仍然超硬阈值：按轮次整组裁剪（回退 L1）。
        # L3 被防抖动跳过时不能丢消息——那会在没有备忘的情况下丢失事实。
        if (not l3_throttled
                and budget.exceeds_hard(self._total_tokens(messages))):
            dropped_fallback = self._drop_oldest_groups(messages, budget)
            if dropped_fallback:
                level = level or CompactionLevel.L1_TRIM
                dropped.extend(dropped_fallback)

        if level is None:
            return None
        tokens_after = self._total_tokens(messages)
        return CompactionOutcome(
            level=level, tokens_before=tokens_before,
            tokens_after=tokens_after,
            dropped_ids=_dedupe_ids(dropped), memo=memo or {})

    def _apply_l1(self, messages: List[ContextMessage],
                  budget: ContextBudget
                  ) -> Tuple[bool, List[str]]:
        """L1_TRIM：工具结果超区段预算时转为摘要 + 关键字段 + artifact 引用。"""
        limit = budget.section_limit(ContextSection.TOOL_RESULTS)
        compressible = [m for m in messages
                        if m.role == LlmMessageRole.TOOL.value and not m.pinned]
        if not compressible:
            return False, []
        changed: List[str] = []
        # 先处理最大的结果，直到工具结果区段回到预算内
        for message in sorted(compressible, key=lambda m: m.token_count,
                              reverse=True):
            if limit > 0 and self._tokens_of(messages, LlmMessageRole.TOOL) \
                    <= limit:
                break
            if self._is_summarized(message.content):
                continue
            summarized = self._summarize_tool_result(message)
            if summarized is None or summarized == message.content:
                continue
            message.content = summarized
            changed.append(message.message_id)
        return bool(changed), changed

    def _apply_l2(self, messages: List[ContextMessage]
                  ) -> Tuple[bool, List[str]]:
        """L2_DEDUPE：相同查询**结果一致**才去重；列表只留计数 + TopN + 查询入口。

        只按「工具 + 参数」判重会把旧结果当权威：轮询类查询（同参数，状态从
        RUNNING 变 SUCCEEDED）会被替换成「结果一致，此处省略」，模型静默拿到
        陈旧事实。因此按分组比较结果内容：内容一致→保留首次；内容不同→保留
        最新一条，旧消息改为「结果已更新」并指向最新消息（§8.2 / §8.1）。
        """
        changed: List[str] = []
        groups: Dict[Tuple[str, str], List[ContextMessage]] = {}
        for message in messages:
            if message.role != LlmMessageRole.TOOL.value or message.pinned:
                continue
            key = (message.tool or '', _args_hash(message.tool_arguments))
            groups.setdefault(key, []).append(message)

        for (tool, args_hash), group in groups.items():
            if len(group) > 1:
                changed.extend(
                    self._dedupe_same_query(group, tool, args_hash))
            for message in group:
                trimmed, _note = self._trim_list_result(message)
                if trimmed is not None:
                    message.content = trimmed
                    changed.append(message.message_id)
        return bool(changed), changed

    @staticmethod
    def _dedupe_same_query(group: List[ContextMessage], tool: str,
                           args_hash: str) -> List[str]:
        """同工具同参数分组内去重：结果一致留首次，结果变化留最新。"""
        contents = [message.content or '' for message in group]
        same_result = all(item == contents[0] for item in contents[1:])
        if same_result:
            authority = group[0]
            note = (
                f'{L2_PREFIX} 与消息 {authority.message_id} 为相同查询'
                f'（工具 {tool}，参数摘要 {args_hash[:8]}），结果一致，'
                f'此处省略。完整结果可重新调用 {tool} 获取。')
            superseded = group[1:]
        else:
            # 结果发生变化：最新一次查询才是当前事实，旧结果不得当权威
            authority = group[-1]
            note = (
                f'{L2_PREFIX} 与消息 {authority.message_id} 为相同查询'
                f'（工具 {tool}，参数摘要 {args_hash[:8]}），但结果已更新，'
                f'此条为旧结果；最新结果以 {authority.message_id} 为准，'
                f'完整结果可重新调用 {tool} 获取。')
            superseded = group[:-1]
        changed: List[str] = []
        for message in superseded:
            message.content = note
            changed.append(message.message_id)
        return changed

    def _trim_list_result(self, message: ContextMessage
                          ) -> Tuple[Optional[str], bool]:
        content = message.content or ''
        if len(content) < max(0, self._settings.list_trim_threshold_chars):
            return None, False
        try:
            data = json.loads(content)
        except (TypeError, ValueError):
            return None, False
        if not isinstance(data, dict):
            return None, False
        for key in _LIST_KEYS:
            items = data.get(key)
            if isinstance(items, list) and len(items) > self._settings.list_top_n:
                total = len(items)
                data[key] = items[:self._settings.list_top_n]
                data[LIST_NOTE_KEY] = {
                    'total_count': total,
                    'returned_count': self._settings.list_top_n,
                    'note': (f'列表已压缩：共 {total} 条，仅保留前 '
                             f'{self._settings.list_top_n} 条；'
                             f'可重新调用 {message.tool} 获取完整列表'),
                }
                return json.dumps(data, ensure_ascii=False), True
        return None, False

    def _apply_l3(self, messages: List[ContextMessage],
                  memo_summarizer: MemoSummarizer
                  ) -> Tuple[Optional[Dict[str, Any]], List[str]]:
        """L3_MEMO：旧对话压成固定 schema；失败返回 (None, []) 由调用方回退。"""
        old = [m for m in messages
               if not m.pinned and m.role != LlmMessageRole.SYSTEM.value]
        if not old:
            return None, []
        payload = [
            {'message_id': m.message_id, 'role': m.role,
             'tool': m.tool, 'content': m.content or ''}
            for m in old
        ]
        # 上一次备忘必须参与本次摘要：否则每次 L3 只会看到最近几轮，
        # 更早的已确认事实会在第二次压缩时丢失（压缩必须可累加）。
        previous_memo = self._current_memo(messages)
        if previous_memo:
            payload.insert(0, {
                'message_id': 'system:memo', 'role': 'system',
                'tool': None, 'content': previous_memo})
        try:
            raw = memo_summarizer(payload)
            memo = _normalize_memo(raw)
        except RunCancelled:
            # 取消必须穿透压缩层，否则会吞掉用户取消
            raise
        except Exception:  # noqa: BLE001 - 摘要失败必须回退 L1
            logger.warning('L3 备忘生成失败，回退 L1', exc_info=True)
            return None, []
        if memo is None:
            return None, []
        old_ids = {m.message_id for m in old}
        messages[:] = [m for m in messages if m.message_id not in old_ids]
        memo_text = f'{MEMO_PREFIX}\n' + json.dumps(
            memo, ensure_ascii=False, indent=1)
        system = next((m for m in messages
                       if m.role == LlmMessageRole.SYSTEM.value), None)
        if system is not None:
            base, _previous = _split_memo(system.content or '')
            system.content = (f'{base}\n\n{memo_text}'.strip()
                              if base else memo_text)
        else:
            messages.insert(0, ContextMessage(
                message_id='system', run_id='', turn=-1,
                role=LlmMessageRole.SYSTEM.value, content=memo_text,
                pinned=True))
        return memo, sorted(old_ids)

    @staticmethod
    def _current_memo(messages: Sequence[ContextMessage]) -> str:
        """取出系统提示中的上一版备忘（供 L3 累加摘要）。"""
        system = next((m for m in messages
                       if m.role == LlmMessageRole.SYSTEM.value), None)
        if system is None:
            return ''
        _base, memo = _split_memo(system.content or '')
        return memo or ''

    def _drop_oldest_groups(self, messages: List[ContextMessage],
                            budget: ContextBudget) -> List[str]:
        """回退 L1：按轮次整组丢弃最旧的未固定消息（保持 tool 配对完整）。"""
        groups: Dict[int, List[ContextMessage]] = {}
        for message in messages:
            groups.setdefault(message.turn, []).append(message)
        if not groups:
            return []
        current_turn = max(groups)
        dropped: List[str] = []
        for turn in sorted(groups):
            group = groups[turn]
            if any(m.pinned for m in group):
                continue
            if turn == current_turn:
                break  # 当前轮永远保留
            for message in group:
                dropped.append(message.message_id)
            messages[:] = [m for m in messages if m.turn != turn]
            if not budget.exceeds_hard(self._total_tokens(messages)):
                break
        return dropped

    def _mark_pinned(self, messages: List[ContextMessage]) -> None:
        """标记永不压缩消息（§8.4）：
        系统提示 / 用户约束 / 最近 N 轮 / 审批状态所在轮次 / artifact 索引。
        """
        turns = sorted({m.turn for m in messages if m.turn >= 0})
        recent = set(turns[-max(1, self._settings.keep_recent_turns):])
        approval_turns = {m.turn for m in messages if m.approval}
        for message in messages:
            if message.role == LlmMessageRole.SYSTEM.value:
                message.pinned = True
            elif message.role == LlmMessageRole.USER.value:
                # 用户明确约束 / 目标：压缩后仍必须原样保留（§8.4-3）
                message.pinned = True
            elif message.turn in recent or message.turn in approval_turns:
                message.pinned = True

    # ------------------------------------------------------------ helpers

    def _messages_for_run(self, run: AgentRun,
                          start_turn: int) -> Tuple[List[ContextMessage], int]:
        events = self._events.list_after(run.id, 0, self._event_fetch_limit)
        user_message = ''
        turns: Dict[int, _Turn] = {}
        for event in events:
            payload = event.payload or {}
            if event.type is EventType.RUN_STARTED:
                user_message = payload.get('user_message') or ''
            elif event.type is EventType.MESSAGE_DELTA:
                turn = turns.setdefault(
                    int(payload.get('turn') or 0), _Turn(number=0))
                turn.deltas.append((
                    int(payload.get('index') or 0),
                    payload.get('message_id') or '',
                    payload.get('delta') or '',
                ))
            elif event.type is EventType.TOOL_CALL:
                turn = turns.setdefault(
                    int(payload.get('turn') or 0), _Turn(number=0))
                call_id = payload.get('tool_call_id')
                if call_id:
                    turn.calls[call_id] = payload
            elif event.type is EventType.TOOL_RESULT:
                turn = turns.setdefault(
                    int(payload.get('turn') or 0), _Turn(number=0))
                call_id = payload.get('tool_call_id')
                if call_id:
                    turn.results[call_id] = payload

        messages: List[ContextMessage] = []
        if user_message:
            messages.append(ContextMessage(
                message_id=f'user:{run.id}', run_id=run.id, turn=start_turn,
                role=LlmMessageRole.USER.value, content=user_message))
        next_turn = start_turn + 1
        for number in sorted(turns):
            turn = turns[number]
            if not turn.complete:
                continue
            text = ''.join(chunk for _i, _mid, chunk in sorted(turn.deltas))
            message_id = next(
                (mid for _i, mid, _c in sorted(turn.deltas) if mid),
                f'assistant:{run.id}:{number}')
            tool_calls = tuple(
                {
                    'id': call_id,
                    'type': 'function',
                    'function': {
                        'name': call.get('tool') or '',
                        'arguments': json.dumps(
                            call.get('arguments') or {}, ensure_ascii=False),
                    },
                }
                for call_id, call in turn.calls.items()
            )
            approval = any(
                (result or {}).get('error_code') in
                self._settings.approval_error_codes
                for result in turn.results.values())
            if not text and not tool_calls:
                continue
            messages.append(ContextMessage(
                message_id=message_id, run_id=run.id, turn=next_turn,
                role=LlmMessageRole.ASSISTANT.value,
                content=text or None, tool_calls=tool_calls,
                approval=approval))
            for call_id, call in turn.calls.items():
                result = turn.results.get(call_id) or {}
                content = result.get('content')
                if content is None:
                    content = json.dumps(result, ensure_ascii=False)
                messages.append(ContextMessage(
                    message_id=f'tool:{call_id}', run_id=run.id,
                    turn=next_turn, role=LlmMessageRole.TOOL.value,
                    content=str(content), tool_call_id=call_id,
                    tool=call.get('tool') or '',
                    tool_arguments=call.get('arguments') or {},
                    approval=approval))
            next_turn += 1
        return messages, next_turn

    def total_tokens(self, messages: Sequence[ContextMessage]) -> int:
        """供测试 / 观测使用：当前上下文 token 估算。"""
        return self._total_tokens(list(messages))

    @staticmethod
    def _total_tokens(messages: Sequence[ContextMessage]) -> int:
        return sum(m.token_count for m in messages)

    @staticmethod
    def _tokens_of(messages: Sequence[ContextMessage], role: str) -> int:
        return sum(m.token_count for m in messages if m.role == role)

    @staticmethod
    def _is_summarized(content: Optional[str]) -> bool:
        return bool(content) and content.startswith(L1_PREFIX)

    def _summarize_tool_result(self, message: ContextMessage
                               ) -> Optional[str]:
        """生成「摘要 + 关键字段 + artifact 引用」。"""
        content = message.content or ''
        if not content:
            return None
        artifact_uri = ''
        if (len(content) >= self._settings.artifact_threshold_chars
                and self._artifacts is not None):
            artifact_uri = self._store_artifact(content, message)
        fields = _key_fields(content, self._settings.max_key_fields)
        summary_body = _first_block(content, self._settings.tool_summary_chars)
        lines = [f'{L1_PREFIX} 工具 {message.tool or "-"} 结果已压缩：'
                 f'原始 {len(content)} 字符 / 约 {message.token_count} tokens。']
        if fields:
            lines.append('关键字段：' + '；'.join(fields))
        if summary_body:
            lines.append('摘要：' + summary_body)
        if artifact_uri:
            lines.append(f'artifact: {artifact_uri}（完整内容可回放）')
        lines.append(f'完整结果可重新调用 {message.tool or "该工具"} 获取。')
        summary = '\n'.join(lines)
        # 摘要本身也受单条上限约束（关键字段 / artifact 引用优先保留）
        return summary[:max(1, self._settings.max_summary_chars)]

    def _put_bounded(self, content: str, *, run_id: str, name: str) -> str:
        """有界等待对象存储上传：超时即抛错，由调用方降级为截断。"""
        timeout = max(0.1, float(
            self._settings.artifact_store_timeout_seconds))
        box: Dict[str, Any] = {}
        done = threading.Event()

        def worker() -> None:
            try:
                box['uri'] = self._artifact_store.put(
                    content, run_id=run_id, name=name)
            except BaseException as exc:  # noqa: BLE001 - 原样回抛
                box['error'] = exc
            finally:
                done.set()

        thread = threading.Thread(target=worker, name='agent-artifact',
                                  daemon=True)
        thread.start()
        if not done.wait(timeout):
            raise TimeoutError('对象存储上传超时')
        error = box.get('error')
        if error is not None:
            raise error
        return str(box.get('uri') or '')

    def _store_artifact(self, content: str,
                        message: ContextMessage) -> str:
        # 产物归属原工具结果所在的 run，artifact 索引按 run 列出时不会漏
        run_id = message.run_id
        artifact_id = _artifact_id(run_id, message.message_id)
        known = self._known_artifacts(run_id)
        if artifact_id in known:
            return known[artifact_id]
        name = f'{_safe_name(message.tool_call_id or message.message_id)}.json'
        try:
            uri = self._put_bounded(content, run_id=run_id, name=name)
        except Exception:  # noqa: BLE001 - 存储不可用降级为截断
            logger.warning('大工具结果外置失败，降级为截断 tool=%s',
                           message.tool, exc_info=True)
            return ''
        if self._artifacts is not None:
            try:
                self._artifacts.add(AgentArtifact(
                    id=artifact_id,
                    run_id=run_id, kind=TOOL_RESULT_ARTIFACT_KIND, uri=uri,
                    size=len(content.encode('utf-8')),
                    metadata={
                        'tool': message.tool,
                        'tool_call_id': message.tool_call_id,
                        'message_id': message.message_id,
                    },
                    created_at=utcnow()))
            except Exception as exc:  # noqa: BLE001 - 索引失败不丢内容
                # 保留静默降级（产物内容已在对象存储，索引缺一行不影响本轮）；
                # 但必须带 id 与异常类型可观测，避免落库系统性失败时完全无声。
                logger.warning('artifact 索引落库失败 run=%s id=%s error=%s: %s',
                               run_id, artifact_id, type(exc).__name__, exc,
                               exc_info=True)
        known[artifact_id] = uri
        return uri

    def _known_artifacts(self, run_id: str) -> Dict[str, str]:
        """run 内已知 artifact（id → uri）；首次按库预载，重启后不重复上传。"""
        known = self._artifact_cache.get(run_id)
        if known is None:
            known = {}
            if self._artifacts is not None:
                try:
                    for artifact in self._artifacts.list_by_run(run_id):
                        known[artifact.id] = artifact.uri
                except Exception:  # noqa: BLE001 - 预载失败按空缓存处理
                    logger.warning('artifact 预载失败 run=%s', run_id,
                                   exc_info=True)
            self._artifact_cache[run_id] = known
        return known

    # ------------------------------------------------------------ snapshot

    def _record_compaction(self, run: AgentRun,
                           outcome: CompactionOutcome) -> None:
        version = self._next_snapshot_version(run.id)
        outcome.version = version
        snapshot_id = _snapshot_id(run.id, version)
        if self._snapshots is not None:
            try:
                self._snapshots.add(AgentContextSnapshot(
                    id=snapshot_id, run_id=run.id,
                    version=version, token_count=outcome.tokens_after,
                    level=outcome.level,
                    dropped_ids=list(outcome.dropped_ids),
                    memo=dict(outcome.memo), created_at=utcnow()))
            except Exception as exc:  # noqa: BLE001 - 快照失败不阻断本轮模型调用
                # 同上：降级保留，但带 id / 层级 / 异常类型可观测。
                logger.warning(
                    '上下文快照落库失败 run=%s id=%s level=%s error=%s: %s',
                    run.id, snapshot_id, outcome.level.value,
                    type(exc).__name__, exc, exc_info=True)
        payload: Dict[str, Any] = {
            'level': outcome.level.value,
            'snapshot_version': version,
            'token_count_before': outcome.tokens_before,
            'token_count_after': outcome.tokens_after,
            'dropped_count': len(outcome.dropped_ids),
            'debug': bool(self._settings.debug),
        }
        if self._settings.debug:
            # 调试模式才下发被裁消息 ID / 备忘，供 UI 与回放使用（§8.5）
            payload['dropped_message_ids'] = list(outcome.dropped_ids)
            payload['memo'] = dict(outcome.memo)
        try:
            self._events.append(run.id, EventType.CONTEXT_COMPACTED, payload)
        except Exception:  # noqa: BLE001 - 事件写失败不阻断模型调用
            logger.warning('context_compacted 事件落库失败 run=%s', run.id,
                           exc_info=True)

    def _latest_memo_snapshot(self, history_runs: Sequence[AgentRun]):
        """会话内最近一条 L3 快照（用于重建上下文时回放备忘与裁剪）。"""
        if self._snapshots is None:
            return None
        for history_run in reversed(list(history_runs)):
            try:
                snapshots = self._snapshots.list_by_run(history_run.id)
            except Exception:  # noqa: BLE001 - 回放失败退回完整重建
                logger.warning('读取上下文快照失败 run=%s', history_run.id,
                               exc_info=True)
                continue
            for snapshot in reversed(snapshots):
                if snapshot.level is CompactionLevel.L3_MEMO:
                    return snapshot
        return None

    def _next_snapshot_version(self, run_id: str) -> int:
        if self._snapshots is None:
            return 1
        try:
            existing = self._snapshots.list_by_run(run_id)
        except Exception:  # noqa: BLE001
            return 1
        return (max((s.version for s in existing), default=0)) + 1

    # ------------------------------------------------------------ legacy

    def _trim(self, messages: List[LlmMessage]) -> List[LlmMessage]:
        if len(messages) <= self._max_messages:
            return messages
        head: List[LlmMessage] = []
        body = messages
        if body and body[0].role == LlmMessageRole.SYSTEM.value:
            head = [body[0]]
            body = body[1:]
        kept = body[-(self._max_messages - len(head)):]
        # 截断后开头不能是孤立的 tool 消息
        while kept and kept[0].role == LlmMessageRole.TOOL.value:
            kept = kept[1:]
        return head + kept


# ---------------------------------------------------------------- helpers

def _args_hash(arguments: Optional[Dict[str, Any]]) -> str:
    canonical = json.dumps(arguments or {}, sort_keys=True,
                           ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _dedupe_ids(ids: Iterable[str]) -> List[str]:
    seen: set = set()
    ordered: List[str] = []
    for item in ids:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _first_block(content: str, limit: int) -> str:
    text = ' '.join(content.split())
    if len(text) <= limit:
        return text
    return text[:max(0, limit)] + '…'


def _key_fields(content: str, limit: int) -> List[str]:
    """提取「关键字段」：JSON 的标量键值（含一层嵌套），最多 ``limit`` 个。"""
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        return []
    fields: List[str] = []

    def add(prefix: str, value: Any) -> None:
        if len(fields) >= limit:
            return
        if isinstance(value, (str, int, float, bool)) or value is None:
            fields.append(f'{prefix}={_short_value(value)}')

    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    add(f'{key}.{sub_key}', sub_value)
            else:
                add(str(key), value)
    elif isinstance(data, list):
        for index, value in enumerate(data[:limit]):
            add(f'[{index}]', value)
    return fields[:limit]


def _short_value(value: Any, limit: int = 80) -> str:
    text = json.dumps(value, ensure_ascii=False) \
        if not isinstance(value, str) else value
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit] + '…'


def _normalize_memo(raw: Optional[Dict[str, Any]]
                    ) -> Optional[Dict[str, Any]]:
    """校验 / 归一 L3 备忘固定 schema；结构不符视为失败（回退 L1）。"""
    if not isinstance(raw, dict):
        return None
    memo: Dict[str, Any] = {}
    for key in MEMO_KEYS:
        default: Any = '' if key == 'goal' else []
        value = raw.get(key, default)
        if key == 'goal':
            if not isinstance(value, str):
                return None
        elif not isinstance(value, list):
            return None
        memo[key] = value
    # 事实必须带来源 ID（§8.2 / §8.4）
    facts: List[Dict[str, Any]] = []
    for item in memo['facts']:
        if not isinstance(item, dict):
            return None
        if 'fact' not in item and 'value' not in item:
            return None
        source = item.get('source_id')
        if not source:
            return None
        facts.append({
            'fact': str(item.get('fact') or item.get('value')),
            'value': item.get('value'),
            'source_id': source,
        })
    memo['facts'] = facts
    return memo


def _split_memo(content: str) -> Tuple[str, str]:
    """把系统提示拆成「基础部分」与「L3 备忘块」。"""
    index = (content or '').find(MEMO_PREFIX)
    if index < 0:
        return content or '', ''
    return content[:index].rstrip('\n'), content[index:]


def _safe_name(value: str) -> str:
    keep = '-_.'
    return ''.join(ch if ch.isalnum() or ch in keep else '_'
                   for ch in (value or 'artifact'))[:120]


# 主键列全仓统一口径（agent_models._PK = String(36)）。生产 PG 上超长 insert 抛
# 「value too long for type character varying(36)」，而两个落库点都按「索引 / 快照
# 失败不阻塞本轮」降级 —— 超长会让两张表一条都写不进去（INT-2537）。
_PK_MAX_LEN = 36
_ARTIFACT_ID_PREFIX = 'art-'
_SNAPSHOT_ID_PREFIX = 'snap-'


def _artifact_id(run_id: str, message_id: str) -> str:
    """产物主键：同一 (run, message) 恒等（重启后据此去重），总长 ≤36。"""
    digest = hashlib.sha1(f'{run_id}:{message_id}'.encode('utf-8')).hexdigest()
    keep = _PK_MAX_LEN - len(_ARTIFACT_ID_PREFIX)
    return _ARTIFACT_ID_PREFIX + digest[:keep]


def _snapshot_id(run_id: str, version: int) -> str:
    """快照主键：同一 (run, version) 恒等，总长 ≤36。"""
    digest = hashlib.sha1(f'{run_id}:{version}'.encode('utf-8')).hexdigest()
    keep = _PK_MAX_LEN - len(_SNAPSHOT_ID_PREFIX)
    return _SNAPSHOT_ID_PREFIX + digest[:keep]


__all__ = [
    'CompactionOutcome', 'CompactionSettings', 'ContextAssembler',
    'ContextMessage', 'MEMO_KEYS', 'MEMO_PREFIX',
]
