# -*- coding: utf-8 -*-
"""EvaluationConfigHandler — CQRS 调度入口。

作为 application/handlers 层，统一接收 infrastructure/grpc/servicers 的请求，
按 Command / Query 分派到对应的 application 服务。

职责：
- 接收 servicer 传入的参数
- 分派到 EvaluationCommandService（写）或 EvaluationQueryService（读）
- 返回统一格式的 dict: {success, message, data, code?}
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from evaluation_service.application.commands.evaluation_command_service import (
    evaluation_command_service,
)
from evaluation_service.application.queries.evaluation_query_service import (
    evaluation_query_service,
)


class EvaluationConfigHandler:
    """评估配置 CQRS 调度器。"""

    @property
    def cmd(self) -> evaluation_command_service.__class__:
        return evaluation_command_service

    @property
    def query(self) -> evaluation_query_service.__class__:
        return evaluation_query_service

    # ==================== Category ====================

    def create_category(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.cmd.create_category(data)

    def update_category(self, cat_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.cmd.update_category(cat_id, data)

    def delete_category(self, cat_id: int) -> Dict[str, Any]:
        return self.cmd.delete_category(cat_id)

    def list_categories(self) -> Dict[str, Any]:
        return self.query.list_categories()

    # ==================== Dimension 写操作 ====================

    def create_dimension(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.cmd.create_dimension(data)

    def update_dimension(self, dim_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.cmd.update_dimension(dim_id, data)

    def delete_dimension(self, dim_id: int) -> Dict[str, Any]:
        return self.cmd.delete_dimension(dim_id)

    def batch_action(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.cmd.batch_action(data)

    def calculate_score(self, dim_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.cmd.calculate_score(dim_id, data)

    def health_check(self, dim_id: int) -> Dict[str, Any]:
        return self.cmd.health_check(dim_id)

    # ==================== Dimension 读操作 ====================

    def list_dimensions(
        self,
        category_id: Optional[int] = None,
        page: int = 1,
        per_page: int = 10,
        search: str = '',
    ) -> Dict[str, Any]:
        return self.query.list_dimensions(
            category_id=category_id, page=page, per_page=per_page, search=search,
        )

    def get_dimension_options(self, algorithm_type: str = '') -> Dict[str, Any]:
        return self.query.get_dimension_options(algorithm_type)


# 模块级单例
evaluation_config_handler = EvaluationConfigHandler()
