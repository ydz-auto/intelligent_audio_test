# -*- coding: utf-8 -*-
"""AI 复核 Schema（INT-824/INT-800）——网关入参校验契约 + AiReviewRecordDto 形状。

对齐契约定稿（父卡 INT-800 审计评论 §二）：
- 发起 POST /tasks/results/ai-review：{result_ids:[int]≥1, dimension_ids?:[int], force?:boolean}
- 历史 GET /tasks/results/{task_id}/ai-review-history：Query result_id/dimension_id/status 可选
- 采纳 POST /tasks/results/ai-review/{id}/adopt：{execution_status?, evaluation_status?, comment:str}
- 驳回 POST /tasks/results/ai-review/{id}/reject：{}

可改判状态复用人工复核同口径（shared/utils/status_constants.py REVIEWABLE_*）。
"""
from typing import List, Optional

from pydantic import BaseModel, Field

from api_gateway.schemas.base import APIModel

# 业务码 → HTTP 状态码映射（后端 data.code 透传语义，对齐 INT-141 F2 口径）
_CODE_HTTP_MAP = {400: 400, 401: 401, 404: 404, 500: 500}

# 可改判状态全集（与人工复核 review.py 同口径）
_REVIEWABLE_EXECUTION_STATUSES = frozenset({'completed', 'failed', 'stopped', 'skipped'})
_REVIEWABLE_EVALUATION_STATUSES = frozenset({'completed', 'failed'})


class AiReviewInitiateRequest(BaseModel):
    """发起 AI 复核请求（POST /tasks/results/ai-review）。"""
    result_ids: List[int] = Field(..., min_length=1, description='执行结果 ID 集合（≥1）')
    dimension_ids: Optional[List[int]] = Field(None, description='复核维度（缺省=结果已完成评估的 LLM 判分维度）')
    force: Optional[bool] = Field(False, description='true 绕过幂等复用，新建记录重新执行')


class AiReviewAdoptRequest(BaseModel):
    """采纳 AI 复核请求（POST /tasks/results/ai-review/{id}/adopt）。"""
    execution_status: Optional[str] = Field(None, description='执行状态改判（completed/failed/stopped/skipped）')
    evaluation_status: Optional[str] = Field(None, description='评估状态改判（completed/failed）')
    comment: str = Field(..., min_length=1, description='复核备注（必填，预填 AI 理由后人工确认）')

    def validate_statuses(self) -> Optional[str]:
        """校验改判状态枚举（与人工复核同口径，返回错误消息或 None）。"""
        if self.execution_status and self.execution_status not in _REVIEWABLE_EXECUTION_STATUSES:
            return f'执行状态不可改判: {self.execution_status}（仅限 completed/failed/stopped/skipped）'
        if self.evaluation_status and self.evaluation_status not in _REVIEWABLE_EVALUATION_STATUSES:
            return f'评估状态不可改判: {self.evaluation_status}（仅限 completed/failed）'
        if not self.execution_status and not self.evaluation_status:
            return '执行状态/评估状态至少设置一项'
        return None


class AiReviewRecordDto(BaseModel):
    """AI 复核记录 DTO（契约定稿表 ai_reviews 全字段，出参透传形状）。"""
    id: int
    result_id: int
    task_id: int
    test_case_id: Optional[str] = None
    dimension_id: Optional[int] = None
    status: str
    verdict: Optional[str] = None
    confidence: Optional[float] = None
    reasoning: Optional[str] = None
    adopted: int = 0
    adopted_by_user_id: Optional[int] = None
    adopted_at: Optional[str] = None
    rejected: int = 0
    rejected_by_user_id: Optional[int] = None
    rejected_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
