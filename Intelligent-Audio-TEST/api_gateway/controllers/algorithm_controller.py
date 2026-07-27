# -*- coding: utf-8 -*-
"""
算法配置 Controller

提供算法定义、参数、映射的 CRUD API
"""

from typing import List, Dict, Any
from flask import request
from shared.models.algorithm_models import (
    AlgorithmDefinition, AlgorithmDeviceParam, AlgorithmApiParam,
    ParamMapping, AlgorithmDimensionRelation, CaseAlgorithmParam, EvaluationDimensionParam,
    AlgorithmReferenceParam
)
from shared.models.database import db
# TODO: 跨服务依赖，应改为 HTTP 调用
from shared.utils.algorithm_config_loader import AlgorithmConfigLoader
# TODO: 跨服务依赖，应改为 HTTP 调用
from shared.utils.case_parameter_extractor import CaseParameterExtractor
from shared.utils.response import success_response, error_response
from shared.models.models import Dimension
from ..schemas.algorithm import (
    AlgorithmListQuery,
    AlgorithmDetailResponse,
    AlgorithmDefinitionCreate,
    AlgorithmDefinitionUpdate,
    AlgorithmDeviceParamCreate,
    AlgorithmDeviceParamUpdate,
    AlgorithmApiParamCreate,
    AlgorithmApiParamUpdate,
    CaseAlgorithmParamCreate,
    CaseAlgorithmParamUpdate,
    MappingCreateRequest,
    MappingUpdateRequest,
    ReferenceParamCreateRequest,
    ReferenceParamUpdateRequest,
    AssociateDimensionsRequest,
    DimensionRelationCreateRequest,
    DimensionRelationUpdateRequest,
    ExtractParamsRequest,
    AlgorithmImportRequest,
    BulkDeleteRequest,
)


def _serialize_algorithm(algo_type: str) -> AlgorithmDetailResponse:
    """序列化算法定义及其关联数据"""
    algo_def = AlgorithmDefinition.query.filter_by(type=algo_type, deleted=False).first()
    if not algo_def:
        return None

    device_params = AlgorithmDeviceParam.query.filter_by(algorithm_type=algo_type, deleted=False).order_by(AlgorithmDeviceParam.ui_order).all()
    api_params = AlgorithmApiParam.query.filter_by(algorithm_type=algo_type, deleted=False).order_by(AlgorithmApiParam.ui_order).all()
    case_params = CaseAlgorithmParam.query.filter_by(algorithm_type=algo_type, deleted=False).order_by(CaseAlgorithmParam.ui_order).all()
    mappings = ParamMapping.query.filter_by(algorithm_type=algo_type, deleted=False).all()
    dimension_relations = AlgorithmDimensionRelation.query.filter_by(algorithm_type=algo_type, deleted=False).all()
    reference_params = AlgorithmReferenceParam.query.filter_by(algorithm_type=algo_type, deleted=False).order_by(AlgorithmReferenceParam.id).all()

    return AlgorithmDetailResponse(
        id=algo_def.id,
        type=algo_def.type,
        name=algo_def.name,
        group_id=algo_def.group_id,
        group_name=algo_def.group.name if algo_def.group else None,
        description=algo_def.description,
        status=algo_def.status,
        icon=algo_def.icon,
        display_order=algo_def.display_order,
        device_params=[_serialize_device_param(p) for p in device_params],
        api_params=[_serialize_api_param(p) for p in api_params],
        case_params=[_serialize_case_param(p) for p in case_params],
        params=[_serialize_device_param(p) for p in device_params],
        mappings=_serialize_mappings(mappings),
        dimension_relations=[_serialize_dimension_relation(r) for r in dimension_relations],
        associated_dimensions=[_serialize_dimension_relation(r) for r in dimension_relations],
        reference_params=[_serialize_reference_param(p) for p in reference_params],
        created_at=algo_def.created_at,
        updated_at=algo_def.updated_at
    )


def _serialize_device_param(param: AlgorithmDeviceParam) -> Dict[str, Any]:
    """序列化设备参数"""
    return param.to_dict()

def _serialize_api_param(param: AlgorithmApiParam) -> Dict[str, Any]:
    """序列化API参数"""
    return param.to_dict()

def _serialize_case_param(param: CaseAlgorithmParam) -> Dict[str, Any]:
    """序列化用例专属参数"""
    return param.to_dict()

def _serialize_dimension_relation(rel: AlgorithmDimensionRelation) -> Dict[str, Any]:
    """序列化评估维度关联"""
    return rel.to_dict()

