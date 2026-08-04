# -*- coding: utf-8 -*-
"""算法配置共享序列化辅助函数。

从 algorithm_controller 中抽取，供 query / command 多个 service 共用。
"""
from typing import List, Dict, Any

from shared.models.algorithm_models import (
    AlgorithmDefinition, AlgorithmDeviceParam, AlgorithmApiParam,
    ParamMapping, AlgorithmDimensionRelation, CaseAlgorithmParam,
    AlgorithmReferenceParam
)
from api_gateway.schemas.algorithm import AlgorithmDetailResponse


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
