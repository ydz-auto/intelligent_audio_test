import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.infrastructure.acl import LaboratoryAclRepositoryImpl
from api_gateway.schemas.common import IdData
from api_gateway.schemas.laboratory import (
    LaboratoryCreateSchema,
    LaboratoryUpdateSchema,
)

logger = logging.getLogger(__name__)

_laboratory_acl = LaboratoryAclRepositoryImpl()


class LaboratoryCommandService:
    """实验室写操作 Service（INT-655，CQRS Command Side）。

    create/update/delete 走 gRPC → device_service.LaboratoryConfigService。
    业务码（404 未找到 / 409 code 冲突）由 gRPC 响应 code 字段透传，
    网关映射为对应 HTTP 状态。
    """

    @staticmethod
    def create():
        try:
            req = LaboratoryCreateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data_dict = req.model_dump(by_alias=False, exclude_none=True)
        result = _laboratory_acl.create(data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 409:
                return error_response(result.get('message', '实验室代码已存在'), code=409, http_code=409)
            return error_response(result.get('message', '创建失败'), code=code, http_code=code)

        new_id = (result.get('data') or {}).get('id')
        return success_response(IdData(id=new_id), result.get('message', '实验室创建成功'), http_code=201)

    @staticmethod
    def update(lab_id: int):
        try:
            req = LaboratoryUpdateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        validated_dict = req.model_dump(by_alias=False, exclude_none=True)
        result = _laboratory_acl.update(lab_id, validated_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到实验室'), code=404, http_code=404)
            if code == 409:
                return error_response(result.get('message', '实验室代码已存在'), code=409, http_code=409)
            return error_response(result.get('message', '更新失败'), code=code, http_code=code)

        return success_response(result.get('data'), result.get('message', '实验室更新成功'))

    @staticmethod
    def delete(lab_id: int):
        result = _laboratory_acl.delete(lab_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '未找到实验室'), code=404, http_code=404)
            return error_response(result.get('message', '删除失败'), code=code, http_code=code)

        return success_response(None, result.get('message', '实验室已删除'))
