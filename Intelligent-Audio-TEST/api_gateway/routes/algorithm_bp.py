# -*- coding: utf-8 -*-
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.application.services.algorithm.algorithm_query_service import AlgorithmQueryService
from api_gateway.application.services.algorithm.algorithm_command_service import AlgorithmCommandService
from api_gateway.application.services.algorithm.algorithm_group_service import AlgorithmGroupService
from api_gateway.routes._response import to_response

router = APIRouter()


# 算法定义相关路由
@router.get('/definitions')
def get_definitions(_: None = require_permission('algorithm:read')):
    return to_response(AlgorithmQueryService.list_algorithms())


@router.get('/definitions/{algo_type}')
def get_definition(algo_type: str, _: None = require_permission('algorithm:read')):
    return to_response(AlgorithmQueryService.get_algorithm(algo_type))


@router.post('/definitions')
def post_definition(_: None = require_permission('algorithm:definition_manage')):
    return to_response(AlgorithmCommandService.create_algorithm())


@router.put('/definitions/{algo_type}')
def put_definition(algo_type: str, _: None = require_permission('algorithm:definition_manage')):
    return to_response(AlgorithmCommandService.update_algorithm(algo_type))


@router.delete('/definitions/{algo_type}')
def delete_definition(algo_type: str, _: None = require_permission('algorithm:definition_manage')):
    return to_response(AlgorithmCommandService.delete_algorithm(algo_type))


# 算法分组相关路由
@router.get('/groups')
def get_groups(_: None = require_permission('algorithm:read')):
    return to_response(AlgorithmGroupService.get_all())


@router.get('/groups/{group_id}')
def get_group(group_id: int, _: None = require_permission('algorithm:read')):
    return to_response(AlgorithmGroupService.get_by_id(group_id))


@router.post('/groups')
def post_group(_: None = require_permission('algorithm:group_manage')):
    return to_response(AlgorithmGroupService.create())


@router.put('/groups/{group_id}')
def put_group(group_id: int, _: None = require_permission('algorithm:group_manage')):
    return to_response(AlgorithmGroupService.update(group_id))


@router.delete('/groups/{group_id}')
def delete_group(group_id: int, _: None = require_permission('algorithm:group_manage')):
    return to_response(AlgorithmGroupService.delete(group_id))


# 参数相关路由
@router.get('/params')
def get_params(_: None = require_permission('algorithm:read')):
    return to_response(AlgorithmQueryService.list_params())


@router.get('/params/{param_id}')
def get_param_by_id(param_id: int, _: None = require_permission('algorithm:read')):
    return to_response(AlgorithmQueryService.get_param(param_id))


@router.post('/params')
def post_param(_: None = require_permission('algorithm:param_manage')):
    return to_response(AlgorithmCommandService.create_param())


@router.put('/params/{param_id}')
def put_param(param_id: int, _: None = require_permission('algorithm:param_manage')):
    return to_response(AlgorithmCommandService.update_param(param_id))


@router.delete('/params/{param_id}')
def delete_param_by_id(param_id: int, _: None = require_permission('algorithm:param_manage')):
    return to_response(AlgorithmCommandService.delete_param(param_id))


# 用例专属参数相关路由
@router.get('/case-params')
def get_case_params(_: None = require_permission('algorithm:read')):
    return to_response(AlgorithmQueryService.list_case_params())


@router.get('/case-params/{param_id}')
def get_case_param_by_id(param_id: int, _: None = require_permission('algorithm:read')):
    return to_response(AlgorithmQueryService.get_case_param(param_id))


@router.post('/case-params')
def post_case_param(_: None = require_permission('algorithm:case_param_manage')):
    return to_response(AlgorithmCommandService.create_case_param())


@router.put('/case-params/{param_id}')
def put_case_param(param_id: int, _: None = require_permission('algorithm:case_param_manage')):
    return to_response(AlgorithmCommandService.update_case_param(param_id))


@router.delete('/case-params/{param_id}')
def delete_case_param_by_id(param_id: int, _: None = require_permission('algorithm:case_param_manage')):
    return to_response(AlgorithmCommandService.delete_case_param(param_id))


