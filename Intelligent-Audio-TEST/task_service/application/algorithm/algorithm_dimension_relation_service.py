# -*- coding: utf-8 -*-
# DEPRECATED: 本文件已废弃，维度关联/导入/批量删除已迁移至 algorithm_service（DDD 四层架构）。
# 后续应通过 algorithm_service 的 gRPC 接口访问，详见 shared/clients/grpc_clients.py
# 中的 get_algorithm_definition_service_stub。
# 当前保留仅为兼容 task_service.interfaces.grpc.algorithm_config.AlgorithmConfigServiceServicer，
# 待 algorithm_service 的 proto 接入并完成调用方切换后删除。
"""AlgorithmDimensionRelationService - 维度关联 / 导入 / 批量删除 mixin。

职责：
- 维度关联写操作（associate_dimensions / create / update / delete_dimension_relation）
- 算法配置导入（import_algorithms）
- 算法批量删除（bulk_delete）

本 mixin 不持有 __init__，依赖由聚合服务
AlgorithmParamCrudService 初始化的 self.repo（AlgorithmRepository）。

所有方法返回 dict: {success, message, data, code?}
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Dict

logger = logging.getLogger(__name__)


class AlgorithmDimensionRelationService:
    """算法-维度关联 / 导入 / 批量删除 写操作 mixin。"""

    # ==================== 维度关联写操作 ====================

    def associate_dimensions(self, algo_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """关联评估维度"""
        try:
            self.repo.soft_delete_algorithm_dimension_relations(algo_type)

            dimensions = data.get('dimensions') or []
            for dim_data in dimensions:
                dim_id = dim_data.get('dimension_id') or dim_data.get('id')
                weight = dim_data.get('weight', 1.0)
                is_default = dim_data.get('is_default', False)

                if dim_id:
                    relation_data = {
                        'algorithm_type': algo_type,
                        'dimension_id': dim_id,
                        'is_default': is_default,
                        'weight': weight,
                    }
                    self.repo.create_dimension_relation(relation_data)

            self.repo.commit()
            return {'success': True, 'message': 'Dimensions associated'}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"关联评估维度失败: {e}")
            return {'success': False, 'message': f'关联失败: {e}', 'code': 500}

    def create_dimension_relation(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建单条维度关联"""
        algorithm_type = data.get('algorithm_type')
        dimension_id = data.get('dimension_id')
        if not algorithm_type or not dimension_id:
            return {'success': False, 'message': 'algorithm_type and dimension_id are required', 'code': 400}

        try:
            existing = self.repo.find_dimension_relation(
                algorithm_type, dimension_id
            )
            if existing:
                return {'success': False, 'message': 'Dimension relation already exists', 'code': 400}

            relation = self.repo.create_dimension_relation(data)
            self.repo.commit()
            return {
                'success': True,
                'message': 'Dimension relation created',
                'data': relation if isinstance(relation, dict) else asdict(relation),
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"创建维度关联失败: {e}")
            return {'success': False, 'message': f'创建失败: {e}', 'code': 500}

    def update_dimension_relation(
        self, relation_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """更新单条维度关联"""
        try:
            relation = self.repo.get_dimension_relation(relation_id)
            if not relation:
                return {'success': False, 'message': 'Dimension relation not found', 'code': 404}

            self.repo.update_dimension_relation_attrs(relation, data)
            self.repo.commit()
            return {
                'success': True,
                'message': 'Dimension relation updated',
                'data': relation if isinstance(relation, dict) else asdict(relation),
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"更新维度关联失败: {e}")
            return {'success': False, 'message': f'更新失败: {e}', 'code': 500}

    def delete_dimension_relation(self, relation_id: int) -> Dict[str, Any]:
        """删除单条维度关联"""
        try:
            relation = self.repo.get_dimension_relation(relation_id)
            if not relation:
                return {'success': False, 'message': 'Dimension relation not found', 'code': 404}

            self.repo.soft_delete_dimension_relation(relation)
            self.repo.commit()
            return {'success': True, 'message': 'Dimension relation deleted'}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"删除维度关联失败: {e}")
            return {'success': False, 'message': f'删除失败: {e}', 'code': 500}

    # ==================== 导入 / 批量删除 ====================

    def import_algorithms(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """导入算法配置"""
        algorithms = data.get('algorithms') or []
        results = []

        try:
            for algo_data in algorithms:
                algo_type = algo_data.get('type')
                if not algo_type:
                    continue

                algo_def = self.repo.find_algorithm_by_type(algo_type)
                if not algo_def:
                    algo_def = self.repo.create_algorithm_definition(algo_data)

                params = algo_data.get('params', [])
                for param_data in params:
                    param_data = {**param_data, 'algorithm_type': algo_type}
                    self.repo.create_import_device_param(param_data)

                results.append(algo_type)

            self.repo.commit()
            return {
                'success': True,
                'message': f"Imported {len(results)} algorithms",
                'data': {'imported': results},
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"导入算法配置失败: {e}")
            return {'success': False, 'message': f'导入失败: {e}', 'code': 500}

    def bulk_delete(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """批量删除算法"""
        algorithm_types = data.get('algorithm_types') or []
        if not algorithm_types:
            return {'success': False, 'message': 'Invalid request data', 'code': 400}

        deleted = []
        try:
            algo_defs = self.repo.list_algorithm_definitions_for_bulk_delete(
                algorithm_types
            )
            for algo_def in algo_defs:
                if isinstance(algo_def, dict):
                    deleted.append(algo_def.get('type'))
                else:
                    deleted.append(algo_def.type)
            self.repo.flush()

            self.repo.commit()
            return {
                'success': True,
                'message': f"Deleted {len(deleted)} algorithms",
                'data': {'deleted_types': deleted},
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"批量删除算法失败: {e}")
            return {'success': False, 'message': f'删除失败: {e}', 'code': 500}
