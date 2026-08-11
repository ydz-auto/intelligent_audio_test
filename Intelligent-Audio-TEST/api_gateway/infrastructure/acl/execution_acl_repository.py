# -*- coding: utf-8 -*-
"""execution_engine ACL 仓储 — 委托 grpc_proxies 实现。

委托现有 execution_engine 单例完成 gRPC 调用，对返回的 (success, message)
tuple / bool 负载转换为 ExecutionResultDTO。
"""
from __future__ import annotations

import logging

from api_gateway.domain.dto import ExecutionResultDTO
from api_gateway.domain.repositories.acl.execution_acl_repository import (
    ExecutionAclRepository,
)

logger = logging.getLogger(__name__)


class ExecutionAclRepositoryImpl(ExecutionAclRepository):
    """execution_engine 跨域 ACL 实现。"""

    def start_task(self, app, task_id) -> ExecutionResultDTO:
        from api_gateway.infrastructure.grpc_proxies import execution_engine
        success, message = execution_engine.start_task(app, task_id)
        return ExecutionResultDTO(
            success=success,
            message=message,
            result_data={'success': success, 'message': message},
        )

    def control_task(self, app, task_id, action) -> ExecutionResultDTO:
        from api_gateway.infrastructure.grpc_proxies import execution_engine
        success, message = execution_engine.control_task(app, task_id, action)
        return ExecutionResultDTO(
            success=success,
            message=message,
            result_data={'success': success, 'message': message},
        )

    def remove_from_queue(self, task_id) -> ExecutionResultDTO:
        from api_gateway.infrastructure.grpc_proxies import execution_engine
        success = execution_engine.remove_from_queue(task_id)
        return ExecutionResultDTO(
            success=success,
            result_data={'success': success},
        )
