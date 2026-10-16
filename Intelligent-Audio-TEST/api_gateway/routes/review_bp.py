# -*- coding: utf-8 -*-
"""人工复核路由（INT-340）。

前缀 /tasks/results（挂载：app.py include_router(review_router, prefix='/api/v1/tasks/results')）。

权限点（seed_rbac.py INT-340 新增）：task.result.review 人工复核提交；
查询侧（计数/历史）对齐任务列表口径放行 task:read（覆盖提醒与历史展示即读任务结果）。

入口对齐设计文档 §2：任务执行详情模态窗结果列表「人工复核」操作 + 结果详情页。
"""
from fastapi import APIRouter

from api_gateway.application.services.task.review_service import ReviewService
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
