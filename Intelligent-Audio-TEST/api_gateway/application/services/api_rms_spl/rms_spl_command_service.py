# -*- coding: utf-8 -*-
"""数字域 RMS→SPL 映射命令 Service（写侧 / CRUD + 校准 + 默认项，UC-0902）。

网关不直接操作 DB，经 ACL 走 gRPC 调用 api_test_service.ApiRmsSplConfigService。
并发校准互斥（分布式锁）由微服务侧持有，网关只透传 409 冲突。
"""
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.infrastructure.acl import ApiRmsSplConfigAclRepositoryImpl
from api_gateway.schemas.api_rms_spl import (
    RmsSplMappingCreateRequest,
    RmsSplMappingUpdateRequest,
    RmsSplCalibrateRequest,
    RmsSplSetDefaultRequest,
)
from api_gateway.schemas.common import IdData


_rms_spl_acl = ApiRmsSplConfigAclRepositoryImpl()


def _error(result, fallback_message: str):
    """按微服务返回的信封 code 映射网关错误响应"""
    code = result.code or 400
    if code == 404:
        return error_response(result.message or fallback_message, code=ErrorCode.NOT_FOUND, http_code=404)
    if code == 409:
        return error_response(result.message or fallback_message, code=ErrorCode.CONFLICT, http_code=409)
    return error_response(result.message or fallback_message, code=ErrorCode.INVALID_PARAMS)


class RmsSplCommandService:
    """数字域 RMS→SPL 映射写操作 Service —— 通过 gRPC 代理调用微服务"""

    @staticmethod
    def create():
        try:
            req_data = RmsSplMappingCreateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", code=ErrorCode.INVALID_PARAMS)

        result = _rms_spl_acl.create(req_data.model_dump(by_alias=False, exclude_none=True))
        if not result.success:
            return _error(result, '创建映射记录失败')

        new_id = (result.data or {}).get('id')
        return success_response(IdData(id=new_id), result.message or 'RMS→SPL 映射记录创建成功', http_code=201)

    @staticmethod
    def update(mapping_id: int):
        try:
            req_data = RmsSplMappingUpdateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", code=ErrorCode.INVALID_PARAMS)

        result = _rms_spl_acl.update(mapping_id, req_data.model_dump(by_alias=False, exclude_none=True))
        if not result.success:
            return _error(result, '更新映射记录失败')
        return success_response(result.data, result.message or 'RMS→SPL 映射记录更新成功')

    @staticmethod
    def delete(mapping_id: int):
        result = _rms_spl_acl.delete(mapping_id)
        if not result.success:
            return _error(result, '删除映射记录失败')
        return success_response(None, result.message or 'RMS→SPL 映射记录已删除')

    @staticmethod
    def calibrate(mapping_id: int):
        try:
            req_data = RmsSplCalibrateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", code=ErrorCode.INVALID_PARAMS)

        result = _rms_spl_acl.calibrate(mapping_id, req_data.calibration_data)
        if not result.success:
            return _error(result, '校准失败')
        return success_response(result.data, result.message or '校准成功')

    @staticmethod
    def set_default(api_id: int):
        try:
            req_data = RmsSplSetDefaultRequest.model_validate(request.get_json() or {})
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", code=ErrorCode.INVALID_PARAMS)

        result = _rms_spl_acl.set_default(api_id, req_data.mapping_id)
        if not result.success:
            return _error(result, '设置默认映射失败')
        return success_response(result.data, result.message or '默认映射已更新')
