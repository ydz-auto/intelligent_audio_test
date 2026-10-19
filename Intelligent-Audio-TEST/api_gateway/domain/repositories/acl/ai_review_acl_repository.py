# -*- coding: utf-8 -*-
"""AI 复核 ACL 仓储接口（INT-824）：task_service.ReviewService（AI 复核方法）抽象契约。"""
from abc import ABC, abstractmethod
from typing import Optional

from api_gateway.domain.dto import CommandResultDTO


class AiReviewAclRepository(ABC):
    """task_service AI 复核（发起/历史/采纳/驳回）ACL 接口。"""

    @abstractmethod
    def initiate_review(self, data) -> CommandResultDTO:
        """发起 AI 复核（result_ids + dimension_ids? + force? → items/reused/skipped）。"""

    @abstractmethod
    def list_ai_review_history(self, task_id, filters: Optional[dict]) -> CommandResultDTO:
        """任务 AI 复核历史（时间倒序；result_id/dimension_id/status 可选过滤）。"""

    @abstractmethod
    def adopt_review(self, review_id, data) -> CommandResultDTO:
        """采纳 AI 复核结论（复用 apply_review 落人工复核语义）。"""

    @abstractmethod
    def reject_review(self, review_id) -> CommandResultDTO:
        """驳回 AI 复核结论（原判定不变）。"""