def _serialize_reference_param(param: AlgorithmReferenceParam) -> Dict[str, Any]:
    """序列化参考参数"""
    return param.to_dict()

def _serialize_mappings(mappings: List[ParamMapping]) -> Dict[str, Any]:
    """序列化参数映射，按源类型(source)分组"""
    result = {'device': [], 'api': [], 'evaluation': []}
    for m in mappings:
        mapping_dict = m.to_dict()
        if m.dimension_id is not None:
            result['evaluation'].append(mapping_dict)
        elif m.source in result:
            result[m.source].append(mapping_dict)
    return result


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


def get_algorithm_options():
    """获取算法选项列表（用于下拉选择）"""
    algorithms = AlgorithmDefinition.query.filter_by(
        deleted=False, status='online'
    ).order_by(AlgorithmDefinition.display_order, AlgorithmDefinition.id).all()
    
    options = [
        {
            'value': a.type,
            'name': a.name,
            'group_id': a.group_id,
            'group_name': a.group.name if a.group else None
        }
        for a in algorithms
    ]
    
    return success_response({
        'algorithms': options
    })


def get_algorithm(algo_type: str):
    """获取算法详情"""
    algo_data = _serialize_algorithm(algo_type)
    if not algo_data:
        return error_response('Algorithm not found', 404)
    return success_response(algo_data)


def create_algorithm():
    """创建算法定义"""
    try:
        req = AlgorithmDefinitionCreate.model_validate(request.get_json())
    except Exception as e:
        return error_response(f"请求数据验证失败: {str(e)}", 400)
    
    if AlgorithmDefinition.query.filter_by(type=req.type, deleted=False).first():
        return error_response(f"Algorithm '{req.type}' already exists")

    algo_def = AlgorithmDefinition(
        type=req.type,
        name=req.name or req.type,
        group_id=req.group_id,
        description=req.description,
        status=req.status or 'online',
        icon=req.icon,
        display_order=req.display_order or 0,
    )
    db.session.add(algo_def)
    
    if req.device_params is not None:
        _update_params(req.type, req.device_params, 'device')
    if req.api_params is not None:
        _update_params(req.type, req.api_params, 'api')
    if req.case_params is not None:
        _update_case_params(req.type, req.case_params)
    if req.mappings is not None:
        _update_mappings(req.type, req.mappings)
    if req.associated_dimensions is not None:
        _update_associated_dimensions(req.type, req.associated_dimensions)
    
    db.session.commit()

    return success_response(_serialize_algorithm(req.type), 'Algorithm created')


def update_algorithm(algo_type: str):
    """更新算法定义"""
    req_data = AlgorithmDefinitionUpdate.model_validate(request.get_json())

    algo_def = AlgorithmDefinition.query.filter_by(type=algo_type, deleted=False).first()
    if not algo_def:
        return error_response('Algorithm not found', 404)

    if req_data.name is not None:
        algo_def.name = req_data.name
    if req_data.group_id is not None:
        algo_def.group_id = req_data.group_id
    if req_data.description is not None:
        algo_def.description = req_data.description
    if req_data.status is not None:
        algo_def.status = req_data.status
    if req_data.icon is not None:
        algo_def.icon = req_data.icon
    if req_data.display_order is not None:
        algo_def.display_order = req_data.display_order

    if req_data.device_params is not None:
        _update_params(algo_type, req_data.device_params, 'device')
    if req_data.api_params is not None:
        _update_params(algo_type, req_data.api_params, 'api')
    if req_data.case_params is not None:
        _update_case_params(algo_type, req_data.case_params)
    if req_data.mappings is not None:
        _update_mappings(algo_type, req_data.mappings)
    if req_data.associated_dimensions is not None:
        _update_associated_dimensions(algo_type, req_data.associated_dimensions)

    db.session.commit()

    return success_response(_serialize_algorithm(algo_type), 'Algorithm updated')


def _update_associated_dimensions(algo_type: str, dimensions_data: List[Dict]):
    """更新关联的评估维度"""
    existing_relations = AlgorithmDimensionRelation.query.filter_by(
        algorithm_type=algo_type, deleted=False
    ).all()
    existing_dim_ids = {r.dimension_id for r in existing_relations}
    
    submitted_dim_ids = set()
    
    for dim_data in dimensions_data:
        dim_id = dim_data.get('dimension_id') or dim_data.get('id')
        weight = dim_data.get('weight', 1.0)
        is_default = dim_data.get('is_default', False)
        
        if dim_id:
            submitted_dim_ids.add(dim_id)
            
            if dim_id in existing_dim_ids:
                relation = AlgorithmDimensionRelation.query.filter_by(
                    algorithm_type=algo_type, dimension_id=dim_id, deleted=False
                ).first()
                if relation:
                    relation.weight = weight
                    relation.is_default = is_default
            else:
                relation = AlgorithmDimensionRelation(
                    algorithm_type=algo_type,
                    dimension_id=dim_id,
                    is_default=is_default,
                    weight=weight
                )
                db.session.add(relation)
    
    for relation in existing_relations:
        if relation.dimension_id not in submitted_dim_ids:
            relation.deleted = True


