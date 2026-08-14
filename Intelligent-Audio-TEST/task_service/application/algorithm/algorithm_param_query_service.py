# -*- coding: utf-8 -*-
# DEPRECATED: 本文件已废弃，算法参数查询已迁移至 algorithm_service（DDD 四层架构）。
# 后续应通过 algorithm_service 的 gRPC 接口访问，详见 shared/clients/grpc_clients.py
# 中的 get_algorithm_definition_service_stub。
# 当前保留仅为兼容 task_service.interfaces.grpc.algorithm_config.AlgorithmConfigServiceServicer，
# 待 algorithm_service 的 proto 接入并完成调用方切换后删除。
"""AlgorithmParamQueryService - 算法参数相关读操作 mixin。

职责：
- 设备/API 参数读（list_params / get_param）
- 用例专属参数读（list_case_params / get_case_param）
- 参考参数读（list_reference_params）
- 参数映射读（list_mappings）
- 表单 Schema 读（get_form_schema）
- 维度关联读（get_algorithm_dimensions）
- 评估维度参数读（get_dimension_params）
- 用例参数提取 / 配置热更新（extract_params / reload_config）

本 mixin 不持有 __init__，依赖由聚合服务
AlgorithmParamCrudService 初始化的 self.repo（AlgorithmRepository）。

所有方法返回 dict: {success, message, data, code?}
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# scope 合法取值
VALID_SCOPES = ('common', 'api', 'e2e')


class AlgorithmParamQueryService:
    """算法参数相关读操作 mixin。"""

    # ==================== 参数读 ====================

    def list_params(
        self,
        algorithm_type: Optional[str] = None,
        param_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取参数列表（支持设备参数和API参数）"""
        try:
            if param_type == 'api':
                params = self.repo.list_api_params(algorithm_type)
            else:
                params = self.repo.list_device_params(algorithm_type)
            serialized = [p if isinstance(p, dict) else asdict(p) for p in params]

            return {
                'success': True,
                'message': '',
                'data': {
                    'parameters': serialized,
                    'total': len(serialized),
                },
            }
        except Exception as e:
            logger.error(f"查询参数列表失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def get_param(self, param_id: int) -> Dict[str, Any]:
        """获取参数详情"""
        try:
            param = self.repo.get_device_param(param_id)
            if param:
                return {'success': True, 'message': '', 'data': param if isinstance(param, dict) else asdict(param)}

            param = self.repo.get_api_param(param_id)
            if param:
                return {'success': True, 'message': '', 'data': param if isinstance(param, dict) else asdict(param)}

            return {'success': False, 'message': 'Parameter not found', 'code': 404}
        except Exception as e:
            logger.error(f"获取参数详情失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    # ==================== 用例专属参数读 ====================

    def list_case_params(
        self,
        algorithm_type: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取用例专属参数列表"""
        if scope and scope not in VALID_SCOPES:
            return {
                'success': False,
                'message': f"Invalid scope: '{scope}'. Must be one of {VALID_SCOPES}",
                'code': 400,
            }

        try:
            params = self.repo.list_case_params(algorithm_type, scope)
            return {
                'success': True,
                'message': '',
                'data': {
                    'parameters': [p if isinstance(p, dict) else asdict(p) for p in params],
                    'total': len(params),
                },
            }
        except Exception as e:
            logger.error(f"查询用例专属参数列表失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def get_case_param(self, param_id: int) -> Dict[str, Any]:
        """获取单个用例专属参数"""
        try:
            param = self.repo.get_case_param(param_id)
            if not param:
                return {'success': False, 'message': 'Case parameter not found', 'code': 404}
            return {'success': True, 'message': '', 'data': param if isinstance(param, dict) else asdict(param)}
        except Exception as e:
            logger.error(f"获取用例专属参数失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    # ==================== 参考参数读 ====================

    def list_reference_params(self, algorithm_type: str) -> Dict[str, Any]:
        """获取参考参数列表"""
        if not algorithm_type:
            return {'success': False, 'message': 'algorithm_type is required', 'code': 400}

        try:
            params = self.repo.list_reference_params(algorithm_type)
            return {
                'success': True,
                'message': '',
                'data': {
                    'parameters': [p if isinstance(p, dict) else asdict(p) for p in params],
                    'total': len(params),
                },
            }
        except Exception as e:
            logger.error(f"查询参考参数列表失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    # ==================== 参数映射读 ====================

    def list_mappings(
        self,
        algorithm_type: Optional[str] = None,
        source_type: Optional[str] = None,
        dimension_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """获取参数映射列表"""
        try:
            mappings = self.repo.list_mappings(
                algorithm_type, source_type, dimension_id
            )

            # 批量查询维度名称
            dim_ids = {m.dimension_id for m in mappings if m.dimension_id is not None}
            dim_map = self.repo.list_dimension_names_map_by_ids(list(dim_ids))

            result = {
                'mappings': [
                    {
                        'id': m.id,
                        'algorithm_type': m.algorithm_type,
                        'source': m.source,
                        'source_param': m.source_param,
                        'source_direction': m.source_direction,
                        'dimension_id': m.dimension_id,
                        'dimension_name': dim_map.get(m.dimension_id) if m.dimension_id else None,
                        'target_param': m.target_param,
                        'transform_type': m.transform_type
                    }
                    for m in mappings
                ],
                'total': len(mappings)
            }
            return {'success': True, 'message': '', 'data': result}
        except Exception as e:
            logger.error(f"查询参数映射列表失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    # ==================== 表单 Schema 读 ====================

    def get_form_schema(self, algo_type: str) -> Dict[str, Any]:
        """获取算法表单 Schema（用于前端动态表单）"""
        try:
            algo = self.repo.find_algorithm_by_type(algo_type)
            if not algo:
                return {
                    'success': False,
                    'message': f"No algorithm found for '{algo_type}'",
                    'code': 404,
                }

            params = self.repo.list_case_params_for_schema(algo_type)

            if not params:
                return {
                    'success': True,
                    'message': '',
                    'data': {
                        'algorithmType': algo_type,
                        'algorithmName': algo.name,
                        'description': algo.description,
                        'groups': [],
                        'fields': []
                    },
                }

            fields = []
            for param in params:
                field = {
                    'fieldCode': param.param_code,
                    'fieldName': param.param_name or param.param_code,
                    'fieldType': param.param_type,
                    'required': param.required,
                    'defaultValue': param.default_value,
                    'component': self._get_default_component(param.param_type),
                    'helpText': param.help_text,
                    'hidden': param.hidden,
                    'uiOrder': param.ui_order,
                    'uiGroup': 'basic',
                    'scope': param.scope or 'common'
                }

                fields.append(field)

            fields.sort(key=lambda x: (x['uiGroup'], x['uiOrder']))

            groups = {}
            for field in fields:
                group_name = field.pop('uiGroup')
                if group_name not in groups:
                    groups[group_name] = {
                        'name': group_name,
                        'label': '基础参数',
                        'fields': []
                    }
                groups[group_name]['fields'].append(field)

            return {
                'success': True,
                'message': '',
                'data': {
                    'algorithmType': algo_type,
                    'algorithmName': algo.name,
                    'description': algo.description,
                    'groups': list(groups.values()),
                    'fields': fields
                },
            }
        except Exception as e:
            logger.error(f"获取算法表单 Schema 失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    # ==================== 维度关联读 ====================

    def get_algorithm_dimensions(self, algo_type: str) -> Dict[str, Any]:
        """获取算法关联的评估维度（包含完整维度详情）"""
        try:
            relations = self.repo.list_dimension_relations(algo_type)

            dimension_ids = [r.dimension_id for r in relations]
            default_relation = next((r for r in relations if r.is_default), None)
            weights_map = {r.dimension_id: r.weight for r in relations}
            is_default_map = {r.dimension_id: r.is_default for r in relations}

            dimension_map = self.repo.list_dimensions_map_by_ids(dimension_ids)

            dimensions_detail = []
            for dim_id in dimension_ids:
                dim = dimension_map.get(dim_id)
                if dim:
                    dimensions_detail.append({
                        'id': dim.id,
                        'name': dim.name,
                        'description': dim.description,
                        'type': dim.type,
                        'weight': weights_map.get(dim_id, 1.0),
                        'is_default': is_default_map.get(dim_id, False)
                    })

            return {
                'success': True,
                'message': '',
                'data': {
                    'dimensions': dimensions_detail,
                    'dimension_ids': dimension_ids,
                    'default_dimension_id': default_relation.dimension_id if default_relation else None,
                    'weights': weights_map
                },
            }
        except Exception as e:
            logger.error(f"获取算法关联维度失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    # ==================== 评估维度参数读 ====================

    def get_dimension_params(self, dimension_id: int) -> Dict[str, Any]:
        """获取评估维度的参数列表（含 output/input 完整字段，供 evaluation_service 跨服务调用）"""
        try:
            params = self.repo.list_dimension_params(dimension_id)

            params_list = []
            for p in params:
                params_list.append({
                    'id': p.id,
                    'dimension_id': p.dimension_id,
                    'code': p.param_code,
                    'param_code': p.param_code,
                    'name': p.param_name,
                    'param_name': p.param_name,
                    'label': p.label,
                    'field_type': p.field_type,
                    'param_direction': p.param_direction,
                    'field_path': p.field_path,
                    'agg_role': p.agg_role,
                    'output_role': p.output_role,
                    'visible_in_report': p.visible_in_report if p.visible_in_report is not None else True,
                    'required': p.required,
                    'default_value': p.default_value,
                    'help_text': p.help_text,
                    'ui_order': p.ui_order
                })

            return {'success': True, 'message': '', 'data': {'params': params_list}}
        except Exception as e:
            logger.error(f"获取评估维度参数失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    # ==================== 提取 / 热更新 ====================

    def extract_params(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """提取用例算法参数（供执行引擎使用）"""
        case_config = data.get('case_config')
        if case_config is None:
            return {'success': False, 'message': 'case_config is required', 'code': 400}

        try:
            result = self.repo.algo_extract_case_all_params(case_config)
            return {'success': True, 'message': '', 'data': result}
        except Exception as e:
            logger.error(f"提取用例算法参数失败: {e}")
            return {'success': False, 'message': f'提取失败: {e}', 'code': 500}

    def reload_config(self) -> Dict[str, Any]:
        """重新加载配置（热更新）"""
        try:
            reload_result = self.repo.algo_reload_config()

            return {
                'success': True,
                'message': 'Config reloaded',
                'data': {
                    'success': True,
                    'message': f"Config reloaded: {bool(reload_result)}",
                    'reload_time': (reload_result or {}).get('reload_time') if isinstance(reload_result, dict) else None
                },
            }
        except Exception as e:
            logger.error(f"重新加载配置失败: {e}")
            return {'success': False, 'message': f'重载失败: {e}', 'code': 500}

    # ==================== 内部辅助 ====================

    @staticmethod
    def _get_default_component(field_type: str) -> str:
        """获取默认前端组件"""
        component_map = {
            'select': 'select',
            'text': 'input',
            'textarea': 'textarea',
            'number': 'input-number',
            'boolean': 'switch',
            'json': 'code-editor',
            'slider': 'slider'
        }
        return component_map.get(field_type, 'input')
