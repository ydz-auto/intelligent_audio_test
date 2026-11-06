# -*- coding: utf-8 -*-
"""task_service.EvaluationStrategyService 跨域 ACL 仓储接口（INT-590）。

所有方法返回 CommandResultDTO，封装 gRPC 信封 {success, message, data, code}。
策略实体归 task_service（用例域）：整体评估维度+全局背景噪声抽为可复用策略。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from api_gateway.domain.dto.api_gateway_acl_dto import CommandResultDTO


class EvaluationStrategyAclRepository(ABC):
    """task_service.EvaluationStrategyService 实体 ACL 接口。"""

    # ---- 写操作 ----
    @abstractmethod
    def create(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update(self, strategy_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete(self, strategy_id) -> CommandResultDTO: ...

    # ---- 读操作 ----
    @abstractmethod
    def list_strategies(self, **kwargs) -> CommandResultDTO: ...

    @abstractmethod
    def get_strategy(self, strategy_id) -> CommandResultDTO: ...