def _update_params(algo_type: str, params: List[Dict], param_type: str):
    """更新参数"""
    ParamModel = AlgorithmApiParam if param_type == 'api' else AlgorithmDeviceParam
    
    existing_ids = {p.id for p in ParamModel.query.filter_by(algorithm_type=algo_type, deleted=False).all()}
    submitted_ids = set()

    for param_data in params:
        param_id = param_data.get('id')
        param_code = param_data.get('param_code')
        direction = param_data.get('direction', 'input')
        
        if param_id:
            param = ParamModel.query.filter_by(id=param_id, deleted=False).first()
            if param:
                submitted_ids.add(param_id)
                for field in ['param_name', 'label', 'param_type', 'direction', 'required', 
                              'default_value', 'validation_rules', 'help_text', 'ui_order', 'hidden']:
                    if field in param_data:
                        setattr(param, field, param_data[field])
        else:
            existing_param = ParamModel.query.filter_by(
                algorithm_type=algo_type,
                param_code=param_code,
                direction=direction,
                deleted=False
            ).first()
            
            if existing_param:
                submitted_ids.add(existing_param.id)
                for field in ['param_name', 'label', 'param_type', 'required', 
                              'default_value', 'validation_rules', 'help_text', 'ui_order', 'hidden']:
                    if field in param_data:
                        setattr(existing_param, field, param_data[field])
            else:
                param = ParamModel(
                    algorithm_type=algo_type,
                    param_code=param_code,
                    param_name=param_data.get('param_name'),
                    label=param_data.get('label'),
                    param_type=param_data.get('param_type', 'text'),
                    direction=direction,
                    required=param_data.get('required', False),
                    default_value=param_data.get('default_value'),
                    validation_rules=param_data.get('validation_rules'),
                    help_text=param_data.get('help_text'),
                    ui_order=param_data.get('ui_order', 0),
                    hidden=param_data.get('hidden', False)
                )
                db.session.add(param)

    for old_id in existing_ids - submitted_ids:
        param = ParamModel.query.filter_by(id=old_id).first()
        if param:
            param.deleted = True


def _update_case_params(algo_type: str, params: List[Dict]):
    """更新用例专属参数"""
    valid_scopes = {'common', 'api', 'e2e'}
    existing_params = CaseAlgorithmParam.query.filter_by(algorithm_type=algo_type, deleted=False).all()
    existing_ids = {p.id for p in existing_params}
    submitted_ids = set()

    for param_data in params:
        param_id = param_data.get('id')
        if param_id:
            param = CaseAlgorithmParam.query.filter_by(id=param_id, deleted=False).first()
            if param:
                submitted_ids.add(param_id)
                for field in ['param_name', 'label', 'param_type', 'required', 
                              'default_value',
                              'help_text', 'ui_order', 'hidden', 'scope',
                              'min_value', 'max_value', 'step', 'unit']:
                    if field in param_data and param_data[field] is not None:
                        if field == 'scope' and param_data[field] not in valid_scopes:
                            continue
                        setattr(param, field, param_data[field])
        else:
            raw_scope = param_data.get('scope', 'common')
            scope_value = raw_scope if raw_scope in valid_scopes else 'common'
            # 查重：避免唯一约束冲突
            pc = param_data.get('param_code')
            if not pc:
                continue
            dup = CaseAlgorithmParam.query.filter_by(
                algorithm_type=algo_type, param_code=pc, deleted=False
            ).first()
            if dup:
                # 已存在则更新
                for field in ['param_name', 'label', 'param_type', 'required',
                              'default_value',
                              'help_text', 'ui_order', 'hidden', 'scope',
                              'min_value', 'max_value', 'step', 'unit']:
                    if field in param_data and param_data[field] is not None:
                        if field == 'scope' and param_data[field] not in valid_scopes:
                            continue
                        setattr(dup, field, param_data[field])
                continue
            # 软删除的同名参数 → 复活而非新建（避免唯一约束冲突）
            soft_dup = CaseAlgorithmParam.query.filter_by(
                algorithm_type=algo_type, param_code=pc, deleted=True
            ).first()
            if soft_dup:
                soft_dup.deleted = False
                for field in ['param_name', 'label', 'param_type', 'required',
                              'default_value',
                              'help_text', 'ui_order', 'hidden', 'scope',
                              'min_value', 'max_value', 'step', 'unit']:
                    if field in param_data and param_data[field] is not None:
                        if field == 'scope' and param_data[field] not in valid_scopes:
                            continue
                        setattr(soft_dup, field, param_data[field])
                continue
            param = CaseAlgorithmParam(
                algorithm_type=algo_type,
                param_code=pc,
                param_name=param_data.get('param_name'),
                label=param_data.get('label'),
                param_type=param_data.get('param_type', 'text'),
                required=param_data.get('required', False),
                default_value=param_data.get('default_value'),
                help_text=param_data.get('help_text'),
                ui_order=param_data.get('ui_order', 0),
                hidden=param_data.get('hidden', False),
                scope=scope_value,
                min_value=param_data.get('min_value'),
                max_value=param_data.get('max_value'),
                step=param_data.get('step'),
                unit=param_data.get('unit')
            )
            db.session.add(param)

    for old_id in existing_ids - submitted_ids:
        param = CaseAlgorithmParam.query.filter_by(id=old_id).first()
        if param:
            param.deleted = True


