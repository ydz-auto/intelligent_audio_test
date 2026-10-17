# -*- coding: utf-8 -*-
"""评估策略写操作 Service（CQRS Command Side，INT-590）。

按 DDD 原则，网关只做 Pydantic 校验 + gRPC 调用，不直接操作 DB。
RBAC 复用 testcase:read / testcase:update（策略归用例域）。
"""
import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.infrastructure.acl import EvaluationStrategyAclRepositoryImpl
from api_gateway.schemas.common import StringIdData
from api_gateway.schemas.evaluation_strategy import (
    EvaluationStrategyCreateSchema,
    EvaluationStrategyUpdateSchema,
)

logger = logging.getLogger(__name__)

_evaluation_strategy_acl = EvaluationStrategyAclRepositoryImpl()


class EvaluationStrategyCommandService:
    """评估策略写操作 Service（CQRS Command Side）。"""

    # 创建评估策略
    @staticmethod
    def create():
        try:
            data = EvaluationStrategyCreateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}")

        data_dict = data.model_dump(by_alias=False, exclude_none=True)

        result = _evaluation_strategy_acl.create(data_dict)

        if not result.get('success'):
            code = result.get('code', 500)
            return error_response(result.get('message', '创建评估策略失败'), code=code)

        new_id = (result.get('data') or {}).get('id')
        return success_response(StringIdData(id=new_id), result.get('message', '评估策略创建成功'), http_code=201)

    # 更新评估策略（P1 不回灌已引用用例）
    @staticmethod
    def update(strategy_id):
        try:
            data = EvaluationStrategyUpdateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}")

        data_dict = data.model_dump(by_alias=False, exclude_none=True)

        result = _evaluation_strategy_acl.update(strategy_id, data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到评估策略", 404)
            return error_response(result.get('message', '更新失败'), code=code)

        return success_response(result.get('data'), result.get('message', '评估策略更新成功'))

    # 删除评估策略（被用例引用时拒绝并返回引用数）
    @staticmethod
    def delete(strategy_id):
        result = _evaluation_strategy_acl.delete(strategy_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到评估策略", 404)
            if code == 409:
                # 被引用拒绝：detail 返回引用数供前端提示二次确认
                data = result.get('data') or {}
                return error_response(
                    result.get('message', '策略被用例引用，无法删除'),
                    code=409,
                    http_code=409,
                    detail={'referenced_case_count': data.get('referenced_case_count', 0)},
                )
            return error_response(result.get('message', '删除失败'), code=code)

        return success_response(None, result.get('message', '评估策略已删除'))
