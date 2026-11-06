# -*- coding: utf-8 -*-
"""E2E 测试仓储抽象接口（ABC）

DDD 规则3：Repository 必须继承 ABC。本模块定义领域层的仓储抽象接口，
infrastructure/persistence/e2e_repository.py 提供具体实现（E2ETestRepository）。

E2ETestRepository 为单例（通过 __new__ 实现），抽象接口仅声明业务方法，
不影响单例语义。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:  # 避免循环引用，仅用于类型注解
    from e2e_test_service.domain.entities import E2ETestSession


class E2ETestRepositoryABC(ABC):
    """E2E 测试仓储抽象接口。

    提供对 E2ETestSession 运行时状态的读取与保存能力。
    """

    @abstractmethod
    def get_status(self, task_id: str) -> Optional['E2ETestSession']:
        """获取任务的运行时状态，返回 E2ETestSession 聚合根。

        Returns:
            E2ETestSession 或 None（任务不存在时）。
        """

    @abstractmethod
    def get_round_progress(self, task_id: str) -> Dict:
        """获取任务的轮次进度。

        返回原始进度字典（跨聚合的值对象），由上层自行解释。
        """

    @abstractmethod
    def save_status(self, task_id: str, status: Dict):
        """保存任务状态（委托给 e2e_service 内部 _task_status）。

        注意：e2e_service 内部通过 _task_status 字典维护状态，
        本方法保持向后兼容，直接写回状态字典。
        """