def _update_mappings(algo_type: str, mappings: Dict):
    """更新映射"""
    existing_mappings = ParamMapping.query.filter_by(algorithm_type=algo_type, deleted=False).all()
    existing_ids = {m.id for m in existing_mappings}
    submitted_ids = set()

    for source_type, mapping_list in mappings.items():
        if source_type not in ('device', 'api', 'evaluation'):
            continue
        for mapping_data in mapping_list:
            mapping_id = mapping_data.get('id')
            if mapping_id:
                mapping = ParamMapping.query.filter_by(id=mapping_id, deleted=False).first()
                if mapping:
                    submitted_ids.add(mapping_id)
                    for field in ['source', 'source_param', 'source_direction', 'dimension_id', 'target_param', 'transform_type']:
                        if field in mapping_data:
                            setattr(mapping, field, mapping_data[field])
                    if source_type == 'evaluation':
                        mapping.source = mapping_data.get('source', 'case')
            else:
                source_value = mapping_data.get('source', 'case') if source_type == 'evaluation' else source_type
                mapping = ParamMapping(
                    algorithm_type=algo_type,
                    source_type=source_value if source_value in ('device', 'api', 'case', 'reference') else 'api',
                    source=source_value,
                    source_param=mapping_data.get('source_param'),
                    source_direction=mapping_data.get('source_direction', 'output'),
                    dimension_id=mapping_data.get('dimension_id'),
                    target_param=mapping_data.get('target_param'),
                    transform_type=mapping_data.get('transform_type', 'none')
                )
                db.session.add(mapping)

    for old_id in existing_ids - submitted_ids:
        mapping = ParamMapping.query.filter_by(id=old_id).first()
        if mapping:
            mapping.deleted = True


def delete_algorithm(algo_type: str):
    """删除算法定义（软删除）"""
    algo_def = AlgorithmDefinition.query.filter_by(type=algo_type, deleted=False).first()
    if not algo_def:
        return error_response('Algorithm not found', 404)

    algo_def.deleted = True
    db.session.commit()

    return success_response(None, 'Algorithm deleted')


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


def get_param(param_id: int):
    """获取参数详情"""
    param = AlgorithmDeviceParam.query.filter_by(id=param_id, deleted=False).first()
    if param:
        return success_response(_serialize_device_param(param))
    param = AlgorithmApiParam.query.filter_by(id=param_id, deleted=False).first()
    if param:
        return success_response(_serialize_api_param(param))
    return error_response('Parameter not found', 404)


