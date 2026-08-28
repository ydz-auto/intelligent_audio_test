# -*- coding: utf-8 -*-
"""API 配置查询 Service（读侧）。

按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 api_test_service。
保留对路由层的签名不变（静态方法 + success_response/error_response 包装）。
"""
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.infrastructure.acl import ApiConfigAclRepositoryImpl
from api_gateway.schemas.api import ApiListQuery


def _parse_query_params(model_cls):
    params = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
    return model_cls.model_validate(params)


_api_acl = ApiConfigAclRepositoryImpl()


class ApiQueryService:
    """API 配置读操作 Service —— 通过 gRPC 代理调用微服务"""

    # ========== 查询 ==========

    @staticmethod
    def get_all():
        query = _parse_query_params(ApiListQuery)

        result = _api_acl.get_all(
            page=query.page,
            per_page=query.per_page,
            keyword=query.keyword,
            status=query.status,
            algorithm_type=query.algorithm_type,
        )

        if not result.get('success'):
            return error_response(result.get('message', '查询失败'))

        return success_response(result.get('data'))

    # 获取单个API配置详情
    @staticmethod
    def get_one(api_id):
        result = _api_acl.get_one(api_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到API配置'), 404)
            return error_response(result.get('message', '查询失败'))

        return success_response(result.get('data'))

    # 测试API连接 (兼容 health_check)
    @staticmethod
    def test_connection(api_id):
        result = _api_acl.test_connection(api_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到API配置'), 404)
            return error_response(result.get('message', '测试失败'))

        data = result.get('data') or {}
        return success_response(
            data,
            result.get('message', '连接测试完成'),
            200,
        )

    # 保持向下兼容
    @staticmethod
    def health_check(api_id):
        return ApiQueryService.test_connection(api_id)

    # 停止测试 API
    @staticmethod
    def stop_test(api_id):
        result = _api_acl.stop_test(api_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到API配置'), 404)
            return error_response(result.get('message', '操作失败'))

        return success_response(result.get('data'), result.get('message', '测试已停止'))
