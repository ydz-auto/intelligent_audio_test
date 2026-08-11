# -*- coding: utf-8 -*-
"""reevaluation executor ACL 仓储 — 委托 grpc_proxies 实现。

委托现有 _ReevaluationExecutorProxy 单例完成 gRPC 调用，对返回的
(success, message) tuple 负载转换为 ReevaluationResultDTO。
"""
from __future__ import annotations

import logging

from api_gateway.domain.dto import ReevaluationResultDTO
from api_gateway.domain.repositories.acl.reevaluation_acl_repository import (
    ReevaluationAclRepository,
)

logger = logging.getLogger(__name__)


class ReevaluationAclRepositoryImpl(ReevaluationAclRepository):
    """_ReevaluationExecutorProxy 跨域 ACL 实现。"""

    def submit(self, task_id, reextract_device_output=True,
               reevaluate_type='all') -> ReevaluationResultDTO:
        from api_gateway.infrastructure.grpc_proxies import _ReevaluationExecutorProxy
        executor = _ReevaluationExecutorProxy.get_instance()
        success, message = executor.submit(
            task_id,
            reextract_device_output=reextract_device_output,
            reevaluate_type=reevaluate_type,
        )
        return ReevaluationResultDTO(
            success=success,
            message=message,
            result_data={'success': success, 'message': message},
        )

    def reevaluate_multi_round(self, task_id, result, test_case_id,
                               algorithm_result, test_type,
                               algorithm_type) -> ReevaluationResultDTO:
        from api_gateway.infrastructure.grpc_proxies import _ReevaluationExecutorProxy
        executor = _ReevaluationExecutorProxy.get_instance()
        success, message = executor._reevaluate_multi_round(
            task_id, result, test_case_id, algorithm_result,
            test_type, algorithm_type,
        )
        return ReevaluationResultDTO(
            success=success,
            message=message,
            result_data={'success': success, 'message': message},
        )

    def reevaluate_single(self, task_id, result_id, test_case_id,
                          algorithm_result, reference_params, test_type,
                          algorithm_type) -> ReevaluationResultDTO:
        from api_gateway.infrastructure.grpc_proxies import _ReevaluationExecutorProxy
        executor = _ReevaluationExecutorProxy.get_instance()
        success, message = executor._reevaluate_single(
            task_id, result_id, test_case_id, algorithm_result,
            reference_params, test_type, algorithm_type,
        )
        return ReevaluationResultDTO(
            success=success,
            message=message,
            result_data={'success': success, 'message': message},
        )
