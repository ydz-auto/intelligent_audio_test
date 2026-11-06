# -*- coding: utf-8 -*-
"""评估策略查询读侧 Service（CQRS Query Side，INT-590）。

网关侧只做参数提取 + gRPC 调用 + Pydantic 包装，不直接操作 DB。
策略列表返回 referenced_case_count（列表展示 + 删保护同源）。
"""
import logging

from pydantic import ValidationError

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.infrastructure.acl import EvaluationStrategyAclRepositoryImpl
from api_gateway.schemas.evaluation_strategy import (
    EvaluationStrategyConfig,
    EvaluationStrategyDetailData,
    EvaluationStrategyListData,
    EvaluationStrategyListItem,
    EvaluationStrategyListQuery,
)

logger = logging.getLogger(__name__)

_evaluation_strategy_acl = EvaluationStrategyAclRepositoryImpl()


def _parse_query_params(model_cls):
    """从 request.args 提取查询参数并通过 APIModel 校验"""
    params = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
    return model_cls.model_validate(params)


def _coerce_config(raw_config):
    """raw config dict → EvaluationStrategyConfig（维度条目结构化校验/回显）。"""
    if not raw_config:
        return EvaluationStrategyConfig()
    try:
        return EvaluationStrategyConfig.model_validate(raw_config)
    except Exception as e:
        logger.warning(f"评估策略 config 结构校验失败: {e}")
        return EvaluationStrategyConfig()


class EvaluationStrategyQueryService:
    """评估策略查询读侧 Service（CQRS Query Side）。"""

    @staticmethod
    def get_all():
        try:
            query = _parse_query_params(EvaluationStrategyListQuery)
        except ValidationError as e:
            return error_response(
                f"参数验证失败: {e}", code=ErrorCode.INVALID_PARAMS, http_code=422)

        result = _evaluation_strategy_acl.list_strategies(
            page=query.page,
            per_page=query.per_page,
            keyword=query.keyword,
            algorithm_type=query.algorithm_type,
            enabled=query.enabled,
        )

        if not result.get('success'):
            return error_response(result.get('message', '查询失败'))

        raw = result.get('data') or {}

        items = []
        for item in raw.get('items', []):
            items.append(
                EvaluationStrategyListItem(
                    id=item.get('id'),
                    name=item.get('name'),
                    description=item.get('description'),
                    algorithm_type=item.get('algorithm_type'),
                    enabled=item.get('enabled'),
                    config=_coerce_config(item.get('config')),
                    referenced_case_count=item.get('referenced_case_count', 0),
                    created_by_user_id=item.get('created_by_user_id'),
                    updated_by_user_id=item.get('updated_by_user_id'),
                    created_at=item.get('created_at'),
                    updated_at=item.get('updated_at'),
                )
            )

        return success_response(
            EvaluationStrategyListData(
                items=items,
                total=raw.get('total', 0),
                page=raw.get('page', query.page),
                per_page=raw.get('per_page', query.per_page),
                pages=raw.get('pages', 0),
            )
        )

    @staticmethod
    def get_one(strategy_id):
        result = _evaluation_strategy_acl.get_strategy(strategy_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到评估策略", 404)
            return error_response(result.get('message', '查询失败'))

        item = result.get('data') or {}

        return success_response(
            EvaluationStrategyDetailData(
                id=item.get('id'),
                name=item.get('name'),
                description=item.get('description'),
                algorithm_type=item.get('algorithm_type'),
                enabled=item.get('enabled'),
                config=_coerce_config(item.get('config')),
                referenced_case_count=item.get('referenced_case_count', 0),
                created_by_user_id=item.get('created_by_user_id'),
                updated_by_user_id=item.get('updated_by_user_id'),
                created_at=item.get('created_at'),
                updated_at=item.get('updated_at'),
            )
        )
