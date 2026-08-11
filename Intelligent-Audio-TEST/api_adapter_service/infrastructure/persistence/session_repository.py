# -*- coding: utf-8 -*-
"""会话仓储：包装已有的 services/session_store.py。

作为 AdapterSession 聚合根的持久化接口，
委托给 SessionStore 单例完成实际内存存储。
"""

from typing import Optional

from api_adapter_service.domain.entities import AdapterSession
from api_adapter_service.domain.repositories.session_repository_abc import (
    SessionRepositoryABC,
)
from api_adapter_service.services.session_store import session_store


class SessionRepository(SessionRepositoryABC):
    """会话仓储。

    将领域聚合根 AdapterSession 与已有的 SessionStore（dict 形式）
    进行相互转换，保持领域层纯逻辑。
    """

    def ensure_session(
        self,
        session_id: str,
        task_id: str,
        context_mode: str = 'full',
        max_history_rounds: int = 10,
        session_timeout: int = 60,
    ) -> AdapterSession:
        """获取或创建会话聚合根。"""
        session_store.ensure_session(
            session_id=session_id,
            task_id=task_id,
            context_mode=context_mode,
            max_history_rounds=max_history_rounds,
            session_timeout=session_timeout,
        )
        return self.get(session_id)

    def get(self, session_id: str) -> Optional[AdapterSession]:
        """按 ID 读取会话聚合根。"""
        data = session_store.get_session(session_id)
        if data is None:
            return None
        return AdapterSession.from_dict(data)

    def add_round(
        self,
        session_id: str,
        round_idx: int,
        input_text: str,
        output_text: str,
        latency: float,
    ) -> None:
        """追加一轮对话（委托 session_store）。"""
        session_store.add_round(
            session_id=session_id,
            round_idx=round_idx,
            input_text=input_text,
            output_text=output_text,
            latency=latency,
        )

    def get_context(self, session_id: str) -> list:
        """获取会话上下文历史。"""
        return session_store.get_context(session_id)

    def get_round_results(self, session_id: str) -> list:
        """获取会话全部轮次结果。"""
        return session_store.get_round_results(session_id)

    def destroy(self, session_id: str) -> None:
        """销毁会话。"""
        session_store.destroy_session(session_id)

    def count(self) -> int:
        """活跃会话数。"""
        return session_store.get_session_count()


# 单例
session_repository = SessionRepository()
