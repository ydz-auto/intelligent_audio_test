# -*- coding: utf-8 -*-
"""重新评估执行器跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from api_gateway.domain.dto import ReevaluationResultDTO


class ReevaluationAclRepository(ABC):
    """_ReevaluationExecutorProxy 跨域 ACL 仓储接口。

    封装 evaluation_service EvaluationService 的重新评估调用，
    返回 ReevaluationResultDTO（不再返回 raw (success, message) tuple）。
    """

    @abstractmethod
    def submit(self, task_id, reextract_device_output=True,
               reevaluate_type='all') -> ReevaluationResultDTO:
        ...

    @abstractmethod
    def reevaluate_multi_round(self, task_id, result, test_case_id,
                               algorithm_result, test_type,
                               algorithm_type) -> ReevaluationResultDTO:
        ...

    @abstractmethod
    def reevaluate_single(self, task_id, result_id, test_case_id,
                          algorithm_result, reference_params, test_type,
                          algorithm_type) -> ReevaluationResultDTO:
        ...
