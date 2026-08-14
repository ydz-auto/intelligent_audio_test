"""算法分组服务

按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 algorithm_service。
"""
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.infrastructure.acl import AlgorithmConfigAclRepositoryImpl

from api_gateway.schemas.algorithm import (
    AlgorithmGroupCreate,
    AlgorithmGroupUpdate,
    AlgorithmGroupItem,
)


_algorithm_acl = AlgorithmConfigAclRepositoryImpl()


class AlgorithmGroupService:
    """算法分组 CRUD 服务"""

    @staticmethod
    def get_all():
        result = _algorithm_acl.list_groups()

        if result.get('success'):
            return success_response(result.get('data'))
        return error_response(result.get('message', '查询失败'), result.get('code', 500))

    @staticmethod
    def get_by_id(group_id):
        result = _algorithm_acl.get_group(group_id)

        if result.get('success'):
            return success_response(result.get('data'))
        return error_response(result.get('message', '查询失败'), result.get('code', 500))

    @staticmethod
    def create():
        try:
            req = AlgorithmGroupCreate.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = _algorithm_acl.create_group(data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '分组创建成功'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def update(group_id):
        try:
            req = AlgorithmGroupUpdate.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data = req.model_dump(by_alias=False, exclude_none=True)
        result = _algorithm_acl.update_group(group_id, data)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '分组更新成功'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))

    @staticmethod
    def delete(group_id):
        result = _algorithm_acl.delete_group(group_id)

        if result.get('success'):
            return success_response(result.get('data'), result.get('message', '分组删除成功'))
        return error_response(result.get('message', '操作失败'), result.get('code', 400))
