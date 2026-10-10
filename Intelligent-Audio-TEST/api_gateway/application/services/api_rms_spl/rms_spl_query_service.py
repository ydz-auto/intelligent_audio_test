# -*- coding: utf-8 -*-
"""数字域 RMS→SPL 映射查询 Service（读侧 / UC-0902）。

网关不直接操作 DB，经 ACL 走 gRPC 调用 api_test_service.ApiRmsSplConfigService。
保留对路由层的签名约定（静态方法 + success_response/error_response 包装）。
"""
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.infrastructure.acl import ApiRmsSplConfigAclRepositoryImpl


_rms_spl_acl = ApiRmsSplConfigAclRepositoryImpl()


class RmsSplQueryService:
    """数字域 RMS→SPL 映射读操作 Service —— 通过 gRPC 代理调用微服务"""

    @staticmethod
    def get_all():
        params = request.query_params
        result = _rms_spl_acl.get_all(
            page=int(params.get('page', 1) or 1),
            per_page=int(params.get('per_page', 10) or 10),
            api_id=params.get('api_id') or None,
            calibration_status=params.get('calibration_status') or None,
        )
        if not result.success:
            return error_response(result.message or '查询失败', code=ErrorCode.INVALID_PARAMS)
        return success_response(result.data, result.message or 'Success')

    @staticmethod
    def get_one(mapping_id: int):
        result = _rms_spl_acl.get_one(mapping_id)
        if not result.success:
            code = result.code or 400
            if code == 404:
                return error_response(result.message or '未找到映射记录', code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.message or '查询失败', code=ErrorCode.INVALID_PARAMS)
        return success_response(result.data, result.message or 'Success')

    @staticmethod
    def get_by_api(api_id: int):
        result = _rms_spl_acl.get_by_api(api_id)
        if not result.success:
            return error_response(result.message or '查询失败', code=ErrorCode.INVALID_PARAMS)
        return success_response(result.data, result.message or 'Success')
