# -*- coding: utf-8 -*-
"""AI 复核 ACL 仓储实现（INT-824）——委托 AI 复核 gRPC 代理。"""
from __future__ import annotations

from typing import Optional

from api_gateway.domain.dto import CommandResultDTO
from api_gateway.domain.repositories.acl.ai_review_acl_repository import AiReviewAclRepository


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


class AiReviewAclRepositoryImpl(AiReviewAclRepository):
    """task_service.ReviewService（AI 复核方法）ACL 实现。"""

    def initiate_review(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import ai_review_proxy
        return _wrap(ai_review_proxy.initiate_review(data))

    def list_ai_review_history(self, task_id, filters: Optional[dict] = None) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import ai_review_proxy
        return _wrap(ai_review_proxy.list_ai_review_history(task_id, filters or {}))

    def adopt_review(self, review_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import ai_review_proxy
        return _wrap(ai_review_proxy.adopt_review(review_id, data))

    def reject_review(self, review_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import ai_review_proxy
        return _wrap(ai_review_proxy.reject_review(review_id))
