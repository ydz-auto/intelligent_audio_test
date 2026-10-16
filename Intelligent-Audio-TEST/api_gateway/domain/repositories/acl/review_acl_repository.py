# -*- coding: utf-8 -*-
"""人工复核 ACL 仓储接口（INT-340）：task_service.ReviewService 抽象契约。"""
from abc import ABC, abstractmethod

from api_gateway.domain.dto import CommandResultDTO


class ReviewAclRepository(ABC):
    """task_service.ReviewService 人工复核 ACL 接口。"""

    @abstractmethod
    def submit_review(self, data) -> CommandResultDTO:
        """复核提交（单条/批量改判执行/评估状态 + 备注必填）。"""

    @abstractmethod
    def get_review_count(self, task_id) -> CommandResultDTO:
        """覆盖提醒计数：任务下已复核结果条数。"""

    @abstractmethod
    def list_review_history(self, task_id) -> CommandResultDTO:
        """任务复核历史（多次复核追加不覆盖）。"""