def create_param():
    """创建参数（支持设备参数和API参数）"""
    json_data = request.get_json()
    param_type_source = json_data.get('param_type_source', 'device')

    if param_type_source == 'api':
        try:
            req = AlgorithmApiParamCreate.model_validate(json_data)
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)
    else:
        try:
            req = AlgorithmDeviceParamCreate.model_validate(json_data)
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

    if not req.algorithm_type or not req.param_code:
        return error_response('algorithm_type and param_code are required')

    if param_type_source == 'api':
        existing = AlgorithmApiParam.query.filter_by(
            algorithm_type=req.algorithm_type,
            param_code=req.param_code,
            direction=req.direction or 'input',
            deleted=False
        ).first()
        if existing:
            return error_response(f"API Parameter '{req.param_code}' already exists for algorithm '{req.algorithm_type}'")

        param = AlgorithmApiParam(
            algorithm_type=req.algorithm_type,
            param_code=req.param_code,
            param_name=req.param_name,
            label=req.label,
            param_type=req.param_type or 'text',
            direction=req.direction or 'input',
            required=req.required or False,
            default_value=req.default_value,
            validation_rules=req.validation_rules,
            help_text=req.help_text,
            ui_order=req.ui_order or 0,
            hidden=req.hidden or False
        )
    else:
        existing = AlgorithmDeviceParam.query.filter_by(
            algorithm_type=req.algorithm_type,
            param_code=req.param_code,
            direction=req.direction or 'input',
            deleted=False
        ).first()
        if existing:
            return error_response(f"Device Parameter '{req.param_code}' already exists for algorithm '{req.algorithm_type}'")

        param = AlgorithmDeviceParam(
            algorithm_type=req.algorithm_type,
            param_code=req.param_code,
            param_name=req.param_name,
            label=req.label,
            param_type=req.param_type or 'text',
            direction=req.direction or 'input',
            required=req.required or False,
            default_value=req.default_value,
            validation_rules=req.validation_rules,
            help_text=req.help_text,
            ui_order=req.ui_order or 0,
            hidden=req.hidden or False
        )

    db.session.add(param)
    db.session.commit()

    if param_type_source == 'api':
        return success_response(_serialize_api_param(param), 'Parameter created')
    else:
        return success_response(_serialize_device_param(param), 'Parameter created')


def update_param(param_id: int):
    """更新参数"""
    param = AlgorithmDeviceParam.query.filter_by(id=param_id, deleted=False).first()
    if not param:
        param = AlgorithmApiParam.query.filter_by(id=param_id, deleted=False).first()
        if not param:
            return error_response('Parameter not found', 404)
        param_type = 'api'
        try:
            req = AlgorithmApiParamUpdate.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)
    else:
        param_type = 'device'
        try:
            req = AlgorithmDeviceParamUpdate.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

    updatable_fields = [
        'param_code', 'param_name', 'label', 'param_type', 'direction', 'required', 'default_value',
        'validation_rules', 'help_text', 'ui_order', 'hidden'
    ]

    for field in updatable_fields:
        value = getattr(req, field, None)
        if value is not None:
            setattr(param, field, value)

    db.session.commit()

    if param_type == 'api':
        return success_response(_serialize_api_param(param), 'Parameter updated')
    else:
        return success_response(_serialize_device_param(param), 'Parameter updated')


def delete_param(param_id: int):
    """删除参数（软删除）"""
    param = AlgorithmDeviceParam.query.filter_by(id=param_id, deleted=False).first()
    if param:
        param.deleted = True
        db.session.commit()
        return success_response(None, 'Parameter deleted')

    param = AlgorithmApiParam.query.filter_by(id=param_id, deleted=False).first()
    if param:
        param.deleted = True
        db.session.commit()
        return success_response(None, 'Parameter deleted')

    return error_response('Parameter not found', 404)


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


def create_mapping():
    """创建参数映射"""
    try:
        req = MappingCreateRequest.model_validate(request.get_json())
    except Exception as e:
        return error_response(f"请求数据验证失败: {str(e)}", 400)

    mapping = ParamMapping(
        algorithm_type=req.algorithm_type,
        source=req.source_type,
        source_param=req.source_param,
        source_direction=req.source_direction or 'output',
        dimension_id=req.dimension_id,
        target_param=req.target_param,
        transform_type=req.transform_type or 'none'
    )
    db.session.add(mapping)
    db.session.commit()

    return success_response({
        'id': mapping.id,
        'algorithm_type': mapping.algorithm_type,
        'source': mapping.source,
        'source_param': mapping.source_param,
        'source_direction': mapping.source_direction,
        'dimension_id': mapping.dimension_id,
        'dimension_name': mapping.dimension.name if mapping.dimension else None,
        'target_param': mapping.target_param,
        'transform_type': mapping.transform_type
    }, 'Mapping created')


def delete_mapping(mapping_id: int):
    """删除参数映射"""
    mapping = ParamMapping.query.filter_by(id=mapping_id, deleted=False).first()
    if not mapping:
        return error_response('Mapping not found', 404)

    mapping.deleted = True
    db.session.commit()

    return success_response(None, 'Mapping deleted')


