# -*- coding: utf-8 -*-
"""AI 复核 BFF Service（INT-824）——网关侧 ACL 编排。

CQRS：命令侧（发起/采纳/驳回）经 ACL 下发写命令；查询侧只读（历史）。
所有方法返回 (payload, http_code) 元组（对齐网关路由层 to_response 约定）。

契约（父卡 INT-800 审计评论 §二）：出参统一信封 {success,message,data}，
data 透传 task_service 返回形状（AiReviewRecordDto 列表 / reused / skipped 等）。
"""
from __future__ import annotations

import logging

from api_gateway.infrastructure.acl import AiReviewAclRepositoryImpl
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.schemas.ai_review import (
    AiReviewInitiateRequest, AiReviewAdoptRequest, _CODE_HTTP_MAP,
)

logger = logging.getLogger(__name__)

_ai_review_acl = AiReviewAclRepositoryImpl()

# 历史查询可选过滤参数白名单（对齐契约定稿 Query）
_HISTORY_FILTER_KEYS = ('result_id', 'dimension_id', 'status')


class AiReviewService:
    """AI 复核 BFF Service（命令/查询经 ACL 下发，网关不触 DB）。"""

    @staticmethod
    def initiate_review():
        try:
            req = AiReviewInitiateRequest.model_validate(request.get_json() or {})
        except Exception as e:
            return error_response(f"数据验证失败: {e}")
        payload = req.model_dump(exclude_none=True)
        result = _ai_review_acl.initiate_review(payload)
        if not result.get('success'):
            return error_response(result.get('message', 'AI 复核发起失败'),
                                  http_code=_CODE_HTTP_MAP.get(result.get('code'), 400))
        return success_response(result.get('data') or {}, result.get('message', 'AI 复核已发起'))

    @staticmethod
    def review_history(task_id):
        # 查询参数转 filters（字符串直传，task_service 侧 int/枚举校验；空值过滤）
        params = request.args.to_dict()
        filters = {k: v for k, v in params.items()
                   if k in _HISTORY_FILTER_KEYS and v not in (None, '')}
        result = _ai_review_acl.list_ai_review_history(task_id, filters)
        if not result.get('success'):
            return error_response(result.get('message', 'AI 复核历史查询失败'),
                                  http_code=_CODE_HTTP_MAP.get(result.get('code'), 400))
        return success_response(result.get('data') or {})

    @staticmethod
    def adopt_review(review_id):
        try:
            req = AiReviewAdoptRequest.model_validate(request.get_json() or {})
        except Exception as e:
            return error_response(f"数据验证失败: {e}")
        err = req.validate_statuses()
        if err:
            return error_response(err, http_code=_CODE_HTTP_MAP.get(400, 400))
        payload = {
            'execution_status': req.execution_status,
            'evaluation_status': req.evaluation_status,
            'comment': req.comment,
        }
        result = _ai_review_acl.adopt_review(review_id, payload)
        if not result.get('success'):
            return error_response(result.get('message', 'AI 复核采纳失败'),
                                  http_code=_CODE_HTTP_MAP.get(result.get('code'), 400))
        return success_response(result.get('data') or {}, result.get('message', '已采纳 AI 复核结论'))

    @staticmethod
    def reject_review(review_id):
        result = _ai_review_acl.reject_review(review_id)
        if not result.get('success'):
            return error_response(result.get('message', 'AI 复核驳回失败'),
                                  http_code=_CODE_HTTP_MAP.get(result.get('code'), 400))
        return success_response(result.get('data') or {}, result.get('message', 'AI 复核已驳回，原判定不变'))
