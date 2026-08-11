# -*- coding: utf-8 -*-
"""领域实体：AdapterSession 聚合根 + DialogRound 实体。

补充导出 session 模块对外可见的会话聚合根概念（SessionAggregate /
Message / SessionSnapshot / SessionStatus），与运行期 AdapterSession 并存，
互不冲突——二者分属不同子模块。
"""

import time
from dataclasses import dataclass, field
from typing import List

from api_adapter_service.domain.value_objects import RoundResult

# 追加 re-export：对外可见的会话聚合根概念（不覆盖 AdapterSession）
from api_adapter_service.domain.entities.session import (  # noqa: F401,E402
    Message,
    SessionAggregate,
    SessionSnapshot,
    SessionStatus,
)


@dataclass
class DialogRound:
    """对话轮次实体。"""
    round: int
    input_text: str = ''
    output_text: str = ''
    latency: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @classmethod
    def from_result(cls, round_idx: int, result: RoundResult) -> 'DialogRound':
        """从 RoundResult 构建实体。"""
        return cls(
            round=round_idx,
            input_text=result.asr_text,
            output_text=result.output,
            latency=result.latency,
        )

    def to_dict(self) -> dict:
        return {
            'round': self.round,
            'input': self.input_text,
            'output': self.output_text,
            'latency': self.latency,
            'timestamp': self.timestamp,
        }


class AdapterSession:
    """会话聚合根。

    聚合内实体：DialogRound 列表。
    聚合内不变式：rounds 顺序、context_history 一致性。
    """

    def __init__(
        self,
        session_id: str,
        task_id: str,
        context_mode: str = 'full',
        max_history_rounds: int = 10,
        session_timeout: int = 60,
    ):
        self.session_id = session_id
        self.task_id = task_id
        self.context_mode = context_mode
        self.max_history_rounds = max_history_rounds
        self.session_timeout = session_timeout
        self.created_at = time.time()
        self.last_active = time.time()
        self.status = 'active'
        self._rounds: List[DialogRound] = []
        self._context_history: list = []

    # ── Round 管理 ──────────────────────────────────────────

    def add_round(self, round_entity: DialogRound) -> None:
        """添加一轮对话，同时维护 context_history。"""
        if self.status != 'active':
            raise RuntimeError(
                f'Cannot add round to non-active session: {self.session_id}'
            )
        self._rounds.append(round_entity)
        self._context_history.append(
            {'role': 'user', 'content': round_entity.input_text}
        )
        self._context_history.append(
            {'role': 'assistant', 'content': round_entity.output_text}
        )
        self.last_active = time.time()

    def add_round_result(self, round_idx: int, result: RoundResult) -> DialogRound:
        """便捷方法：从结果构建轮次并添加。"""
        round_entity = DialogRound.from_result(round_idx, result)
        self.add_round(round_entity)
        return round_entity

    def get_rounds(self) -> List[DialogRound]:
        return list(self._rounds)

    def get_context(self) -> list:
        """获取下一轮请求的上下文历史。"""
        if self.context_mode == 'sliding_window':
            max_messages = self.max_history_rounds * 2
            if len(self._context_history) > max_messages:
                return list(self._context_history[-max_messages:])
        return list(self._context_history)

    # ── 状态管理 ──────────────────────────────────────────────

    def close(self) -> None:
        """关闭会话。"""
        self.status = 'closed'

    def destroy(self) -> None:
        """销毁会话。"""
        self.status = 'destroyed'
        self._rounds.clear()
        self._context_history.clear()

    def is_expired(self) -> bool:
        """是否超时。"""
        return (time.time() - self.last_active) > self.session_timeout * 1.5

    # ── 序列化（供基础设施层使用）──────────────────────────────

    def to_dict(self) -> dict:
        return {
            'session_id': self.session_id,
            'task_id': self.task_id,
            'context_mode': self.context_mode,
            'max_history_rounds': self.max_history_rounds,
            'session_timeout': self.session_timeout,
            'context_history': list(self._context_history),
            'round_results': [r.to_dict() for r in self._rounds],
            'created_at': self.created_at,
            'last_active': self.last_active,
            'status': self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AdapterSession':
        """从 dict（如 SessionStore 的记录）重建聚合根。"""
        session = cls(
            session_id=data['session_id'],
            task_id=data.get('task_id', ''),
            context_mode=data.get('context_mode', 'full'),
            max_history_rounds=data.get('max_history_rounds', 10),
            session_timeout=data.get('session_timeout', 60),
        )
        session.created_at = data.get('created_at', session.created_at)
        session.last_active = data.get('last_active', session.last_active)
        session.status = data.get('status', 'active')
        for r in data.get('round_results', []):
            session._rounds.append(
                DialogRound(
                    round=r.get('round', 0),
                    input_text=r.get('input', ''),
                    output_text=r.get('output', ''),
                    latency=r.get('latency', 0),
                    timestamp=r.get('timestamp', time.time()),
                )
            )
        session._context_history = list(data.get('context_history', []))
        return session
