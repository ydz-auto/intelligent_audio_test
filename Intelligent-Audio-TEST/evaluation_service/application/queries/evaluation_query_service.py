# -*- coding: utf-8 -*-
"""EvaluationQueryService — 评估维度读操作应用服务（CQRS Query 侧）。

承担 list_categories / list_dimensions / get_dimension_options 等查询职责。

约定：
- 所有方法返回 dict: {success, message, data, code?}
- 通过 self.repo 调用 Repository，不直连 DB
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from evaluation_service.domain.repositories.evaluation_repository_abc import (
    EvaluationRepositoryABC,
)
from evaluation_service.infrastructure.persistence.evaluation_repository import (
    evaluation_repository,
)

logger = logging.getLogger(__name__)


class EvaluationQueryService:
    """评估维度读操作应用服务（CQRS Query）。"""

    def __init__(self, repo: EvaluationRepositoryABC = None):
        self.repo = repo or evaluation_repository

    def list_categories(self) -> Dict[str, Any]:
        """查询分类列表。"""
        try:
            categories = self.repo.list_categories()
            data = []
            for cat in categories:
                created_at = cat.created_at
                updated_at = cat.updated_at

                if isinstance(created_at, datetime):
                    created_at_iso = created_at.isoformat()
                else:
                    created_at_iso = str(created_at)

                if isinstance(updated_at, datetime):
                    updated_at_iso = updated_at.isoformat()
                else:
                    updated_at_iso = str(updated_at)

                data.append({
                    'id': cat.id,
                    'name': cat.name,
                    'description': cat.description,
                    'icon': cat.icon,
                    'created_at': created_at_iso,
                    'updated_at': updated_at_iso,
                })

            return {
                'success': True,
                'message': '',
                'data': {'items': data, 'total': len(data)},
            }
        except Exception as e:
            logger.error(f"查询分类列表失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def list_dimensions(
        self,
        category_id: Optional[int] = None,
        page: int = 1,
        per_page: int = 10,
        search: str = '',
    ) -> Dict[str, Any]:
        """分页查询评分维度列表。"""
        try:
            pagination = self.repo.query_dimensions_paginated(
                category_id=category_id, page=page, per_page=per_page, search=search,
            )
            dimensions = pagination.items

            data = []
            for dim in dimensions:
                data.append({
                    **self._serialize_dimension(dim),
                    # 详情字段按需通过 GET /dimensions/{id} 加载，避免列表 N+1 gRPC。
                    'required_inputs': [],
                    'output_fields': [],
                    'associated_algorithms': [],
                })

            return {
                'success': True,
                'message': '',
                'data': {
                    'items': data,
                    'total': pagination.total,
                    'page': page,
                    'per_page': per_page,
                    'pages': pagination.pages,
                },
            }
        except Exception as e:
            logger.error(f"查询评分维度列表失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def get_dimension(self, dim_id: int) -> Dict[str, Any]:
        """查询单个维度完整配置，仅在编辑维度时调用。"""
        try:
            dim = self.repo.get_dimension(dim_id)
            if not dim or getattr(dim, 'deleted', False):
                return {'success': False, 'message': '未找到评估维度', 'code': 404}

            params = self.repo.list_dimension_params(dim.id)
            relations = self.repo.list_relations_by_dimension(dim.id)
            return {
                'success': True,
                'message': '',
                'data': {
                    **self._serialize_dimension(dim),
                    'required_inputs': [
                        self._serialize_dimension_param(p)
                        for p in params
                        if getattr(p, 'param_direction', None) == 'input'
                    ],
                    'output_fields': [
                        self._serialize_dimension_param(p)
                        for p in params
                        if getattr(p, 'param_direction', None) == 'output'
                    ],
                    'associated_algorithms': [
                        {
                            'algorithm_type': getattr(rel, 'algorithm_type', None),
                            'is_default': getattr(rel, 'is_default', None),
                            'weight': getattr(rel, 'weight', None),
                        }
                        for rel in relations
                    ],
                },
            }
        except Exception as e:
            logger.error(f"查询评估维度详情失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    @staticmethod
    def _serialize_dimension(dim: Any) -> Dict[str, Any]:
        """序列化维度基础字段，列表与详情共用。"""
        return {
            'id': dim.id,
            'name': dim.name,
            'description': dim.description,
            'keywords': dim.keywords,
            'dimension_type': dim.dimension_type,
            'parent_dimension_id': dim.parent_dimension_id,
            'task_type_code': dim.task_type_code,
            'category_id': dim.category_id,
            'api_url': dim.api_url,
            'api_endpoints': dim.api_endpoints,
            'api_settings': dim.api_settings,
            'api_status': dim.api_status,
            'score_unit': dim.score_unit,
            'type': dim.type,
            'result_type': dim.result_type,
            'result_min': dim.result_min,
            'result_max': dim.result_max,
            'decimal_places': dim.decimal_places,
            'weight': dim.weight,
            'estimated_exec_time': dim.estimated_exec_time,
            'rule': dim.rule,
            'statistic_method': getattr(dim, 'statistic_method', 'average') or 'average',
            'status': dim.status,
            'created_at': dim.created_at.isoformat() if dim.created_at else None,
            'updated_at': dim.updated_at.isoformat() if dim.updated_at else None,
        }

    def get_dimension_options(self, algorithm_type: str = '') -> Dict[str, Any]:
        """查询维度选项列表（可按 algorithm_type 过滤）。"""
        try:
            dimensions = self.repo.list_dimension_options(algorithm_type)

            # 查询哪些维度需要音频文件参数
            dim_ids = [d.id for d in dimensions]
            audio_dim_ids = self.repo.find_audio_dimension_ids(dim_ids)

            return {
                'success': True,
                'message': '',
                'data': {
                    'dimensions': [
                        {
                            'id': d.id,
                            'name': d.name,
                            'description': d.description,
                            'type': d.type,
                            'dimension_type': d.dimension_type,
                            'category_id': d.category_id,
                            'task_type_code': d.task_type_code,
                            'requires_audio': d.id in audio_dim_ids,
                        }
                        for d in dimensions
                    ]
                },
            }
        except Exception as e:
            logger.error(f"查询维度选项失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    @staticmethod
    def _serialize_dimension_param(param: Any) -> Dict[str, Any]:
        """将 ACL DTO 序列化为评估维度页面所需的完整参数字段。"""
        return {
            'id': getattr(param, 'id', None),
            'dimension_id': getattr(param, 'dimension_id', None),
            'param_code': getattr(param, 'param_code', None),
            'param_name': getattr(param, 'param_name', None),
            'label': getattr(param, 'label', None),
            'field_type': getattr(param, 'field_type', None),
            'param_direction': getattr(param, 'param_direction', None),
            'field_path': getattr(param, 'field_path', None),
            'agg_role': getattr(param, 'agg_role', None),
            'output_role': getattr(param, 'output_role', None),
            'visible_in_report': getattr(param, 'visible_in_report', True),
            'required': getattr(param, 'required', None),
            'default_value': getattr(param, 'default_value', None),
            'help_text': getattr(param, 'help_text', None),
            'ui_order': getattr(param, 'ui_order', None),
        }

    def get_dimension_basics_by_ids(self, dim_ids: list) -> Dict[str, Any]:
        """按 dim_id 列表批量查询维度基础信息（供 gRPC servicer 调用）。"""
        try:
            from evaluation_service.infrastructure.persistence.evaluation_dimension_repository import (
                evaluation_dimension_repository,
            )
            items = evaluation_dimension_repository.get_dimension_basics_by_ids(dim_ids)
            return {'success': True, 'message': '', 'data': {'items': items}}
        except Exception as e:
            logger.error(f"批量查询维度基础信息失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def get_dimension_results_by_result_ids(self, result_ids: list) -> Dict[str, Any]:
        """按 result_id 列表批量查询维度评估结果（含 dimension_name）。"""
        try:
            from evaluation_service.infrastructure.persistence.evaluation_dimension_repository import (
                evaluation_dimension_repository,
            )
            items = evaluation_dimension_repository.get_dimension_results_with_names_by_result_ids(result_ids)
            return {'success': True, 'message': '', 'data': {'items': items}}
        except Exception as e:
            logger.error(f"批量查询维度评估结果失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}


# 模块级单例
evaluation_query_service = EvaluationQueryService()
