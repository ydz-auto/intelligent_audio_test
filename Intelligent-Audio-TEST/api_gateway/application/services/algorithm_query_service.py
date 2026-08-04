# -*- coding: utf-8 -*-
"""算法配置查询 Service（读侧）。

将 algorithm_controller 中的查询读侧函数迁移为 AlgorithmQueryService 的静态方法。
保留原有逻辑，不改业务。
"""
from typing import Dict, Any

from api_gateway.infrastructure.request_adapter import request
from shared.models.algorithm_models import (
    AlgorithmDefinition, AlgorithmDeviceParam, AlgorithmApiParam,
    ParamMapping, AlgorithmDimensionRelation, CaseAlgorithmParam,
    EvaluationDimensionParam
)
from shared.utils.response import success_response, error_response
from shared.models.models import Dimension
from api_gateway.schemas.algorithm import (
    AlgorithmListQuery,
    AlgorithmParamListQuery,
)
from .algorithm_common import (
    _serialize_algorithm,
    _serialize_device_param,
    _serialize_api_param,
    _serialize_case_param,
    _serialize_dimension_relation,
    _serialize_reference_param,
    _serialize_mappings,
)


class AlgorithmQueryService:
    # ========== 算法定义查询 ==========

    @staticmethod
    def list_algorithms():
        """获取算法定义列表"""
        query_params_dict = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
        query_params = AlgorithmListQuery.model_validate(query_params_dict)

        query = AlgorithmDefinition.query.filter_by(deleted=False)

        if query_params.status:
            query = query.filter_by(status=query_params.status)
        if query_params.group_id:
            query = query.filter_by(group_id=query_params.group_id)

        algorithms = query.order_by(
            AlgorithmDefinition.display_order, AlgorithmDefinition.id
        ).all()

        return success_response({
            'data': [_serialize_algorithm(a.type) for a in algorithms],
            'total': len(algorithms)
        })

    @staticmethod
    def get_algorithm_options():
        """获取算法选项（下拉框用）

        原文件有两次同名定义，保留逻辑更完整（含 icon 字段）的版本。
        """
        algorithms = AlgorithmDefinition.query.filter_by(
            status='online', deleted=False
        ).order_by(AlgorithmDefinition.display_order).all()

        return success_response({
            'algorithms': [
                {
                    'value': a.type,
                    'name': a.name,
                    'group_id': a.group_id,
                    'group_name': a.group.name if a.group else None,
                    'icon': a.icon
                }
                for a in algorithms
            ]
        })

    @staticmethod
    def get_algorithm(algo_type: str):
        """获取算法详情"""
        algo_data = _serialize_algorithm(algo_type)
        if not algo_data:
            return error_response('Algorithm not found', 404)
        return success_response(algo_data)

    # ========== 参数查询 ==========

    @staticmethod
    def list_params():
        """获取参数列表（支持设备参数和API参数）"""
        query_params_dict = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
        query_params = AlgorithmParamListQuery.model_validate(query_params_dict)
        algorithm_type = query_params.algorithm_type
        param_type = query_params.param_type

        if param_type == 'api':
            if algorithm_type:
                params = AlgorithmApiParam.query.filter_by(
                    algorithm_type=algorithm_type, deleted=False
                ).order_by(AlgorithmApiParam.ui_order).all()
            else:
                params = AlgorithmApiParam.query.filter_by(deleted=False).all()
            return success_response({
                'parameters': [_serialize_api_param(p) for p in params],
                'total': len(params)
            })
        else:
            if algorithm_type:
                params = AlgorithmDeviceParam.query.filter_by(
                    algorithm_type=algorithm_type, deleted=False
                ).order_by(AlgorithmDeviceParam.ui_order).all()
            else:
                params = AlgorithmDeviceParam.query.filter_by(deleted=False).all()
            return success_response({
                'parameters': [_serialize_device_param(p) for p in params],
                'total': len(params)
            })

    @staticmethod
    def get_param(param_id: int):
        """获取参数详情"""
        param = AlgorithmDeviceParam.query.filter_by(id=param_id, deleted=False).first()
        if param:
            return success_response(_serialize_device_param(param))
        param = AlgorithmApiParam.query.filter_by(id=param_id, deleted=False).first()
        if param:
            return success_response(_serialize_api_param(param))
        return error_response('Parameter not found', 404)

    # ========== 映射查询 ==========

    @staticmethod
    def list_mappings():
        """获取参数映射列表"""
        algorithm_type = request.args.get('algorithm_type')
        source_type = request.args.get('source_type')  # device 或 api
        dimension_id = request.args.get('dimension_id')

        query = ParamMapping.query.filter_by(deleted=False)
        if algorithm_type:
            query = query.filter_by(algorithm_type=algorithm_type)
        if source_type:
            query = query.filter_by(source=source_type)
        if dimension_id:
            query = query.filter_by(dimension_id=int(dimension_id))

        mappings = query.all()

        result = {
            'mappings': [
                {
                    'id': m.id,
                    'algorithm_type': m.algorithm_type,
                    'source': m.source,
                    'source_param': m.source_param,
                    'source_direction': m.source_direction,
                    'dimension_id': m.dimension_id,
                    'dimension_name': m.dimension.name if m.dimension else None,
                    'target_param': m.target_param,
                    'transform_type': m.transform_type
                }
                for m in mappings
            ],
            'total': len(mappings)
        }
        return success_response(result)

    # ========== 用例专属参数查询 ==========

    @staticmethod
    def list_case_params():
        """获取用例专属参数列表"""
        algorithm_type = request.args.get('algorithm_type')
        scope = request.args.get('scope')

        # scope 值校验
        valid_scopes = ('common', 'api', 'e2e')
        if scope and scope not in valid_scopes:
            return error_response(f"Invalid scope: '{scope}'. Must be one of {valid_scopes}", 400)

        query = CaseAlgorithmParam.query.filter_by(deleted=False)

        if algorithm_type:
            query = query.filter_by(algorithm_type=algorithm_type)

        if scope:
            query = query.filter(
                (CaseAlgorithmParam.scope == 'common') |
                (CaseAlgorithmParam.scope == scope)
            )

        params = query.order_by(CaseAlgorithmParam.ui_order).all()

        return success_response({
            'parameters': [p.to_dict() for p in params],
            'total': len(params)
        })

    @staticmethod
    def get_case_param(param_id: int):
        """获取单个用例专属参数"""
        param = CaseAlgorithmParam.query.filter_by(id=param_id, deleted=False).first()
        if not param:
            return error_response('Case parameter not found', 404)
        return success_response(param.to_dict())

    # ========== 参考参数查询 ==========

    @staticmethod
    def list_reference_params():
        """获取参考参数列表"""
        algorithm_type = request.args.get('algorithm_type')

        if not algorithm_type:
            return error_response('algorithm_type is required')

        from shared.models.algorithm_models import AlgorithmReferenceParam
        params = AlgorithmReferenceParam.query.filter_by(
            algorithm_type=algorithm_type, deleted=False
        ).order_by(AlgorithmReferenceParam.id).all()

        return success_response({
            'parameters': [p.to_dict() for p in params],
            'total': len(params)
        })

    # ========== 表单 Schema ==========

    @staticmethod
    def get_form_schema(algo_type: str):
        """获取算法表单 Schema（用于前端动态表单）"""
        from shared.models.algorithm_models import CaseAlgorithmParam, AlgorithmDefinition

        algo = AlgorithmDefinition.query.filter_by(type=algo_type, deleted=False).first()
        if not algo:
            return error_response(f"No algorithm found for '{algo_type}'", 404)

        params = CaseAlgorithmParam.query.filter_by(
            algorithm_type=algo_type, deleted=False, hidden=False
        ).order_by(CaseAlgorithmParam.ui_order).all()

        if not params:
            return success_response({
                'algorithmType': algo_type,
                'algorithmName': algo.name,
                'description': algo.description,
                'groups': [],
                'fields': []
            })

        fields = []
        for param in params:
            field = {
                'fieldCode': param.param_code,
                'fieldName': param.param_name or param.param_code,
                'fieldType': param.param_type,
                'required': param.required,
                'defaultValue': param.default_value,
                'component': AlgorithmQueryService._get_default_component(param.param_type),
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

        return success_response({
            'algorithmType': algo_type,
            'algorithmName': algo.name,
            'description': algo.description,
            'groups': list(groups.values()),
            'fields': fields
        })

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

    # ========== 维度查询 ==========

    @staticmethod
    def get_algorithm_dimensions(algo_type: str):
        """获取算法关联的评估维度（包含完整维度详情）"""
        relations = AlgorithmDimensionRelation.query.filter_by(
            algorithm_type=algo_type, deleted=False
        ).all()

        dimension_ids = [r.dimension_id for r in relations]
        default_relation = next((r for r in relations if r.is_default), None)
        weights_map = {r.dimension_id: r.weight for r in relations}
        is_default_map = {r.dimension_id: r.is_default for r in relations}

        dimensions = Dimension.query.filter(Dimension.id.in_(dimension_ids), Dimension.deleted == False).all()
        dimension_map = {d.id: d for d in dimensions}

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

        return success_response({
            'dimensions': dimensions_detail,
            'dimension_ids': dimension_ids,
            'default_dimension_id': default_relation.dimension_id if default_relation else None,
            'weights': weights_map
        })

    @staticmethod
    def get_dimension_params(dimension_id: int):
        """获取评估维度的参数列表"""
        params = EvaluationDimensionParam.query.filter_by(
            dimension_id=dimension_id, deleted=False
        ).order_by(EvaluationDimensionParam.ui_order).all()

        params_list = []
        for p in params:
            params_list.append({
                'id': p.id,
                'dimension_id': p.dimension_id,
                'code': p.param_code,
                'name': p.param_name,
                'label': p.label,
                'field_type': p.field_type,
                'required': p.required,
                'default_value': p.default_value,
                'help_text': p.help_text,
                'ui_order': p.ui_order
            })

        return success_response({'params': params_list})
