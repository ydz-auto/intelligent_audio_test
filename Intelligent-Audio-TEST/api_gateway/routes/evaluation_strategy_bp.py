from fastapi import APIRouter, Query

from api_gateway.application.services.evaluation_strategy.evaluation_strategy_command_service import (
    EvaluationStrategyCommandService,
)
from api_gateway.application.services.evaluation_strategy.evaluation_strategy_query_service import (
    EvaluationStrategyQueryService,
)
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission

# 评估策略归用例域：RBAC 复用 testcase:read / testcase:update
router = APIRouter()


@router.get('')
def get_all(_: None = require_permission('testcase:read')):
    return to_response(EvaluationStrategyQueryService.get_all())


@router.get('/{strategy_id}')
def get_one(strategy_id: str, _: None = require_permission('testcase:read')):
    return to_response(EvaluationStrategyQueryService.get_one(strategy_id))


@router.post('')
def create(_: None = require_permission('testcase:update')):
    return to_response(EvaluationStrategyCommandService.create())


@router.put('/{strategy_id}')
def update(strategy_id: str, _: None = require_permission('testcase:update')):
    return to_response(EvaluationStrategyCommandService.update(strategy_id))


@router.delete('/{strategy_id}')
def delete(strategy_id: str, _: None = require_permission('testcase:update')):
    return to_response(EvaluationStrategyCommandService.delete(strategy_id))
