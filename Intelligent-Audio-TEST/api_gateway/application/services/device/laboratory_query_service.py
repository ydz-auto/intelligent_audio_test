import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response, wrap_grpc_response
from api_gateway.infrastructure.acl import LaboratoryAclRepositoryImpl
from api_gateway.schemas.laboratory import LaboratoryListQuery

logger = logging.getLogger(__name__)

_laboratory_acl = LaboratoryAclRepositoryImpl()

_NOT_FOUND_MAPPING = {404: ('未找到实验室', 404)}


class LaboratoryQueryService:
    """实验室查询读侧 Service（INT-655，CQRS Query Side）。

    网关不直接操作 DB，通过 gRPC 调用 device_service.LaboratoryConfigService。
    列表/详情响应天然携带 device_count/playback_device_count/test_case_count。
    """

    @staticmethod
    def get_all():
        params = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
        try:
            query = LaboratoryListQuery.model_validate(params)
        except Exception as e:
            return error_response(f"请求参数错误: {str(e)}", 400)

        result = _laboratory_acl.get_all(
            page=query.page,
            per_page=query.per_page,
            keyword=query.keyword,
            status=query.status,
        )

        if not result.get('success'):
            return wrap_grpc_response(result, default_error_msg='查询失败')

        return success_response(result.get('data'))

    @staticmethod
    def get_one(lab_id: int):
        result = _laboratory_acl.get_one(lab_id)
        if not result.get('success'):
            return wrap_grpc_response(
                result, default_error_msg='查询失败', error_code_mapping=_NOT_FOUND_MAPPING)
        return success_response(result.get('data'))

    @staticmethod
    def get_summary(lab_id: int):
        """实验室资源统计（GET /{id}/summary）"""
        result = _laboratory_acl.get_summary(lab_id)
        if not result.get('success'):
            return wrap_grpc_response(
                result, default_error_msg='查询失败', error_code_mapping=_NOT_FOUND_MAPPING)
        return success_response(result.get('data'))
