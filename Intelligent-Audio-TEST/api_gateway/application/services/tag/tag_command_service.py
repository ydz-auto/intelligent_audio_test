"""标签写操作 Service（CQRS Command Side）。

按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 task_service。
保留 Pydantic schema 校验。
"""
import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.infrastructure.grpc_proxies import tag_config_service

from api_gateway.schemas.testcase import (
    TagCategoryItem,
    TagCategoryCreateSchema,
    TagCategoryUpdateSchema,
    TagItem,
    TagCreateSchema,
    TagUpdateSchema,
)

logger = logging.getLogger(__name__)


class TagCategoryCommandService:
    """标签分类写操作 Service。"""

    @staticmethod
    def create():
        try:
            data = TagCategoryCreateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}")

        data_dict = data.model_dump(by_alias=False, exclude_none=True)

        result = tag_config_service.create_category(data_dict)

        if not result.get('success'):
            code = result.get('code', 500)
            return error_response(result.get('message', '创建失败'), code=code)

        item = result.get('data') or {}
        return success_response(
            TagCategoryItem(**item),
            result.get('message', '标签分类创建成功'),
            http_code=201,
        )

    @staticmethod
    def update(category_id):
        try:
            data = TagCategoryUpdateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}")

        data_dict = data.model_dump(by_alias=False, exclude_none=True)

        result = tag_config_service.update_category(category_id, data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到标签分类", 404)
            return error_response(result.get('message', '更新失败'), code=code)

        item = result.get('data') or {}
        return success_response(
            TagCategoryItem(**item),
            result.get('message', '标签分类更新成功'),
        )

    @staticmethod
    def delete(category_id):
        result = tag_config_service.delete_category(category_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到标签分类", 404)
            return error_response(result.get('message', '删除失败'), code=code)

        return success_response(None, result.get('message', '标签分类删除成功'))


class TagCommandService:
    """标签写操作 Service。"""

    @staticmethod
    def create():
        try:
            data = TagCreateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}")

        data_dict = data.model_dump(by_alias=False, exclude_none=True)

        result = tag_config_service.create_tag(data_dict)

        if not result.get('success'):
            code = result.get('code', 500)
            return error_response(result.get('message', '创建失败'), code=code)

        item = result.get('data') or {}
        return success_response(
            TagItem(**item),
            result.get('message', '标签创建成功'),
            http_code=201,
        )

    @staticmethod
    def update(tag_id):
        try:
            data = TagUpdateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}")

        data_dict = data.model_dump(by_alias=False, exclude_none=True)

        result = tag_config_service.update_tag(tag_id, data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到标签", 404)
            return error_response(result.get('message', '更新失败'), code=code)

        item = result.get('data') or {}
        return success_response(
            TagItem(**item),
            result.get('message', '标签更新成功'),
        )

    @staticmethod
    def delete(tag_id):
        result = tag_config_service.delete_tag(tag_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到标签", 404)
            return error_response(result.get('message', '删除失败'), code=code)

        return success_response(None, result.get('message', '标签删除成功'))

    @staticmethod
    def batch_update_category():
        body = request.get_json() or {}
        tag_ids = body.get('tag_ids', [])
        category_id = body.get('category_id')

        result = tag_config_service.batch_update_category({
            'tag_ids': tag_ids,
            'category_id': category_id,
        })

        if not result.get('success'):
            code = result.get('code', 400)
            return error_response(result.get('message', '批量更新失败'), code=code)

        return success_response(None, result.get('message', '批量更新成功'))
