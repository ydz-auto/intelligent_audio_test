# -*- coding: utf-8 -*-
"""SPL 映射查询 Service（读侧）。

按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 device_service。
保留对路由层的签名不变（静态方法 + success_response/error_response 包装）。
保留 Pydantic schema 校验。
"""
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.infrastructure.grpc_proxies import spl_config_service
from api_gateway.schemas.spl import (
    SPLMappingQueryRequest,
)


class SPLQueryService:
    """SPL 映射查询读操作 Service —— 通过 gRPC 代理调用微服务"""

    # ========== 查询读侧 ==========

    # 获取所有 SPL 映射配置
    @staticmethod
    def get_all():
        query_params_dict = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
        req_data = SPLMappingQueryRequest.model_validate(query_params_dict)

        keyword = req_data.keyword or req_data.search
        calibration_status = req_data.calibration_status
        page = req_data.page or 1
        per_page = req_data.per_page or 10
        device_id = req_data.device_id

        result = spl_config_service.get_all(
            page=page,
            per_page=per_page,
            keyword=keyword,
            calibration_status=calibration_status,
            device_id=device_id,
        )

        if not result.get('success'):
            return error_response(result.get('message', '查询失败'), code=ErrorCode.DATABASE_ERROR)

        return success_response(result.get('data'))

    # 获取单个映射详情
    @staticmethod
    def get_one(mapping_id):
        result = spl_config_service.get_one(mapping_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到 SPL 映射记录'), code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '查询失败'))

        return success_response(result.get('data'))

    # 获取校准历史
    @staticmethod
    def get_history(mapping_id):
        result = spl_config_service.get_history(mapping_id)

        if not result.get('success'):
            return error_response(result.get('message', '查询失败'), code=ErrorCode.DATABASE_ERROR)

        return success_response(result.get('data'))

    # 获取详细校准数据 (最新)
    @staticmethod
    def get_calibration_data(mapping_id):
        result = spl_config_service.get_calibration_data(mapping_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到映射记录'), code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '查询失败'))

        return success_response(result.get('data'))

    # 获取 SPL 统计信息
    @staticmethod
    def get_stats():
        result = spl_config_service.get_stats()

        if not result.get('success'):
            return error_response(result.get('message', '查询失败'), code=ErrorCode.DATABASE_ERROR)

        return success_response(result.get('data'))

    # 按设备ID获取SPL映射列表
    @staticmethod
    def get_by_device(device_id):
        result = spl_config_service.get_by_device(device_id)

        if not result.get('success'):
            return error_response(result.get('message', '查询失败'), code=ErrorCode.DATABASE_ERROR)

        return success_response(result.get('data'))
