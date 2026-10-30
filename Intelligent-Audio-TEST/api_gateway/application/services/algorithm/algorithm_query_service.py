# -*- coding: utf-8 -*-
"""算法配置查询 Service（读侧）。

按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 algorithm_service。
"""
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response, wrap_grpc_response
from api_gateway.infrastructure.acl import AlgorithmConfigAclRepositoryImpl
from api_gateway.infrastructure.grpc_proxies.algorithm_proxies import (
    algorithm_query_service as _algorithm_service_proxy,
)

from api_gateway.schemas.algorithm import (
    AlgorithmListQuery,
    AlgorithmParamListQuery,
    AlgorithmMappingListQuery,
    AlgorithmCaseParamListQuery,
    AlgorithmReferenceParamListQuery,
)


def _parse_query_params(model_cls):
    params = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
    return model_cls.model_validate(params)


_algorithm_acl = AlgorithmConfigAclRepositoryImpl()


class AlgorithmQueryService:
    # ========== 算法定义查询 ==========

    @staticmethod
    def list_algorithms():
        """获取算法定义列表"""
        query_params_dict = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
        query_params = AlgorithmListQuery.model_validate(query_params_dict)

        result = _algorithm_acl.list_algorithms(
            status=query_params.status,
            group_id=query_params.group_id,
        )

        if result.get('success'):
            return success_response(result.get('data'))
        return wrap_grpc_response(result, default_error_msg='查询失败')

    @staticmethod
    def get_algorithm_options():
        """获取算法选项（下拉框用）"""
        result = _algorithm_acl.get_algorithm_options()

        if result.get('success'):
            return success_response(result.get('data'))
        return wrap_grpc_response(result, default_error_msg='查询失败')

    @staticmethod
    def get_algorithm(algo_type: str):
        """获取算法详情"""
        result = _algorithm_acl.get_algorithm(algo_type)

        if result.get('success'):
            return success_response(result.get('data'))
        return wrap_grpc_response(result, default_error_msg='查询失败')

    @staticmethod
    def get_definition_draft(algo_type: str):
        """获取算法定义草稿快照（前端编辑恢复）"""
        result = _algorithm_service_proxy.get_algorithm_definition_draft(algo_type)

        if result.get('success'):
            return success_response(result.get('data'))
        return wrap_grpc_response(result, default_error_msg='查询失败')

    # ========== 参数查询 ==========

    @staticmethod
    def list_params():
        """获取参数列表（设备参数 / API 参数）。

        API 参数已下沉到 API 实例作用域：param_type=api 必须带 api_id，只返回该
        API 的字段声明行（算法类型级默认层废弃）。
        """
        query_params_dict = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
        query_params = AlgorithmParamListQuery.model_validate(query_params_dict)

        if query_params.param_type == 'api':
            if query_params.api_id is None:
                return error_response('param_type=api 时必须带 api_id（API 参数按 API 实例作用域读取）', 400)
            result = _algorithm_acl.get_api_params(
                algorithm_type=query_params.algorithm_type,
                api_id=query_params.api_id,
            )
        else:
            result = _algorithm_acl.list_params(
                algorithm_type=query_params.algorithm_type,
                param_type=query_params.param_type,
            )

        if result.get('success'):
            return success_response(result.get('data'))
        return wrap_grpc_response(result, default_error_msg='查询失败')

    @staticmethod
    def get_param(param_id: int):
        """获取参数详情"""
        result = _algorithm_acl.get_param(param_id)

        if result.get('success'):
            return success_response(result.get('data'))
        return wrap_grpc_response(result, default_error_msg='查询失败')

    # ========== 映射查询 ==========

    @staticmethod
    def list_mappings():
        """获取参数映射列表。

        source_type=api 且带 api_id 时按 API 实例作用域读取（映射随 API 参数一起
        下沉，算法类型级默认层废弃）；其余情况沿用算法类型级读取。
        """
        query = _parse_query_params(AlgorithmMappingListQuery)

        if query.api_id is not None:
            result = _algorithm_acl.get_param_mapping_for_component(
                algorithm_type=query.algorithm_type,
                component_type=query.source_type or 'api',
                api_id=query.api_id,
            )
        else:
            result = _algorithm_acl.list_mappings(
                algorithm_type=query.algorithm_type,
                source_type=query.source_type,
                dimension_id=query.dimension_id,
            )

        if result.get('success'):
            return success_response(result.get('data'))
        return wrap_grpc_response(result, default_error_msg='查询失败')

    # ========== 用例专属参数查询 ==========

    @staticmethod
    def list_case_params():
        """获取用例专属参数列表"""
        query = _parse_query_params(AlgorithmCaseParamListQuery)

        result = _algorithm_acl.list_case_params(
            algorithm_type=query.algorithm_type,
            scope=query.scope,
        )

        if result.get('success'):
            return success_response(result.get('data'))
        return wrap_grpc_response(result, default_error_msg='查询失败')

    @staticmethod
    def get_case_param(param_id: int):
        """获取单个用例专属参数"""
        result = _algorithm_acl.get_case_param(param_id)

        if result.get('success'):
            return success_response(result.get('data'))
        return wrap_grpc_response(result, default_error_msg='查询失败')

    # ========== 参考参数查询 ==========

    @staticmethod
    def list_reference_params():
        """获取参考参数列表"""
        query = _parse_query_params(AlgorithmReferenceParamListQuery)

        if not query.algorithm_type:
            return error_response('algorithm_type is required')

        result = _algorithm_acl.list_reference_params(algorithm_type=query.algorithm_type)

        if result.get('success'):
            return success_response(result.get('data'))
        return wrap_grpc_response(result, default_error_msg='查询失败')

    @staticmethod
    def get_reference_param(param_id: int):
        """获取单个参考参数"""
        result = _algorithm_acl.get_reference_param(param_id)

        if result.get('success'):
            return success_response(result.get('data'))
        return wrap_grpc_response(result, default_error_msg='查询失败')

    # ========== 表单 Schema ==========

    @staticmethod
    def get_form_schema(algo_type: str):
        """获取算法表单 Schema（用于前端动态表单）"""
        result = _algorithm_acl.get_form_schema(algo_type)

        if result.get('success'):
            return success_response(result.get('data'))
        return wrap_grpc_response(result, default_error_msg='查询失败')

    # ========== 维度查询 ==========

    @staticmethod
    def get_algorithm_dimensions(algo_type: str):
        """获取算法关联的评估维度（包含完整维度详情）"""
        result = _algorithm_acl.get_algorithm_dimensions(algo_type)

        if result.get('success'):
            return success_response(result.get('data'))
        return wrap_grpc_response(result, default_error_msg='查询失败')

    @staticmethod
    def get_dimension_params(dimension_id: int):
        """获取评估维度的参数列表"""
        result = _algorithm_acl.get_dimension_params(dimension_id)

        if result.get('success'):
            return success_response(result.get('data'))
        return wrap_grpc_response(result, default_error_msg='查询失败')
