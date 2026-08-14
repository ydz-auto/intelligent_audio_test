# -*- coding: utf-8 -*-
# DEPRECATED: 本文件已废弃，algorithm CRUD 已迁移至 algorithm_service（DDD 四层架构）。
# 后续应通过 algorithm_service 的 gRPC 接口访问，详见 shared/clients/grpc_clients.py
# 中的 get_algorithm_group_service_stub / get_algorithm_definition_service_stub。
# 当前保留仅为兼容 task_service.interfaces.grpc.algorithm_config.AlgorithmConfigServiceServicer，
# 待 algorithm_service 的 proto 接入并完成调用方切换后删除。
"""AlgorithmCrudService - 算法定义 CRUD 服务（写模型 + 读模型）。

职责：
- 算法定义 CRUD（创建/更新/删除/查询）
- 算法定义序列化

分组/参数/映射/维度关联等 CRUD 由以下组合服务提供：
- AlgorithmGroupCrudService（algorithm_group_crud_service.py）
- AlgorithmParamCrudService（algorithm_param_crud_service.py）

持久化访问统一委托给 AlgorithmRepository（Repository 模式），
本服务不再直接出现 `session = get_db_session()` / `session.query()`。

所有方法返回 dict: {success, message, data, code?}
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from task_service.application.algorithm.algorithm_group_crud_service import (
    AlgorithmGroupCrudService,
)
from task_service.application.algorithm.algorithm_param_crud_service import (
    AlgorithmParamCrudService,
)

logger = logging.getLogger(__name__)


class AlgorithmCrudService(AlgorithmGroupCrudService, AlgorithmParamCrudService):
    """算法定义 CRUD 服务。

    通过多重继承组合分组 CRUD 与参数/映射/维度关联 CRUD，
    使 ``algorithm_crud_service`` 单例仍持有全部方法，servicer 无需改动。
    """

    # ==================== 算法定义 写操作 ====================

    def create_algorithm(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建算法定义"""
        algo_type = data.get('type')
        if not algo_type:
            return {'success': False, 'message': 'type is required', 'code': 400}

        try:
            if self.repo.find_algorithm_by_type(algo_type):
                return {'success': False, 'message': f"Algorithm '{algo_type}' already exists"}

            algo_def = self.repo.create_algorithm_definition(data)

            if data.get('device_params') is not None:
                self._update_params(algo_type, data.get('device_params'), 'device')
            if data.get('api_params') is not None:
                self._update_params(algo_type, data.get('api_params'), 'api')
            if data.get('case_params') is not None:
                self._update_case_params(algo_type, data.get('case_params'))
            if data.get('mappings') is not None:
                self._update_mappings(algo_type, data.get('mappings'))
            if data.get('associated_dimensions') is not None:
                self._update_associated_dimensions(
                    algo_type, data.get('associated_dimensions')
                )

            self.repo.commit()

            return {
                'success': True,
                'message': 'Algorithm created',
                'data': self._serialize_algorithm(algo_type),
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"创建算法定义失败: {e}")
            return {'success': False, 'message': f'创建失败: {e}', 'code': 500}

    def update_algorithm(self, algo_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新算法定义"""
        try:
            algo_def = self.repo.find_algorithm_by_type(algo_type)
            if not algo_def:
                return {'success': False, 'message': 'Algorithm not found', 'code': 404}

            self.repo.update_algorithm_definition_attrs(algo_def, data)

            if data.get('device_params') is not None:
                self._update_params(algo_type, data['device_params'], 'device')
            if data.get('api_params') is not None:
                self._update_params(algo_type, data['api_params'], 'api')
            if data.get('case_params') is not None:
                self._update_case_params(algo_type, data['case_params'])
            if data.get('mappings') is not None:
                self._update_mappings(algo_type, data['mappings'])
            if data.get('associated_dimensions') is not None:
                self._update_associated_dimensions(
                    algo_type, data['associated_dimensions']
                )

            self.repo.commit()

            return {
                'success': True,
                'message': 'Algorithm updated',
                'data': self._serialize_algorithm(algo_type),
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"更新算法定义失败: {e}")
            return {'success': False, 'message': f'更新失败: {e}', 'code': 500}

    def delete_algorithm(self, algo_type: str) -> Dict[str, Any]:
        """删除算法定义（软删除）"""
        try:
            algo_def = self.repo.find_algorithm_by_type(algo_type)
            if not algo_def:
                return {'success': False, 'message': 'Algorithm not found', 'code': 404}

            self.repo.soft_delete_algorithm(algo_def)
            self.repo.commit()

            return {'success': True, 'message': 'Algorithm deleted'}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"删除算法定义失败: {e}")
            return {'success': False, 'message': f'删除失败: {e}', 'code': 500}

    # ========== 算法定义私有辅助 ==========

    def _update_associated_dimensions(
        self, algo_type: str, dimensions_data: List[Dict]
    ) -> None:
        """更新关联的评估维度"""
        existing_relations = self.repo.list_dimension_relations(algo_type)
        existing_dim_ids = {r.dimension_id for r in existing_relations}

        submitted_dim_ids = set()

        for dim_data in dimensions_data:
            dim_id = dim_data.get('dimension_id') or dim_data.get('id')
            weight = dim_data.get('weight', 1.0)
            is_default = dim_data.get('is_default', False)

            if dim_id:
                submitted_dim_ids.add(dim_id)

                if dim_id in existing_dim_ids:
                    relation = self.repo.find_dimension_relation(algo_type, dim_id)
                    if relation:
                        self.repo.update_dimension_relation_attrs(relation, {
                            'weight': weight,
                            'is_default': is_default,
                        })
                else:
                    self.repo.create_dimension_relation({
                        'algorithm_type': algo_type,
                        'dimension_id': dim_id,
                        'is_default': is_default,
                        'weight': weight,
                    })

        for relation in existing_relations:
            if relation.dimension_id not in submitted_dim_ids:
                self.repo.soft_delete_dimension_relation(relation)

    def _update_params(
        self, algo_type: str, params: List[Dict], param_type: str
    ) -> None:
        """更新参数（device 或 api）"""
        is_api = param_type == 'api'

        if is_api:
            existing_params = self.repo.list_api_params(algo_type)
            get_param = self.repo.get_api_param
            find_by_code = self.repo.find_api_param_by_code
            create_param = self.repo.create_api_param
        else:
            existing_params = self.repo.list_device_params(algo_type)
            get_param = self.repo.get_device_param
            find_by_code = self.repo.find_device_param_by_code
            create_param = self.repo.create_device_param

        existing_ids = {p.id for p in existing_params}
        submitted_ids = set()

        for param_data in params:
            param_id = param_data.get('id')
            param_code = param_data.get('param_code')
            direction = param_data.get('direction', 'input')

            if param_id:
                param = get_param(param_id)
                if param:
                    submitted_ids.add(param_id)
                    update_fields = {
                        field: param_data[field]
                        for field in ['param_name', 'label', 'param_type', 'direction', 'required',
                                      'default_value', 'validation_rules', 'help_text',
                                      'ui_order', 'hidden']
                        if field in param_data
                    }
                    self.repo.update_param_attrs(param, update_fields)
            else:
                existing_param = find_by_code(algo_type, param_code, direction)

                if existing_param:
                    submitted_ids.add(existing_param.id)
                    update_fields = {
                        field: param_data[field]
                        for field in ['param_name', 'label', 'param_type', 'required',
                                      'default_value', 'validation_rules', 'help_text',
                                      'ui_order', 'hidden']
                        if field in param_data
                    }
                    self.repo.update_param_attrs(existing_param, update_fields)
                else:
                    create_param({
                        'algorithm_type': algo_type,
                        'param_code': param_code,
                        'param_name': param_data.get('param_name'),
                        'label': param_data.get('label'),
                        'param_type': param_data.get('param_type', 'text'),
                        'direction': direction,
                        'required': param_data.get('required', False),
                        'default_value': param_data.get('default_value'),
                        'validation_rules': param_data.get('validation_rules'),
                        'help_text': param_data.get('help_text'),
                        'ui_order': param_data.get('ui_order', 0),
                        'hidden': param_data.get('hidden', False),
                    })

        for old_id in existing_ids - submitted_ids:
            if is_api:
                param = self.repo.get_api_param(old_id)
            else:
                param = self.repo.get_device_param(old_id)
            # get_*_param 仅返回未删除项；若已软删则跳过
            if param:
                self.repo.soft_delete_param(param)

    def _update_case_params(
        self, algo_type: str, params: List[Dict]
    ) -> None:
        """更新用例专属参数"""
        valid_scopes = {'common', 'api', 'e2e'}
        existing_params = self.repo.list_case_params(algo_type)
        existing_ids = {p.id for p in existing_params}
        submitted_ids = set()

        case_param_fields = ['param_name', 'label', 'param_type', 'required',
                             'default_value',
                             'help_text', 'ui_order', 'hidden', 'scope',
                             'min_value', 'max_value', 'step', 'unit']

        for param_data in params:
            param_id = param_data.get('id')
            if param_id:
                param = self.repo.get_case_param(param_id)
                if param:
                    submitted_ids.add(param_id)
                    update_fields = {}
                    for field in case_param_fields:
                        if field in param_data and param_data[field] is not None:
                            if field == 'scope' and param_data[field] not in valid_scopes:
                                continue
                            update_fields[field] = param_data[field]
                    self.repo.update_param_attrs(param, update_fields)
            else:
                raw_scope = param_data.get('scope', 'common')
                scope_value = raw_scope if raw_scope in valid_scopes else 'common'
                pc = param_data.get('param_code')
                if not pc:
                    continue
                dup = self.repo.find_case_param_by_code(algo_type, pc, deleted=False)
                if dup:
                    update_fields = {}
                    for field in case_param_fields:
                        if field in param_data and param_data[field] is not None:
                            if field == 'scope' and param_data[field] not in valid_scopes:
                                continue
                            update_fields[field] = param_data[field]
                    self.repo.update_param_attrs(dup, update_fields)
                    continue
                self.repo.create_case_param({
                    'algorithm_type': algo_type,
                    'param_code': pc,
                    'param_name': param_data.get('param_name'),
                    'label': param_data.get('label'),
                    'param_type': param_data.get('param_type', 'text'),
                    'required': param_data.get('required', False),
                    'default_value': param_data.get('default_value'),
                    'help_text': param_data.get('help_text'),
                    'ui_order': param_data.get('ui_order', 0),
                    'hidden': param_data.get('hidden', False),
                    'scope': scope_value,
                    'min_value': param_data.get('min_value'),
                    'max_value': param_data.get('max_value'),
                    'step': param_data.get('step'),
                    'unit': param_data.get('unit'),
                })

        for old_id in existing_ids - submitted_ids:
            param = self.repo.get_case_param(old_id)
            if param:
                self.repo.soft_delete_param(param)

    def _update_mappings(
        self, algo_type: str, mappings: Dict
    ) -> None:
        """更新映射"""
        existing_mappings = self.repo.list_mappings(algorithm_type=algo_type)
        existing_ids = {m.id for m in existing_mappings}
        submitted_ids = set()

        for source_type, mapping_list in mappings.items():
            if source_type not in ('device', 'api', 'evaluation'):
                continue
            for mapping_data in mapping_list:
                mapping_id = mapping_data.get('id')
                if mapping_id:
                    mapping = self.repo.get_mapping(mapping_id)
                    if mapping:
                        submitted_ids.add(mapping_id)
                        update_data = {
                            field: mapping_data[field]
                            for field in ['source', 'source_param', 'source_direction',
                                          'dimension_id', 'target_param', 'transform_type']
                            if field in mapping_data
                        }
                        if source_type == 'evaluation':
                            update_data['source'] = mapping_data.get('source', 'case')
                        self.repo.update_mapping_attrs(mapping, update_data)
                else:
                    source_value = (
                        mapping_data.get('source', 'case')
                        if source_type == 'evaluation'
                        else source_type
                    )
                    self.repo.create_mapping({
                        'algorithm_type': algo_type,
                        'source_type': (
                            source_value
                            if source_value in ('device', 'api', 'case', 'reference')
                            else 'api'
                        ),
                        'source': source_value,
                        'source_param': mapping_data.get('source_param'),
                        'source_direction': mapping_data.get('source_direction', 'output'),
                        'dimension_id': mapping_data.get('dimension_id'),
                        'target_param': mapping_data.get('target_param'),
                        'transform_type': mapping_data.get('transform_type', 'none'),
                    })

        for old_id in existing_ids - submitted_ids:
            mapping = self.repo.get_mapping(old_id)
            if mapping:
                self.repo.soft_delete_mapping(mapping)

    # ==================== 算法定义 读操作 ====================

    def list_algorithms(
        self,
        status: Optional[str] = None,
        group_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """获取算法定义列表"""
        try:
            algorithms = self.repo.list_algorithm_definitions(
                status=status, group_id=group_id
            )

            data_list = [
                self._serialize_algorithm(a.type) for a in algorithms
            ]

            return {
                'success': True,
                'message': '',
                'data': {
                    'data': data_list,
                    'total': len(algorithms),
                },
            }
        except Exception as e:
            logger.error(f"查询算法定义列表失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def get_algorithm_options(self) -> Dict[str, Any]:
        """获取算法选项（下拉框用）"""
        try:
            algorithms = self.repo.list_online_algorithm_definitions()

            return {
                'success': True,
                'message': '',
                'data': {
                    'algorithms': [
                        {
                            'value': a.type,
                            'name': a.name,
                            'group_id': a.group_id,
                            'group_name': a.group_name,
                            'icon': a.icon
                        }
                        for a in algorithms
                    ]
                },
            }
        except Exception as e:
            logger.error(f"获取算法选项失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def get_algorithm(self, algo_type: str) -> Dict[str, Any]:
        """获取算法详情"""
        try:
            algo_data = self._serialize_algorithm(algo_type)
            if not algo_data:
                return {'success': False, 'message': 'Algorithm not found', 'code': 404}
            return {'success': True, 'message': '', 'data': algo_data}
        except Exception as e:
            logger.error(f"获取算法详情失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    # ==================== 序列化辅助 ====================

    def _serialize_algorithm(self, algo_type: str) -> Optional[Dict[str, Any]]:
        """序列化算法定义及其关联数据"""
        algo_def = self.repo.find_algorithm_by_type(algo_type)
        if not algo_def:
            return None

        device_params = self.repo.list_device_params(algo_type)
        api_params = self.repo.list_api_params(algo_type)
        case_params = self.repo.list_case_params(algo_type)
        mappings = self.repo.list_mappings(algorithm_type=algo_type)
        dimension_relations = self.repo.list_dimension_relations(algo_type)
        reference_params = self.repo.list_reference_params(algo_type)

        return {
            'id': algo_def.id,
            'type': algo_def.type,
            'name': algo_def.name,
            'group_id': algo_def.group_id,
            'group_name': algo_def.group_name,
            'description': algo_def.description,
            'status': algo_def.status,
            'icon': algo_def.icon,
            'display_order': algo_def.display_order,
            'device_params': [self._serialize_device_param(p) for p in device_params] if isinstance(device_params, list) else [],
            'api_params': [self._serialize_api_param(p) for p in api_params] if isinstance(api_params, list) else [],
            'case_params': [self._serialize_case_param(p) for p in case_params] if isinstance(case_params, list) else [],
            'params': [self._serialize_device_param(p) for p in device_params] if isinstance(device_params, list) else [],
            'mappings': self._serialize_mappings(mappings),
            'dimension_relations': [
                self._serialize_dimension_relation(r) for r in dimension_relations
            ],
            'associated_dimensions': [
                self._serialize_dimension_relation(r) for r in dimension_relations
            ],
            'reference_params': [self._serialize_reference_param(p) for p in reference_params] if isinstance(reference_params, list) else [],
            'created_at': algo_def.created_at,
            'updated_at': algo_def.updated_at
        }

    @staticmethod
    def _serialize_device_param(param) -> Dict[str, Any]:
        """序列化设备参数"""
        return param if isinstance(param, dict) else asdict(param)

    @staticmethod
    def _serialize_api_param(param) -> Dict[str, Any]:
        """序列化API参数"""
        return param if isinstance(param, dict) else asdict(param)

    @staticmethod
    def _serialize_case_param(param) -> Dict[str, Any]:
        """序列化用例专属参数"""
        return param if isinstance(param, dict) else asdict(param)

    def _serialize_dimension_relation(self, rel) -> Dict[str, Any]:
        """序列化评估维度关联"""
        return rel if isinstance(rel, dict) else asdict(rel)

    @staticmethod
    def _serialize_reference_param(param) -> Dict[str, Any]:
        """序列化参考参数"""
        return param if isinstance(param, dict) else asdict(param)

    def _serialize_mappings(self, mappings) -> Dict[str, Any]:
        """序列化参数映射，按源类型(source)分组"""
        result = {'device': [], 'api': [], 'evaluation': []}
        for m in mappings or []:
            if isinstance(m, dict):
                m_dict = m
            else:
                m_dict = asdict(m)
            if m_dict.get('dimension_id') is not None:
                result['evaluation'].append(m_dict)
            elif m_dict.get('source') in result:
                result[m_dict.get('source')].append(m_dict)
        return result


# 模块级单例
algorithm_crud_service = AlgorithmCrudService()