def update_mapping(mapping_id: int):
    """更新参数映射"""
    try:
        req = MappingUpdateRequest.model_validate(request.get_json())
    except Exception as e:
        return error_response(f"请求数据验证失败: {str(e)}", 400)

    mapping = ParamMapping.query.filter_by(id=mapping_id, deleted=False).first()
    if not mapping:
        return error_response('Mapping not found', 404)

    if req.source_type is not None:
        mapping.source = req.source_type
    if req.source_param is not None:
        mapping.source_param = req.source_param
    if req.source_direction is not None:
        mapping.source_direction = req.source_direction
    if req.dimension_id is not None:
        mapping.dimension_id = req.dimension_id
    if req.target_param is not None:
        mapping.target_param = req.target_param
    if req.transform_type is not None:
        mapping.transform_type = req.transform_type

    db.session.commit()

    return success_response({
        'id': mapping.id,
        'algorithm_type': mapping.algorithm_type,
        'source': mapping.source,
        'source_param': mapping.source_param,
        'source_direction': mapping.source_direction,
        'dimension_id': mapping.dimension_id,
        'dimension_name': mapping.dimension.name if mapping.dimension else None,
        'target_param': mapping.target_param,
        'transform_type': mapping.transform_type
    }, 'Mapping updated')


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


def get_case_param(param_id: int):
    """获取单个用例专属参数"""
    param = CaseAlgorithmParam.query.filter_by(id=param_id, deleted=False).first()
    if not param:
        return error_response('Case parameter not found', 404)
    return success_response(param.to_dict())


def create_case_param():
    """创建用例专属参数"""
    try:
        req = CaseAlgorithmParamCreate.model_validate(request.get_json())
    except Exception as e:
        return error_response(f"请求数据验证失败: {str(e)}", 400)

    existing = CaseAlgorithmParam.query.filter_by(
        algorithm_type=req.algorithm_type,
        param_code=req.param_code,
        deleted=False
    ).first()
    if existing:
        return error_response(f"Case parameter '{req.param_code}' already exists for algorithm '{req.algorithm_type}'")

    # 软删除的同名参数 → 复活而非新建（避免唯一约束冲突）
    soft_deleted = CaseAlgorithmParam.query.filter_by(
        algorithm_type=req.algorithm_type,
        param_code=req.param_code,
        deleted=True
    ).first()
    if soft_deleted:
        soft_deleted.deleted = False
        updatable_fields = {
            'param_name': req.param_name,
            'param_type': req.param_type,
            'required': req.required,
            'default_value': req.default_value,
            'help_text': req.help_text,
            'ui_order': req.ui_order,
            'hidden': req.hidden,
            'scope': req.scope,
            'min_value': req.min_value,
            'max_value': req.max_value,
            'step': req.step,
            'unit': req.unit,
        }
        for field, value in updatable_fields.items():
            if value is not None:
                setattr(soft_deleted, field, value)
        db.session.commit()
        return success_response(soft_deleted.to_dict(), 'Case parameter revived')

    param = CaseAlgorithmParam(
        algorithm_type=req.algorithm_type,
        param_code=req.param_code,
        param_name=req.param_name,
        label=req.label,
        param_type=req.param_type or 'text',
        required=req.required or False,
        default_value=req.default_value,
        help_text=req.help_text,
        ui_order=req.ui_order or 0,
        hidden=req.hidden or False,
        scope=req.scope or 'common',
        min_value=req.min_value,
        max_value=req.max_value,
        step=req.step,
        unit=req.unit
    )
    db.session.add(param)
    db.session.commit()

    return success_response(param.to_dict(), 'Case parameter created')


def update_case_param(param_id: int):
    """更新用例专属参数"""
    try:
        req = CaseAlgorithmParamUpdate.model_validate(request.get_json())
    except Exception as e:
        return error_response(f"请求数据验证失败: {str(e)}", 400)

    param = CaseAlgorithmParam.query.filter_by(id=param_id, deleted=False).first()
    if not param:
        return error_response('Case parameter not found', 404)

    updatable_fields = [
        'param_name', 'label', 'param_type', 'required', 'default_value',
        'help_text', 'ui_order', 'hidden', 'scope',
        'min_value', 'max_value', 'step', 'unit'
    ]
    raw_data = request.get_json() or {}
    for field in updatable_fields:
        # 检查字段是否在请求中（支持 snake_case 和 camelCase）
        if field in raw_data or field.replace('_', '') in raw_data:
            value = getattr(req, field, None)
            setattr(param, field, value)

    db.session.commit()

    return success_response(param.to_dict(), 'Case parameter updated')


