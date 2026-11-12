# -*- coding: utf-8 -*-
"""上下文组装（落地方案 §5.1 第 1 步）。

数据来源是 agent_run_event（唯一事实源），因此进程重启后可以原样重建：
- run_started.payload.user_message → user 消息
- message_delta（按 message_id 拼接）→ assistant 文本
- tool_call / tool_result（按 tool_call_id 配对）→ assistant tool_calls + tool 消息

只回灌**完整轮次**（有 tool_call 的轮次必须所有结果都已落库）；中断时未产生
结果的轮次整段丢弃，由模型重新规划 —— 这样恢复时不会把已执行的工具再跑一遍。
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from agent_service.domain.enums import EventType, LlmMessageRole, RunStatus
from agent_service.domain.model.entities import AgentRun, LlmMessage
from agent_service.domain.repositories import EventRepository, RunRepository

logger = logging.getLogger(__name__)


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
                 max_messages: int = 120, event_fetch_limit: int = 10000):
        self._events = events
        self._runs = runs
        self._system_prompt = system_prompt or ''
        self._max_runs = max(1, int(max_runs))
        self._max_messages = max(4, int(max_messages))
        self._event_fetch_limit = max(1, int(event_fetch_limit))

    def assemble(self, session_id: str, run: AgentRun) -> List[LlmMessage]:
        """组装本次模型调用的完整消息列表（system + 历史 + 当前轮）。"""
        messages: List[LlmMessage] = []
        if self._system_prompt:
            messages.append(LlmMessage(
                role=LlmMessageRole.SYSTEM.value, content=self._system_prompt))
        history_runs = self._runs.list_session_runs(session_id, self._max_runs)
        if run.id not in {r.id for r in history_runs}:
            history_runs.append(run)
        for item in history_runs:
            if item.status is RunStatus.QUEUED:
                # 尚未执行过的 run 只有 run_started，仍保留用户输入
                pass
            messages.extend(self._messages_for_run(item))
        return self._trim(messages)

    def recent_messages(self, session_id: str, run: Optional[AgentRun],
                        limit: int) -> List[dict]:
        """会话最近消息（GET session 展示用，不含 system）。"""
        if run is None:
            return []
        runs = self._runs.list_session_runs(session_id, self._max_runs)
        return self.recent_session_messages(runs, limit)

    def recent_session_messages(self, runs, limit: int) -> List[dict]:
        """跨 run 汇总最近消息（会话历史由 DB 保证完整，§8.1）。"""
        messages: List[LlmMessage] = []
        for item in runs[-self._max_runs:]:
            messages.extend(self._messages_for_run(item))
        return [
            {'role': m.role, 'content': m.content,
             'tool_call_id': m.tool_call_id}
            for m in messages[-max(1, limit):]
        ]

    # ------------------------------------------------------------ internals

    def _messages_for_run(self, run: AgentRun) -> List[LlmMessage]:
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

        messages: List[LlmMessage] = []
        if user_message:
            messages.append(LlmMessage(
                role=LlmMessageRole.USER.value, content=user_message))
        for number in sorted(turns):
            turn = turns[number]
            if not turn.complete:
                continue
            text = ''.join(chunk for _i, _mid, chunk in sorted(turn.deltas))
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
            if not text and not tool_calls:
                continue
            messages.append(LlmMessage(
                role=LlmMessageRole.ASSISTANT.value,
                content=text or None,
                tool_calls=tool_calls,
            ))
            for call_id in turn.calls:
                result = turn.results.get(call_id) or {}
                content = result.get('content')
                if content is None:
                    content = json.dumps(result, ensure_ascii=False)
                messages.append(LlmMessage(
                    role=LlmMessageRole.TOOL.value,
                    content=str(content),
                    tool_call_id=call_id,
                ))
        return messages

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
