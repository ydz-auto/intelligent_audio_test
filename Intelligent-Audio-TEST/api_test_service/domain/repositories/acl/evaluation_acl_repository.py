# -*- coding: utf-8 -*-
"""evaluation_service.EvaluationService 跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class EvaluationAclRepository(ABC):
    """evaluation_service.EvaluationService 跨域调用接口。"""

    @abstractmethod
    def submit_evaluate_case(self, task_id, result_id, test_case_id,
                             algorithm_result, eval_params) -> bool:
        """提交单条用例评估请求（EvaluateCase）。"""
        ...
