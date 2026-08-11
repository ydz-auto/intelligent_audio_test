# -*- coding: utf-8 -*-
"""会话仓储抽象接口（ABC）

DDD 规则3：Repository 必须继承 ABC。本模块定义领域层的仓储抽象接口，
infrastructure/persistence/session_repository.py 提供具体实现（SessionRepository）。

抽象方法签名与具体实现保持一致，确保上层通过依赖注入使用接口，
不直接依赖 SessionStore 实现。

会话仓储作为 AdapterSession 聚合根的持久化接口，
委托给 SessionStore 单例完成实际内存存储。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # 避免循环引用，仅用于类型注解
    from api_adapter_service.domain.entities import AdapterSession


class SessionRepositoryABC(ABC):
    """会话仓储抽象接口。

    将领域聚合根 AdapterSession 与已有的 SessionStore（dict 形式）
    进行相互转换，保持领域层纯逻辑。
    """

    @abstractmethod
    def ensure_session(
        self,
        session_id: str,
        task_id: str,
        context_mode: str = 'full',
        max_history_rounds: int = 10,
        session_timeout: int = 60,
    ) -> 'AdapterSession':
        """获取或创建会话聚合根。"""

    @abstractmethod
    def get(self, session_id: str) -> Optional['AdapterSession']:
        """按 ID 读取会话聚合根。"""

    @abstractmethod
    def add_round(
        self,
        session_id: str,
        round_idx: int,
        input_text: str,
        output_text: str,
        latency: float,
    ) -> None:
        """追加一轮对话（委托 session_store）。"""

    @abstractmethod
    def get_context(self, session_id: str) -> list:
        """获取会话上下文历史。"""

    @abstractmethod
    def get_round_results(self, session_id: str) -> list:
        """获取会话全部轮次结果。"""

    @abstractmethod
    def destroy(self, session_id: str) -> None:
        """销毁会话。"""

    @abstractmethod
    def count(self) -> int:
        """活跃会话数。"""
