# -*- coding: utf-8 -*-
"""evaluation_service.EvaluationService ACL 仓储 — gRPC 实现。"""
from __future__ import annotations

from api_test_service.domain.repositories.acl.evaluation_acl_repository import (
    EvaluationAclRepository,
)


class EvaluationAclRepositoryImpl(EvaluationAclRepository):
    """evaluation_service.EvaluationService 跨域调用 gRPC 实现。"""

    def submit_evaluate_case(self, task_id, result_id, test_case_id,
                             algorithm_result, eval_params) -> bool:
        from shared.clients.grpc_clients import submit_evaluate_case as _submit
        _submit(
            task_id=task_id,
            result_id=result_id,
            test_case_id=test_case_id,
            algorithm_result=algorithm_result,
            eval_params=eval_params,
        )
        return True
