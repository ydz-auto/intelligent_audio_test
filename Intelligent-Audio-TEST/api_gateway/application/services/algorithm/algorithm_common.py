# -*- coding: utf-8 -*-
"""算法配置共享序列化辅助函数。

从 algorithm_controller 中抽取，供 query / command 多个 service 共用。
"""
from typing import List, Dict, Any

from api_gateway.schemas.algorithm import AlgorithmDetailResponse
from api_gateway.infrastructure.acl import AlgorithmConfigAclRepositoryImpl

_algorithm_acl = AlgorithmConfigAclRepositoryImpl()


def _serialize_algorithm(algo_type: str) -> AlgorithmDetailResponse:
    """序列化算法定义及其关联数据

    通过 ACL 仓储调用 algorithm_service 获取算法详情。
    """
    # 通过 ACL 获取算法定义
    res = _algorithm_acl.get_algorithm(algo_type)
    if not res.get('success'):
        return None

    resp = res if isinstance(res, dict) else {}
    data = resp.get('data') if 'data' in resp else res
    # algorithm_config_service 的方法可能未经过 _resp 处理，尝试取 data
    if isinstance(data, str):
        import json
        data = json.loads(data) if data else {}
    algo_def = data if isinstance(data, dict) else {}

    if not algo_def:
        return None

    # 通过 gRPC 获取维度关联（替代直连 algorithm_service PO）
    dim_res = _algorithm_acl.get_algorithm_dimensions(algo_type)
    dim_relations = []
    if dim_res.get('success'):
        dim_data = dim_res.get('data') or []
        if isinstance(dim_data, list):
            dim_relations = dim_data
        elif isinstance(dim_data, dict) and 'items' in dim_data:
            dim_relations = dim_data.get('items', [])

    # 通过 gRPC获取映射（替代直连 algorithm_service PO）
    map_res = _algorithm_acl.list_mappings(algorithm_type=algo_type)
    mappings_data = []
    if map_res.get('success'):
        map_data = map_res.get('data') or []
        if isinstance(map_data, list):
            mappings_data = map_data
        elif isinstance(map_data, dict) and 'items' in map_data:
            mappings_data = map_data.get('items', [])

    # 通过 gRPC 获取参数（替代直连 algorithm_service PO）
    dev_params = []
    api_params = []
    case_params = []
    ref_params = []

    params_res = _algorithm_acl.list_params(algorithm_type=algo_type)
    if params_res.get('success'):
        params_data = params_res.get('data') or []
        params_items = params_data if isinstance(params_data, list) else (params_data.get('items', []) if isinstance(params_data, dict) else [])
        for p in params_items:
            p_type = p.get('param_type', '') if isinstance(p, dict) else ''
            if p_type == 'device':
                dev_params.append(p)
            elif p_type == 'api':
                api_params.append(p)

    case_params_res = _algorithm_acl.list_case_params(algorithm_type=algo_type)
    if case_params_res.get('success'):
        cp_data = case_params_res.get('data') or []
        case_params = cp_data if isinstance(cp_data, list) else (cp_data.get('items', []) if isinstance(cp_data, dict) else [])

    ref_params_res = _algorithm_acl.list_reference_params(algorithm_type=algo_type)
    if ref_params_res.get('success'):
        rp_data = ref_params_res.get('data') or []
        ref_params = rp_data if isinstance(rp_data, list) else (rp_data.get('items', []) if isinstance(rp_data, dict) else [])

    return AlgorithmDetailResponse(
        id=algo_def.get('id'),
        type=algo_def.get('type'),
        name=algo_def.get('name'),
        group_id=algo_def.get('group_id'),
        group_name=algo_def.get('group_name'),
        description=algo_def.get('description'),
        status=algo_def.get('status'),
        icon=algo_def.get('icon'),
        display_order=algo_def.get('display_order'),
        device_params=dev_params,
        api_params=api_params,
        case_params=case_params,
        params=dev_params,
        mappings=_serialize_mappings(mappings_data),
        dimension_relations=dim_relations,
        associated_dimensions=dim_relations,
        reference_params=ref_params,
        created_at=algo_def.get('created_at'),
        updated_at=algo_def.get('updated_at')
    )


def _serialize_mappings(mappings: List) -> Dict[str, Any]:
    """序列化参数映射，按源类型(source)分组

    mappings 为 gRPC 返回的 dict 列表（替代原 ORM 对象列表）。
    """
    result = {'device': [], 'api': [], 'evaluation': []}
    for m in mappings:
        mapping_dict = m if isinstance(m, dict) else {}
        if not mapping_dict:
            continue
        if mapping_dict.get('dimension_id') is not None:
            result['evaluation'].append(mapping_dict)
        elif mapping_dict.get('source') in result:
            result[mapping_dict.get('source')].append(mapping_dict)
    return result
