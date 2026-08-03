# -*- coding: utf-8 -*-
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.controllers.algorithm_controller import (
    list_algorithms, get_algorithm, create_algorithm, update_algorithm,
    delete_algorithm, list_params, get_param, create_param, update_param,
    delete_param, list_mappings, create_mapping, update_mapping, delete_mapping,
    get_algorithm_options, get_form_schema,
    get_algorithm_dimensions, associate_dimensions, reload_config,
    import_algorithms, bulk_delete, extract_params, get_dimension_params,
    list_reference_params, create_reference_param, update_reference_param, delete_reference_param,
    create_dimension_relation, update_dimension_relation, delete_dimension_relation,
    list_case_params, get_case_param, create_case_param, update_case_param, delete_case_param
)
from api_gateway.controllers.algorithm_group_controller import AlgorithmGroupController
from api_gateway.routes._response import to_response

router = APIRouter()


# 算法定义相关路由
@router.get('/definitions')
def get_definitions():
    return to_response(list_algorithms())


@router.get('/definitions/{algo_type}')
def get_definition(algo_type: str):
    return to_response(get_algorithm(algo_type))


@router.post('/definitions')
def post_definition():
    return to_response(create_algorithm())


@router.put('/definitions/{algo_type}')
def put_definition(algo_type: str):
    return to_response(update_algorithm(algo_type))


@router.delete('/definitions/{algo_type}')
def delete_definition(algo_type: str):
    return to_response(delete_algorithm(algo_type))


# 算法分组相关路由
@router.get('/groups')
def get_groups():
    return to_response(AlgorithmGroupController.get_all())


@router.get('/groups/{group_id}')
def get_group(group_id: int):
    return to_response(AlgorithmGroupController.get_by_id(group_id))


@router.post('/groups')
def post_group():
    return to_response(AlgorithmGroupController.create())


@router.put('/groups/{group_id}')
def put_group(group_id: int):
    return to_response(AlgorithmGroupController.update(group_id))


@router.delete('/groups/{group_id}')
def delete_group(group_id: int):
    return to_response(AlgorithmGroupController.delete(group_id))


# 参数相关路由
@router.get('/params')
def get_params():
    return to_response(list_params())


@router.get('/params/{param_id}')
def get_param_by_id(param_id: int):
    return to_response(get_param(param_id))


@router.post('/params')
def post_param():
    return to_response(create_param())


@router.put('/params/{param_id}')
def put_param(param_id: int):
    return to_response(update_param(param_id))


@router.delete('/params/{param_id}')
def delete_param_by_id(param_id: int):
    return to_response(delete_param(param_id))


# 用例专属参数相关路由
@router.get('/case-params')
def get_case_params():
    return to_response(list_case_params())


@router.get('/case-params/{param_id}')
def get_case_param_by_id(param_id: int):
    return to_response(get_case_param(param_id))


@router.post('/case-params')
def post_case_param():
    return to_response(create_case_param())


@router.put('/case-params/{param_id}')
def put_case_param(param_id: int):
    return to_response(update_case_param(param_id))


@router.delete('/case-params/{param_id}')
def delete_case_param_by_id(param_id: int):
    return to_response(delete_case_param(param_id))


# 参考参数相关路由
@router.get('/reference-params')
def get_reference_params():
    return to_response(list_reference_params())


@router.post('/reference-params')
def post_reference_param():
    return to_response(create_reference_param())


@router.put('/reference-params/{param_id}')
def put_reference_param(param_id: int):
    return to_response(update_reference_param(param_id))


@router.delete('/reference-params/{param_id}')
def delete_reference_param_by_id(param_id: int):
    return to_response(delete_reference_param(param_id))


# 映射相关路由
@router.get('/mappings')
def get_mappings():
    return to_response(list_mappings())


@router.post('/mappings')
def post_mapping():
    return to_response(create_mapping())


@router.put('/mappings/{mapping_id}')
def put_mapping(mapping_id: int):
    return to_response(update_mapping(mapping_id))


@router.delete('/mappings/{mapping_id}')
def delete_mapping_by_id(mapping_id: int):
    return to_response(delete_mapping(mapping_id))


# 其他功能路由
@router.get('/options')
def get_options():
    return to_response(get_algorithm_options())


@router.get('/form-schema/{algo_type}')
def get_algo_form_schema(algo_type: str):
    return to_response(get_form_schema(algo_type))


@router.get('/dimensions/{algo_type}')
def get_dimensions(algo_type: str):
    return to_response(get_algorithm_dimensions(algo_type))


@router.post('/dimensions/{algo_type}')
def post_dimensions(algo_type: str):
    return to_response(associate_dimensions(algo_type))


@router.post('/dimension-relations')
def post_dimension_relation():
    return to_response(create_dimension_relation())


@router.put('/dimension-relations/{relation_id}')
def put_dimension_relation(relation_id: int):
    return to_response(update_dimension_relation(relation_id))


@router.delete('/dimension-relations/{relation_id}')
def delete_dimension_relation_by_id(relation_id: int):
    return to_response(delete_dimension_relation(relation_id))


@router.post('/reload')
def reload():
    return to_response(reload_config())


@router.post('/import')
def import_algo():
    return to_response(import_algorithms())


@router.post('/bulk-delete')
def bulk_delete_algos():
    return to_response(bulk_delete())


@router.post('/extract-params')
def extract():
    return to_response(extract_params())


@router.get('/dimension-params/{dimension_id}')
def get_dim_params(dimension_id: int):
    return to_response(get_dimension_params(dimension_id))
