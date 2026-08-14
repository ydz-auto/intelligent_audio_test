# -*- coding: utf-8 -*-
"""算法配置查询 Service（读侧）。

按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 algorithm_service。
"""
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response, wrap_grpc_response
from api_gateway.infrastructure.acl import AlgorithmConfigAclRepositoryImpl

from api_gateway.schemas.algorithm import (
    AlgorithmListQuery,
    AlgorithmParamListQuery,
)


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

    # ========== 参数查询 ==========

    @staticmethod
    def list_params():
        """获取参数列表（支持设备参数和API参数）"""
        query_params_dict = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
        query_params = AlgorithmParamListQuery.model_validate(query_params_dict)

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
        """获取参数映射列表"""
        algorithm_type = request.args.get('algorithm_type')
        source_type = request.args.get('source_type')
        dimension_id = request.args.get('dimension_id', type=int)

        result = _algorithm_acl.list_mappings(
            algorithm_type=algorithm_type,
            source_type=source_type,
            dimension_id=dimension_id,
        )

        if result.get('success'):
            return success_response(result.get('data'))
        return wrap_grpc_response(result, default_error_msg='查询失败')

    # ========== 用例专属参数查询 ==========

    @staticmethod
    def list_case_params():
        """获取用例专属参数列表"""
        algorithm_type = request.args.get('algorithm_type')
        scope = request.args.get('scope')

        result = _algorithm_acl.list_case_params(
            algorithm_type=algorithm_type,
            scope=scope,
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
        algorithm_type = request.args.get('algorithm_type')

        if not algorithm_type:
            return error_response('algorithm_type is required')

        result = _algorithm_acl.list_reference_params(algorithm_type=algorithm_type)

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
