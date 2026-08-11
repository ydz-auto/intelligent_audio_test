# -*- coding: utf-8 -*-
"""API 配置命令 Service（写侧 / CRUD）。

按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 api_test_service。
保留对路由层的签名不变（静态方法 + success_response/error_response 包装）。
"""
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.schemas.api import ApiCreateInput, ApiUpdateInput
from api_gateway.schemas.common import IdData
from api_gateway.infrastructure.grpc_proxies import api_config_service


class ApiCommandService:
    """API 配置写操作 Service —— 通过 gRPC 代理调用微服务"""

    # ========== 写操作 ==========

    @staticmethod
    def create():
        try:
            data = ApiCreateInput.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        # 将 Pydantic 模型转为 dict，传给微服务
        data_dict = data.model_dump(by_alias=False, exclude_none=True)

        result = api_config_service.create(data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 202:
                return error_response(result.get('message', '操作失败'), code=202)
            return error_response(result.get('message', '操作失败'), code=code)

        new_id = (result.get('data') or {}).get('id')
        return success_response(IdData(id=new_id), result.get('message', 'API配置创建成功'), http_code=201)

    @staticmethod
    def update(api_id):
        try:
            data = ApiUpdateInput.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {str(e)}")

        data_dict = data.model_dump(by_alias=False, exclude_none=True)

        result = api_config_service.update(api_id, data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到API配置'), 404)
            return error_response(result.get('message', '操作失败'), code=code)

        return success_response(None, result.get('message', 'API配置更新成功'))

    @staticmethod
    def delete(api_id):
        result = api_config_service.delete(api_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到API配置'), 404)
            if code == 202:
                return error_response(result.get('message', '操作失败'), code=202)
            return error_response(result.get('message', '操作失败'), code=code)

        return success_response(None, result.get('message', 'API配置已删除'))