# 参考参数相关路由
@router.get('/reference-params')
def get_reference_params(_: None = require_permission('algorithm:read')):
    return to_response(AlgorithmQueryService.list_reference_params())


@router.post('/reference-params')
def post_reference_param(_: None = require_permission('algorithm:param_manage')):
    return to_response(AlgorithmCommandService.create_reference_param())


@router.put('/reference-params/{param_id}')
def put_reference_param(param_id: int, _: None = require_permission('algorithm:param_manage')):
    return to_response(AlgorithmCommandService.update_reference_param(param_id))


@router.delete('/reference-params/{param_id}')
def delete_reference_param_by_id(param_id: int, _: None = require_permission('algorithm:param_manage')):
    return to_response(AlgorithmCommandService.delete_reference_param(param_id))


# 映射相关路由
@router.get('/mappings')
def get_mappings(_: None = require_permission('algorithm:read')):
    return to_response(AlgorithmQueryService.list_mappings())


@router.post('/mappings')
def post_mapping(_: None = require_permission('algorithm:definition_manage')):
    return to_response(AlgorithmCommandService.create_mapping())


@router.put('/mappings/{mapping_id}')
def put_mapping(mapping_id: int, _: None = require_permission('algorithm:definition_manage')):
    return to_response(AlgorithmCommandService.update_mapping(mapping_id))


@router.delete('/mappings/{mapping_id}')
def delete_mapping_by_id(mapping_id: int, _: None = require_permission('algorithm:definition_manage')):
    return to_response(AlgorithmCommandService.delete_mapping(mapping_id))


# 其他功能路由
@router.get('/options')
def get_options(_: None = require_permission('algorithm:read')):
    return to_response(AlgorithmQueryService.get_algorithm_options())


@router.get('/form-schema/{algo_type}')
def get_algo_form_schema(algo_type: str, _: None = require_permission('algorithm:read')):
    return to_response(AlgorithmQueryService.get_form_schema(algo_type))


@router.get('/dimensions/{algo_type}')
def get_dimensions(algo_type: str, _: None = require_permission('algorithm:read')):
    return to_response(AlgorithmQueryService.get_algorithm_dimensions(algo_type))


@router.post('/dimensions/{algo_type}')
def post_dimensions(algo_type: str, _: None = require_permission('algorithm:definition_manage')):
    return to_response(AlgorithmCommandService.associate_dimensions(algo_type))


@router.post('/dimension-relations')
def post_dimension_relation(_: None = require_permission('algorithm:definition_manage')):
    return to_response(AlgorithmCommandService.create_dimension_relation())


@router.put('/dimension-relations/{relation_id}')
def put_dimension_relation(relation_id: int, _: None = require_permission('algorithm:definition_manage')):
    return to_response(AlgorithmCommandService.update_dimension_relation(relation_id))


@router.delete('/dimension-relations/{relation_id}')
def delete_dimension_relation_by_id(relation_id: int, _: None = require_permission('algorithm:definition_manage')):
    return to_response(AlgorithmCommandService.delete_dimension_relation(relation_id))


@router.post('/reload')
def reload(_: None = require_permission('algorithm:definition_manage')):
    return to_response(AlgorithmCommandService.reload_config())


@router.post('/import')
def import_algo(_: None = require_permission('algorithm:definition_manage')):
    return to_response(AlgorithmCommandService.import_algorithms())


@router.post('/bulk-delete')
def bulk_delete_algos(_: None = require_permission('algorithm:definition_manage')):
    return to_response(AlgorithmCommandService.bulk_delete())


@router.post('/extract-params')
def extract(_: None = require_permission('algorithm:param_manage')):
    return to_response(AlgorithmCommandService.extract_params())


@router.get('/dimension-params/{dimension_id}')
def get_dim_params(dimension_id: int, _: None = require_permission('algorithm:read')):
    return to_response(AlgorithmQueryService.get_dimension_params(dimension_id))
