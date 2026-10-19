# -*- coding: utf-8 -*-
"""人工复核路由（INT-340）+ AI 复核路由（INT-824）。

前缀 /tasks/results（挂载：app.py include_router(review_router, prefix='/api/v1/tasks/results')）。

权限点（seed_rbac.py INT-340 新增）：task.result.review 人工复核提交；
查询侧（计数/历史）对齐任务列表口径放行 task:read（覆盖提醒与历史展示即读任务结果）。
AI 复核（INT-800/INT-824）：发起/驳回 task.result.ai_review（新码，seed_rbac 注册），
历史 task:read，采纳 task.result.review（衔接权威改判，对齐设计 §6）。

入口对齐设计文档 §2：任务执行详情模态窗结果列表「人工复核」操作 + 结果详情页。
"""
from fastapi import APIRouter

from api_gateway.application.services.task.review_service import ReviewService
from api_gateway.application.services.task.ai_review_service import AiReviewService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission

router = APIRouter()


@router.post('/review')
def submit_review(_: None = require_permission('task.result.review')):
    return to_response(ReviewService.submit_review())


@router.get('/{task_id}/review-count')
def review_count(task_id: int, _: None = require_permission('task:read')):
    return to_response(ReviewService.review_count(task_id))


@router.get('/{task_id}/review-history')
def review_history(task_id: int, _: None = require_permission('task:read')):
    return to_response(ReviewService.review_history(task_id))


# ==================== AI 复核（INT-800/INT-824） ====================

@router.post('/ai-review')
def initiate_ai_review(_: None = require_permission('task.result.ai_review')):
    """发起 AI 复核：{result_ids:[int]≥1, dimension_ids?:[int], force?:boolean}。"""
    return to_response(AiReviewService.initiate_review())


@router.get('/{task_id}/ai-review-history')
def ai_review_history(task_id: int, _: None = require_permission('task:read')):
    """任务 AI 复核历史（时间倒序；Query 可选 result_id/dimension_id/status）。"""
    return to_response(AiReviewService.review_history(task_id))


@router.post('/ai-review/{id}/adopt')
def adopt_ai_review(id: int, _: None = require_permission('task.result.review')):
    """采纳 AI 复核结论（预填评估状态 + 备注=AI 理由，人工确认提交）。"""
    return to_response(AiReviewService.adopt_review(id))


@router.post('/ai-review/{id}/reject')
def reject_ai_review(id: int, _: None = require_permission('task.result.ai_review')):
    """驳回 AI 复核结论（原判定不变）。"""
    return to_response(AiReviewService.reject_review(id))
