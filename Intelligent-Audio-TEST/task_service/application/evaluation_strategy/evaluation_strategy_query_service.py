# -*- coding: utf-8 -*-
"""EvaluationStrategyQueryService — 评估策略查询应用服务（读侧，INT-590）。

策略列表返回 referenced_case_count（列表展示 + 删保护同源）；查询侧只读
ReadModel，不产生副作用。
"""
from __future__ import annotations

import logging

from task_service.domain.repositories.evaluation_strategy_repository import (
    EvaluationStrategyRepositoryABC,
)
from task_service.infrastructure.persistence.evaluation_strategy_repository import (
    evaluation_strategy_repository,
)

logger = logging.getLogger(__name__)


class EvaluationStrategyQueryService:
    """评估策略查询应用服务（读侧）。"""

    def __init__(self, repo: EvaluationStrategyRepositoryABC = None):
        self.repo = repo or evaluation_strategy_repository

    # ==================== 读操作 ====================

    def list_strategies(self, page=1, per_page=10, keyword=None,
                        algorithm_type=None, enabled=None) -> dict:
        """分页查询评估策略列表（含 referenced_case_count）。

        enabled 过滤三态：None 不过滤，True/False 按启用状态过滤。
        """
        try:
            if enabled is not None:
                enabled = str(enabled).lower() == 'true'
            pagination = self.repo.list_strategies(
                page=page, per_page=per_page, keyword=keyword,
                algorithm_type=algorithm_type, enabled=enabled,
            )
            return {
                'success': True,
                'message': '',
                'data': pagination,
            }
        except Exception as e:
            logger.error(f"查询评估策略列表失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def get_strategy(self, strategy_id: str) -> dict:
        """获取单个评估策略详情（含 referenced_case_count）。"""
        try:
            strategy = self.repo.get_strategy(strategy_id)
            if not strategy:
                return {'success': False, 'message': '未找到评估策略', 'data': {'code': 404}, 'code': 404}

            from task_service.application.evaluation_strategy.evaluation_strategy_crud_service import (
                evaluation_strategy_crud_service,
            )
            data = evaluation_strategy_crud_service._serialize(
                strategy,
                referenced_case_count=self.repo.count_referenced_cases(strategy_id),
            )
            return {'success': True, 'message': '', 'data': data}
        except Exception as e:
            logger.error(f"获取评估策略详情失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}


# 模块级单例
evaluation_strategy_query_service = EvaluationStrategyQueryService()
