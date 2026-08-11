import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.infrastructure.grpc_proxies import device_config_service
from api_gateway.schemas.common import IdData
from api_gateway.schemas.device import (
    DeviceCreateSchema,
    DeviceUpdateSchema,
)

logger = logging.getLogger(__name__)


class DeviceCommandService:
    """设备写操作 Service（CQRS Command Side）。

    按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 device_service。
    保留对路由层的签名不变（静态方法 + success_response/error_response 包装）。
    保留 Pydantic schema 校验。
    """

    # 注册新设备
    @staticmethod
    def create():
        try:
            req = DeviceCreateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data_dict = req.model_dump(by_alias=False, exclude_none=True)

        result = device_config_service.create(data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '操作失败'), 404)
            return error_response(result.get('message', '操作失败'), code=code)

        new_id = (result.get('data') or {}).get('id')
        return success_response(IdData(id=new_id), result.get('message', '设备注册成功'), http_code=201)

    # 更新设备信息
    @staticmethod
    def update(device_id):
        try:
            req = DeviceUpdateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        validated_dict = req.model_dump(by_alias=True, exclude_none=True)

        result = device_config_service.update(device_id, validated_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到设备'), 404)
            return error_response(result.get('message', '操作失败'), code=code)

        return success_response(None, result.get('message', '设备信息更新成功'))

    # 删除设备
    @staticmethod
    def delete(device_id):
        result = device_config_service.delete(device_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到设备'), 404)
            return error_response(result.get('message', '操作失败'), code=code)

        return success_response(None, result.get('message', '设备已删除 (逻辑删除)'))
