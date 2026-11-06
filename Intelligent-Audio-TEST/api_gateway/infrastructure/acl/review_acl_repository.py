# -*- coding: utf-8 -*-
"""人工复核 ACL 仓储实现（INT-340）——委托 review gRPC 代理。"""
from __future__ import annotations

from api_gateway.domain.dto import CommandResultDTO
from api_gateway.domain.repositories.acl.review_acl_repository import ReviewAclRepository


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


class ReviewAclRepositoryImpl(ReviewAclRepository):
    """task_service.ReviewService 人工复核 ACL 实现。"""

    def submit_review(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import review_service
        return _wrap(review_service.submit_review(data))

    def get_review_count(self, task_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import review_service
        return _wrap(review_service.get_review_count(task_id))

    def list_review_history(self, task_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import review_service
        return _wrap(review_service.list_review_history(task_id))