def delete_case_param(param_id: int):
    """删除用例专属参数"""
    param = CaseAlgorithmParam.query.filter_by(id=param_id, deleted=False).first()
    if not param:
        return error_response('Case parameter not found', 404)

    param.deleted = True
    db.session.commit()

    return success_response(None, 'Case parameter deleted')


def list_reference_params():
    """获取参考参数列表"""
    algorithm_type = request.args.get('algorithm_type')
    
    if not algorithm_type:
        return error_response('algorithm_type is required')
    
    params = AlgorithmReferenceParam.query.filter_by(
        algorithm_type=algorithm_type, deleted=False
    ).order_by(AlgorithmReferenceParam.id).all()
    
    return success_response({
        'parameters': [p.to_dict() for p in params],
        'total': len(params)
    })


def create_reference_param():
    """创建参考参数"""
    try:
        req = ReferenceParamCreateRequest.model_validate(request.get_json())
    except Exception as e:
        return error_response(f"请求数据验证失败: {str(e)}", 400)

    existing = AlgorithmReferenceParam.query.filter_by(
        algorithm_type=req.algorithm_type, code=req.code, deleted=False
    ).first()
    if existing:
        return error_response(f"Reference parameter '{req.code}' already exists for algorithm '{req.algorithm_type}'")
    
    new_param = AlgorithmReferenceParam(
        algorithm_type=req.algorithm_type,
        code=req.code,
        name=req.name or '',
        param_type=req.type or 'text',
        annotation_code=req.annotation_code,
        annotation_format=req.annotation_format,
        field_path=req.field_path,
        merge_mode=req.merge_mode or 'join',
        help_text=req.help_text or ''
    )
    db.session.add(new_param)
    db.session.commit()
    
    return success_response(new_param.to_dict(), 'Reference parameter created')


def update_reference_param(param_id: int):
    """更新参考参数"""
    try:
        req = ReferenceParamUpdateRequest.model_validate(request.get_json())
    except Exception as e:
        return error_response(f"请求数据验证失败: {str(e)}", 400)
    
    relation = AlgorithmReferenceParam.query.filter_by(
        id=param_id, deleted=False
    ).first()
    
    if not relation:
        return error_response('Reference parameter not found', 404)
    
    if req.code:
        relation.code = req.code
    if req.name is not None:
        relation.name = req.name
    if req.type:
        relation.param_type = req.type
    if req.annotation_code is not None:
        relation.annotation_code = req.annotation_code
    if req.annotation_format is not None:
        relation.annotation_format = req.annotation_format
    if req.field_path is not None:
        relation.field_path = req.field_path
    if req.merge_mode is not None:
        relation.merge_mode = req.merge_mode
    if req.help_text is not None:
        relation.help_text = req.help_text
    
    db.session.commit()
    
    return success_response(relation.to_dict(), 'Reference parameter updated')


def delete_reference_param(param_id: int):
    """删除参考参数"""
    param = AlgorithmReferenceParam.query.filter_by(
        id=param_id, deleted=False
    ).first()
    
    if not param:
        return error_response('Reference parameter not found', 404)
    
    param.deleted = True
    db.session.commit()
    
    return success_response(None, 'Reference parameter deleted')


def get_algorithm_options():
    """获取算法选项（下拉框用）"""
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
            'component': _get_default_component(param.param_type),
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


def associate_dimensions(algo_type: str):
    """关联评估维度"""
    try:
        req = AssociateDimensionsRequest.model_validate(request.get_json() or {})
    except Exception as e:
        return error_response(f"请求数据验证失败: {str(e)}", 400)
    
    AlgorithmDimensionRelation.query.filter_by(
        algorithm_type=algo_type
    ).update({'deleted': True})
    
    if req.dimensions:
        for dim_data in req.dimensions:
            dim_id = dim_data.get('dimension_id') or dim_data.get('id')
            weight = dim_data.get('weight', 1.0)
            is_default = dim_data.get('is_default', False)
            
            if dim_id:
                relation = AlgorithmDimensionRelation(
                    algorithm_type=algo_type,
                    dimension_id=dim_id,
                    is_default=is_default,
                    weight=weight
                )
                db.session.add(relation)
    
    db.session.commit()

    return success_response(None, 'Dimensions associated')


def reload_config():
    """重新加载配置（热更新）"""
    loader = AlgorithmConfigLoader()
    reloaded = loader.reload_if_changed()

    return success_response({
        'success': True,
        'message': f"Config reloaded: {reloaded}",
        'reload_time': loader.get_last_reload_time()
    })


