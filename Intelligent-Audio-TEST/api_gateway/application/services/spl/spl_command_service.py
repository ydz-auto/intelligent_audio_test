# -*- coding: utf-8 -*-
"""SPL 映射命令 Service（写侧 / CRUD + 校准 + 测试音）。

按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 device_service。
保留对路由层的签名不变（静态方法 + success_response/error_response 包装）。
保留 Pydantic schema 校验。校准点校验逻辑已下沉到微服务。
"""
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.infrastructure.acl import SplConfigAclRepositoryImpl
from api_gateway.schemas.common import IdData
from api_gateway.schemas.spl import (
    SPLMappingCreateRequest,
    SPLMappingUpdateRequest,
    PlayTestToneRequest,
    StopTestToneRequest,
)


_spl_acl = SplConfigAclRepositoryImpl()


class SPLCommandService:
    """SPL 映射写操作 Service —— 通过 gRPC 代理调用微服务"""

    # ========== 写操作 ==========

    # 创建新的 SPL 映射记录
    @staticmethod
    def create():
        try:
            req_data = SPLMappingCreateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", code=ErrorCode.INVALID_PARAMS)

        device_id = req_data.device_id
        device_type = req_data.device_type

        if device_id is None and device_type is None:
            return error_response("必须提供 device_id 或 device_type 之一", code=ErrorCode.INVALID_PARAMS)

        data_dict = req_data.model_dump(by_alias=False, exclude_none=True)

        result = _spl_acl.create(data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到'), code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '操作失败'), code=ErrorCode.INVALID_PARAMS)

        new_id = (result.get('data') or {}).get('id')
        return success_response(IdData(id=new_id), result.get('message', 'SPL 映射记录创建成功'), http_code=201)

    # 更新 SPL 映射信息
    @staticmethod
    def update(mapping_id):
        try:
            req_data = SPLMappingUpdateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", code=ErrorCode.INVALID_PARAMS)

        data_dict = req_data.model_dump(by_alias=False, exclude_none=True)

        result = _spl_acl.update(mapping_id, data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到 SPL 映射记录'), code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '操作失败'), code=ErrorCode.INVALID_PARAMS)

        return success_response(None, result.get('message', 'SPL 映射记录更新成功'))

    # 删除 SPL 映射记录
    @staticmethod
    def delete(mapping_id):
        result = _spl_acl.delete(mapping_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到 SPL 映射记录'), code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '操作失败'), code=ErrorCode.DATABASE_ERROR)

        return success_response(None, result.get('message', 'SPL 映射记录已删除'))

    # 执行 SPL 校准流程
    @staticmethod
    def calibrate(mapping_id):
        result = _spl_acl.calibrate(mapping_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到映射记录'), code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '校准失败'), code=ErrorCode.CALIBRATION_FAILED)

        return success_response(result.get('data'), result.get('message', '校准成功'))

    # 播放测试音（改为播放指定的音频文件）
    @staticmethod
    def play_test_tone(mapping_id=None):
        try:
            req_data = PlayTestToneRequest.model_validate(request.get_json() or {})
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", code=ErrorCode.INVALID_PARAMS)

        data_dict = req_data.model_dump(by_alias=False, exclude_none=True)

        result = _spl_acl.play_test_tone(data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到'), code=ErrorCode.NOT_FOUND, http_code=404)
            if code == 403:
                return error_response(result.get('message', '操作失败'), code=ErrorCode.FORBIDDEN, http_code=403)
            return error_response(result.get('message', '播放失败'), code=ErrorCode.DATABASE_ERROR)

        return success_response(result.get('data'), result.get('message', '测试音频已播放'))

    @staticmethod
    def stop_test_tone():
        try:
            req_data = StopTestToneRequest.model_validate(request.get_json() or {})
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", code=ErrorCode.INVALID_PARAMS)

        data_dict = req_data.model_dump(by_alias=False, exclude_none=True)

        result = _spl_acl.stop_test_tone(data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '设备未找到'), code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '操作失败'), code=ErrorCode.DATABASE_ERROR)

        return success_response(result.get('data'), result.get('message', '测试音已停止'))
