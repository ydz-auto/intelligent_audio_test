# -*- coding: utf-8 -*-
"""幂等仓储端口 — 用例批量操作幂等去重（INT-75）。

应用层经此端口做重复提交判定与响应回放；Redis 实现见
task_service/infrastructure/persistence/idempotency_store.py。
"""
from abc import ABC, abstractmethod
from typing import Optional


class IdempotencyRepositoryABC(ABC):
    """幂等键仓储抽象：占位、回放与释放。"""

    @abstractmethod
    def lookup(self, key: str) -> Optional[dict]:
        """查询幂等记录。

        Returns:
            记录 dict（{'status': 'completed', 'response': {...}} 或
            {'status': 'processing'}）；无记录或存储不可用返回 None。
        """

    @abstractmethod
    def reserve(self, key: str, ttl_seconds: int) -> bool:
        """原子占位幂等键（不存在时写入 processing 占位并设 TTL）。

        Returns:
            True 表示占位成功（或存储不可用降级放行）；False 表示已被占位。
        """

    @abstractmethod
    def complete(self, key: str, response: dict, ttl_seconds: int) -> None:
        """执行成功后写入完整响应，供 TTL 窗口内重复提交回放。"""

    @abstractmethod
    def release(self, key: str) -> None:
        """释放占位（执行失败时调用），允许客户端重试。"""
