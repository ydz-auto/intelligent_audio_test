# -*- coding: utf-8 -*-
"""人工复核 BFF Service（INT-340）——网关侧 ACL 编排。

CQRS：命令侧（复核提交）经 ACL 下发写命令；查询侧只读（计数/历史）。
所有方法返回 (payload, http_code) 元组（对齐网关路由层 to_response 约定）。
"""
from __future__ import annotations

import logging

from api_gateway.infrastructure.acl import ReviewAclRepositoryImpl
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.schemas.review import ReviewSubmitRequest, _CODE_HTTP_MAP

logger = logging.getLogger(__name__)

_review_acl = ReviewAclRepositoryImpl()


class ReviewService:
    """人工复核 BFF Service（命令/查询经 ACL 下发，网关不触 DB）。"""

    @staticmethod
    def submit_review():
        try:
            req = ReviewSubmitRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {e}")
        err = req.validate_statuses()
        if err:
            return error_response(err, http_code=_CODE_HTTP_MAP.get(400, 400))
        payload = {
            'result_ids': req.result_ids,
            'execution_status': req.execution_status,
            'evaluation_status': req.evaluation_status,
            'comment': req.comment,
        }
        result = _review_acl.submit_review(payload)
        if not result.get('success'):
            return error_response(result.get('message', '复核提交失败'),
                                  http_code=_CODE_HTTP_MAP.get(result.get('code'), 400))
        return success_response(result.get('data') or {}, result.get('message', '复核已提交'))

    @staticmethod
    def review_count(task_id):
        result = _review_acl.get_review_count(task_id)
        if not result.get('success'):
            return error_response(result.get('message', '复核计数查询失败'))
        return success_response(result.get('data') or {})

    @staticmethod
    def review_history(task_id):
        result = _review_acl.list_review_history(task_id)
        if not result.get('success'):
            return error_response(result.get('message', '复核历史查询失败'))
        return success_response(result.get('data') or {})
