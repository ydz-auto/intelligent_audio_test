# -*- coding: utf-8 -*-
# DEPRECATED: 本文件已废弃，算法参数/映射/维度关联 CRUD 已迁移至 algorithm_service（DDD 四层架构）。
# 后续应通过 algorithm_service 的 gRPC 接口访问，详见 shared/clients/grpc_clients.py
# 中的 get_algorithm_definition_service_stub。
# 当前保留仅为兼容 task_service.interfaces.grpc.algorithm_config.AlgorithmConfigServiceServicer，
# 待 algorithm_service 的 proto 接入并完成调用方切换后删除。
"""AlgorithmParamCrudService - 算法参数/映射/维度关联 CRUD 聚合服务。

职责：
- 设备/API 参数写 CRUD（create / update / delete_param）
- 参数映射写 CRUD（create / update / delete_mapping）
- 用例专属参数写 CRUD（create / update / delete_case_param）
- 参考参数写 CRUD（create / update / delete_reference_param）
- 聚合读操作与维度关联/导入/批量删除（由 mixin 提供）

持久化访问统一委托给 AlgorithmRepository（Repository 模式），
本服务不再直接出现 `session = get_db_session()` / `session.query()`，
仅保留跨域查询注释标记后续 gRPC 改造。

拆分结构：
- AlgorithmParamQueryService (algorithm_param_query_service.py)
    读：参数/用例参数/参考参数/映射读、Schema、维度关联读、
        评估维度参数读、extract_params / reload_config
- AlgorithmDimensionRelationService (algorithm_dimension_relation_service.py)
    写：维度关联 CRUD、import_algorithms、bulk_delete
- AlgorithmParamCrudService (本文件)
    写：参数/映射/用例参数/参考参数 CRUD；负责 __init__ 注入 self.repo

所有方法返回 dict: {success, message, data, code?}
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Dict

from task_service.infrastructure.acl.algorithm_acl_repository import (
    AlgorithmRepository,
)
from task_service.application.algorithm.algorithm_param_query_service import (
    AlgorithmParamQueryService,
)
from task_service.application.algorithm.algorithm_dimension_relation_service import (
    AlgorithmDimensionRelationService,
)

logger = logging.getLogger(__name__)


class AlgorithmParamCrudService(
    AlgorithmDimensionRelationService,
    AlgorithmParamQueryService,
):
    """算法参数/映射/维度关联 CRUD 聚合服务。

    通过 mixin 组合读操作（AlgorithmParamQueryService）与
    维度关联/导入/批量删除写操作（AlgorithmDimensionRelationService），
    本类聚焦参数/映射/用例参数/参考参数的写操作，并在 __init__ 中
    注入 self.repo（AlgorithmRepository），供所有 mixin 共用。
    """

    def __init__(self):
        self.repo = AlgorithmRepository()
        super().__init__()

    # ==================== 参数（设备/API）写操作 ====================

    def create_param(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建参数（支持设备参数和API参数）"""
        param_type_source = data.get('param_type_source', 'device')
        algorithm_type = data.get('algorithm_type')
        param_code = data.get('param_code')

        if not algorithm_type or not param_code:
            return {'success': False, 'message': 'algorithm_type and param_code are required', 'code': 400}

        try:
            direction = data.get('direction') or 'input'
            if param_type_source == 'api':
                existing = self.repo.find_api_param_by_code(
                    algorithm_type, param_code, direction
                )
                if existing:
                    return {
                        'success': False,
                        'message': f"API Parameter '{param_code}' already exists for algorithm '{algorithm_type}'",
                    }
                param = self.repo.create_api_param(data)
            else:
                existing = self.repo.find_device_param_by_code(
                    algorithm_type, param_code, direction
                )
                if existing:
                    return {
                        'success': False,
                        'message': f"Device Parameter '{param_code}' already exists for algorithm '{algorithm_type}'",
                    }
                param = self.repo.create_device_param(data)

            self.repo.commit()
            return {
                'success': True,
                'message': 'Parameter created',
                'data': param if isinstance(param, dict) else asdict(param),
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"创建参数失败: {e}")
            return {'success': False, 'message': f'创建失败: {e}', 'code': 500}

    def update_param(self, param_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新参数

        接受 camelCase 和 snake_case 两种键名（网关 update_param 直接传原始 JSON，
        可能含 camelCase 键如 paramName/uiOrder）。
        """
        try:
            param = self.repo.get_device_param(param_id)
            is_device = param is not None
            if not param:
                param = self.repo.get_api_param(param_id)
                if not param:
                    return {'success': False, 'message': 'Parameter not found', 'code': 404}

            updatable_fields = [
                'param_code', 'param_name', 'label', 'param_type', 'direction',
                'required', 'default_value', 'validation_rules', 'help_text',
                'ui_order', 'hidden'
            ]
            # camelCase → snake_case 映射，兼容前端直接透传的 camelCase 键
            camel_to_snake = {
                'paramCode': 'param_code', 'paramName': 'param_name',
                'paramType': 'param_type', 'uiOrder': 'ui_order',
                'defaultValue': 'default_value', 'validationRules': 'validation_rules',
                'helpText': 'help_text',
            }
            update_fields = {}
            for field in updatable_fields:
                if field in data:
                    update_fields[field] = data[field]
                elif field in camel_to_snake and camel_to_snake[field] in data:
                    # Also check if the camelCase version exists
                    pass
            # Also check camelCase keys
            for camel_key, snake_key in camel_to_snake.items():
                if snake_key in updatable_fields and camel_key in data:
                    update_fields[snake_key] = data[camel_key]

            self.repo.update_param_attrs(param, update_fields)

            self.repo.commit()

            # Re-fetch to get updated data
            if is_device:
                param = self.repo.get_device_param(param_id)
            else:
                param = self.repo.get_api_param(param_id)
            return {
                'success': True,
                'message': 'Parameter updated',
                'data': param if isinstance(param, dict) else asdict(param),
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"更新参数失败: {e}")
            return {'success': False, 'message': f'更新失败: {e}', 'code': 500}

    def delete_param(self, param_id: int) -> Dict[str, Any]:
        """删除参数（软删除）"""
        try:
            param = self.repo.get_device_param(param_id)
            if param:
                self.repo.soft_delete_param(param)
                self.repo.commit()
                return {'success': True, 'message': 'Parameter deleted'}

            param = self.repo.get_api_param(param_id)
            if param:
                self.repo.soft_delete_param(param)
                self.repo.commit()
                return {'success': True, 'message': 'Parameter deleted'}

            return {'success': False, 'message': 'Parameter not found', 'code': 404}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"删除参数失败: {e}")
            return {'success': False, 'message': f'删除失败: {e}', 'code': 500}

    # ==================== 参数映射写操作 ====================

    def create_mapping(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建参数映射"""
        try:
            mapping = self.repo.create_mapping(data)

            dim_name = None
            if mapping.dimension_id:
                # P1.7: Dimension 跨域查询改 gRPC（返回 DimensionDTO）
                dim = self.repo.get_dimension_by_id(mapping.dimension_id)
                if dim:
                    dim_name = dim.name

            self.repo.commit()
            return {
                'success': True,
                'message': 'Mapping created',
                'data': {
                    'id': mapping.id,
                    'algorithm_type': mapping.algorithm_type,
                    'source': mapping.source,
                    'source_param': mapping.source_param,
                    'source_direction': mapping.source_direction,
                    'dimension_id': mapping.dimension_id,
                    'dimension_name': dim_name,
                    'target_param': mapping.target_param,
                    'transform_type': mapping.transform_type
                },
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"创建参数映射失败: {e}")
            return {'success': False, 'message': f'创建失败: {e}', 'code': 500}

    def update_mapping(self, mapping_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新参数映射"""
        try:
            mapping = self.repo.get_mapping(mapping_id)
            if not mapping:
                return {'success': False, 'message': 'Mapping not found', 'code': 404}

            self.repo.update_mapping_attrs(mapping, data)

            dim_name = None
            if mapping.dimension_id:
                # P1.7: Dimension 跨域查询改 gRPC（返回 DimensionDTO）
                dim = self.repo.get_dimension_by_id(mapping.dimension_id)
                if dim:
                    dim_name = dim.name

            self.repo.commit()
            return {
                'success': True,
                'message': 'Mapping updated',
                'data': {
                    'id': mapping.id,
                    'algorithm_type': mapping.algorithm_type,
                    'source': mapping.source,
                    'source_param': mapping.source_param,
                    'source_direction': mapping.source_direction,
                    'dimension_id': mapping.dimension_id,
                    'dimension_name': dim_name,
                    'target_param': mapping.target_param,
                    'transform_type': mapping.transform_type
                },
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"更新参数映射失败: {e}")
            return {'success': False, 'message': f'更新失败: {e}', 'code': 500}

    def delete_mapping(self, mapping_id: int) -> Dict[str, Any]:
        """删除参数映射"""
        try:
            mapping = self.repo.get_mapping(mapping_id)
            if not mapping:
                return {'success': False, 'message': 'Mapping not found', 'code': 404}

            self.repo.soft_delete_mapping(mapping)
            self.repo.commit()
            return {'success': True, 'message': 'Mapping deleted'}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"删除参数映射失败: {e}")
            return {'success': False, 'message': f'删除失败: {e}', 'code': 500}

    # ==================== 用例专属参数写操作 ====================

    def create_case_param(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建用例专属参数"""
        algorithm_type = data.get('algorithm_type')
        param_code = data.get('param_code')
        if not algorithm_type or not param_code:
            return {
                'success': False,
                'message': 'algorithm_type and param_code are required',
                'code': 400,
            }

        try:
            existing = self.repo.find_case_param_by_code(
                algorithm_type, param_code, deleted=False
            )
            if existing:
                return {
                    'success': False,
                    'message': f"Case parameter '{param_code}' already exists for algorithm '{algorithm_type}'",
                }

            param = self.repo.create_case_param(data)
            self.repo.commit()
            return {
                'success': True,
                'message': 'Case parameter created',
                'data': param if isinstance(param, dict) else asdict(param),
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"创建用例专属参数失败: {e}")
            return {'success': False, 'message': f'创建失败: {e}', 'code': 500}

    def update_case_param(self, param_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新用例专属参数"""
        try:
            param = self.repo.get_case_param(param_id)
            if not param:
                return {'success': False, 'message': 'Case parameter not found', 'code': 404}

            updatable_fields = [
                'param_name', 'label', 'param_type', 'required', 'default_value',
                'help_text', 'ui_order', 'hidden', 'scope',
                'min_value', 'max_value', 'step', 'unit'
            ]
            update_fields = {}
            for field in updatable_fields:
                if field in data:
                    value = data[field]
                    if value is not None:
                        update_fields[field] = value
            self.repo.update_case_param_attrs(param, update_fields)

            self.repo.commit()

            # Re-fetch to get updated data
            param = self.repo.get_case_param(param_id)
            return {
                'success': True,
                'message': 'Case parameter updated',
                'data': param if isinstance(param, dict) else asdict(param),
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"更新用例专属参数失败: {e}")
            return {'success': False, 'message': f'更新失败: {e}', 'code': 500}

    def delete_case_param(self, param_id: int) -> Dict[str, Any]:
        """删除用例专属参数"""
        try:
            param = self.repo.get_case_param(param_id)
            if not param:
                return {'success': False, 'message': 'Case parameter not found', 'code': 404}

            self.repo.soft_delete_case_param(param)
            self.repo.commit()
            return {'success': True, 'message': 'Case parameter deleted'}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"删除用例专属参数失败: {e}")
            return {'success': False, 'message': f'删除失败: {e}', 'code': 500}

    # ==================== 参考参数写操作 ====================

    def create_reference_param(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建参考参数"""
        try:
            existing = self.repo.find_reference_param(
                data.get('algorithm_type'), data.get('code')
            )
            if existing:
                return {
                    'success': False,
                    'message': f"Reference parameter '{data.get('code')}' already exists for algorithm '{data.get('algorithm_type')}'",
                }

            new_param = self.repo.create_reference_param(data)
            self.repo.commit()
            return {
                'success': True,
                'message': 'Reference parameter created',
                'data': new_param if isinstance(new_param, dict) else asdict(new_param),
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"创建参考参数失败: {e}")
            return {'success': False, 'message': f'创建失败: {e}', 'code': 500}

    def update_reference_param(self, param_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新参考参数"""
        try:
            relation = self.repo.get_reference_param(param_id)
            if not relation:
                return {'success': False, 'message': 'Reference parameter not found', 'code': 404}

            update_fields = {}
            if data.get('code'):
                update_fields['code'] = data['code']
            if data.get('name') is not None:
                update_fields['name'] = data['name']
            if data.get('type'):
                update_fields['param_type'] = data['type']
            if data.get('annotation_code') is not None:
                update_fields['annotation_code'] = data['annotation_code']
            if data.get('annotation_format') is not None:
                update_fields['annotation_format'] = data['annotation_format']
            if data.get('field_path') is not None:
                update_fields['field_path'] = data['field_path']
            if data.get('merge_mode') is not None:
                update_fields['merge_mode'] = data['merge_mode']
            if data.get('help_text') is not None:
                update_fields['help_text'] = data['help_text']
            self.repo.update_reference_param_attrs(relation, update_fields)

            self.repo.commit()

            # Re-fetch to get updated data
            relation = self.repo.get_reference_param(param_id)
            return {
                'success': True,
                'message': 'Reference parameter updated',
                'data': relation if isinstance(relation, dict) else asdict(relation),
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"更新参考参数失败: {e}")
            return {'success': False, 'message': f'更新失败: {e}', 'code': 500}

    def delete_reference_param(self, param_id: int) -> Dict[str, Any]:
        """删除参考参数"""
        try:
            param = self.repo.get_reference_param(param_id)
            if not param:
                return {'success': False, 'message': 'Reference parameter not found', 'code': 404}

            self.repo.soft_delete_reference_param(param)
            self.repo.commit()
            return {'success': True, 'message': 'Reference parameter deleted'}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"删除参考参数失败: {e}")
            return {'success': False, 'message': f'删除失败: {e}', 'code': 500}


# 模块级单例
algorithm_param_crud_service = AlgorithmParamCrudService()
