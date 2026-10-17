# -*- coding: utf-8 -*-
"""评估策略 ACL 仓储实现 — 委托 grpc_proxies 实现（INT-590）。

所有方法委托 grpc_proxies 单例完成 gRPC 调用，将返回的
{success, message, data, code} 信封封装为 CommandResultDTO。
"""
from __future__ import annotations

from api_gateway.domain.dto.api_gateway_acl_dto import CommandResultDTO
from api_gateway.domain.repositories.acl.evaluation_strategy_acl_repository import (
    EvaluationStrategyAclRepository,
)


def _wrap(result) -> CommandResultDTO:
    """将 gRPC 返回的信封 dict 封装为 CommandResultDTO。"""
    if isinstance(result, dict):
        return CommandResultDTO(
            success=result.get('success', False),
            message=result.get('message'),
            data=result.get('data'),
            code=result.get('code'),
        )
    return CommandResultDTO(success=False, data=result)


class EvaluationStrategyAclRepositoryImpl(EvaluationStrategyAclRepository):
    """task_service.EvaluationStrategyService 实体 ACL 实现。"""

    def create(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import evaluation_strategy_service
        return _wrap(evaluation_strategy_service.create(data))

    def update(self, strategy_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import evaluation_strategy_service
        return _wrap(evaluation_strategy_service.update(strategy_id, data))

    def delete(self, strategy_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import evaluation_strategy_service
        return _wrap(evaluation_strategy_service.delete(strategy_id))

    def list_strategies(self, **kwargs) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import evaluation_strategy_service
        return _wrap(evaluation_strategy_service.list_strategies(**kwargs))

    def get_strategy(self, strategy_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import evaluation_strategy_service
        return _wrap(evaluation_strategy_service.get_strategy(strategy_id))