def create_dimension_relation():
    """创建单条维度关联"""
    try:
        req = DimensionRelationCreateRequest.model_validate(request.get_json())
    except Exception as e:
        return error_response(f"请求数据验证失败: {str(e)}", 400)
    
    if not req.algorithm_type or not req.dimension_id:
        return error_response('algorithm_type and dimension_id are required')
    
    existing = AlgorithmDimensionRelation.query.filter_by(
        algorithm_type=req.algorithm_type,
        dimension_id=req.dimension_id,
        deleted=False
    ).first()
    
    if existing:
        return error_response('Dimension relation already exists', 400)
    
    relation = AlgorithmDimensionRelation(
        algorithm_type=req.algorithm_type,
        dimension_id=req.dimension_id,
        is_default=req.is_default,
        weight=req.weight
    )
    db.session.add(relation)
    db.session.commit()
    
    return success_response(relation.to_dict(), 'Dimension relation created')


def update_dimension_relation(relation_id: int):
    """更新单条维度关联"""
    try:
        req = DimensionRelationUpdateRequest.model_validate(request.get_json())
    except Exception as e:
        return error_response(f"请求数据验证失败: {str(e)}", 400)
    
    relation = AlgorithmDimensionRelation.query.get(relation_id)
    if not relation:
        return error_response('Dimension relation not found', 404)
    
    if req.weight is not None:
        relation.weight = req.weight
    if req.is_default is not None:
        relation.is_default = req.is_default
    if req.dimension_id is not None:
        relation.dimension_id = req.dimension_id
    
    db.session.commit()
    
    return success_response(relation.to_dict(), 'Dimension relation updated')


def delete_dimension_relation(relation_id: int):
    """删除单条维度关联"""
    relation = AlgorithmDimensionRelation.query.get(relation_id)
    if not relation:
        return error_response('Dimension relation not found', 404)
    
    relation.deleted = True
    db.session.commit()
    
    return success_response(None, 'Dimension relation deleted')


def import_algorithms():
    """导入算法配置"""
    try:
        req = AlgorithmImportRequest.model_validate(request.get_json())
    except Exception as e:
        return error_response(f"请求数据验证失败: {str(e)}", 400)

    results = []
    for algo_data in req.algorithms:
        algo_type = algo_data.get('type')
        if not algo_type:
            continue

        algo_def = AlgorithmDefinition.query.filter_by(
            type=algo_type, deleted=False
        ).first()

        if not algo_def:
            algo_def = AlgorithmDefinition(
                type=algo_type,
                name=algo_data.get('name', algo_type),
                group_id=algo_data.get('group_id'),
                description=algo_data.get('description'),
                status=algo_data.get('status', 'online'),
                icon=algo_data.get('icon'),
                display_order=algo_data.get('display_order', 0)
            )
            db.session.add(algo_def)
            db.session.commit()

        params = algo_data.get('params', [])
        for param_data in params:
            param = AlgorithmDeviceParam(
                algorithm_type=algo_type,
                param_code=param_data.get('code'),
                param_name=param_data.get('name'),
                label=param_data.get('label'),
                param_type=param_data.get('type', 'text'),
                direction='input',
                required=param_data.get('required', False),
                default_value=param_data.get('default_value'),
                ui_order=param_data.get('ui_order', 0),
                hidden=param_data.get('hidden', False)
            )
            db.session.add(param)

        results.append(algo_type)

    db.session.commit()
    return success_response({'imported': results}, f"Imported {len(results)} algorithms")


def bulk_delete():
    """批量删除算法"""
    try:
        req = BulkDeleteRequest.model_validate(request.get_json())
    except Exception as e:
        return error_response(f"请求数据验证失败: {str(e)}", 400)
    
    if not req.algorithm_types:
        return error_response('Invalid request data')

    deleted = []

    for algo_type in req.algorithm_types:
        algo_def = AlgorithmDefinition.query.filter_by(
            type=algo_type, deleted=False
        ).first()
        if algo_def:
            algo_def.deleted = True
            deleted.append(algo_type)

    db.session.commit()
    return success_response({'deleted_types': deleted}, f"Deleted {len(deleted)} algorithms")


def extract_params():
    """提取用例算法参数（供执行引擎使用）"""
    try:
        req = ExtractParamsRequest.model_validate(request.get_json() or {})
    except Exception as e:
        return error_response(f"请求数据验证失败: {str(e)}", 400)

    result = CaseParameterExtractor.get_all_params(req.case_config)

    return success_response(result)


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
