"""标签查询读侧 Service（CQRS Query Side）。

按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 task_service。
"""
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.infrastructure.acl import TagConfigAclRepositoryImpl

_tag_acl = TagConfigAclRepositoryImpl()

from api_gateway.schemas.testcase import (
    TagCategoryItem,
    TagCategoryListData,
    TagItem,
    TagDetailListData,
    TagListData,
    TagCategoryListQuery,
    TagListQuery,
    TagNameListQuery,
)


def _parse_query_params(model_cls):
    """从 request.args 提取查询参数并通过 APIModel 校验"""
    params = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
    return model_cls.model_validate(params)


class TagCategoryQueryService:
    """标签分类查询读侧 Service。"""

    @staticmethod
    def get_all():
        query = _parse_query_params(TagCategoryListQuery)

        result = _tag_acl.list_categories(
            page=query.page,
            per_page=query.per_page,
            keyword=query.keyword,
        )

        if not result.get('success'):
            return error_response(result.get('message', '查询失败'))

        raw = result.get('data') or {}
        items = [TagCategoryItem(**item) for item in raw.get('items', [])]

        return success_response(
            TagCategoryListData(items=items, total=raw.get('total', 0))
        )

    @staticmethod
    def get_one(category_id):
        result = _tag_acl.get_category(category_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到标签分类", 404)
            return error_response(result.get('message', '查询失败'))

        item = result.get('data') or {}
        return success_response(TagCategoryItem(**item))


class TagQueryService:
    """标签查询读侧 Service。"""

    @staticmethod
    def get_all():
        query = _parse_query_params(TagListQuery)

        result = _tag_acl.list_tags(
            page=query.page,
            per_page=query.per_page,
            category_id=query.category_id,
            keyword=query.keyword,
        )

        if not result.get('success'):
            return error_response(result.get('message', '查询失败'))

        raw = result.get('data') or {}
        items = [TagItem(**item) for item in raw.get('items', [])]

        return success_response(
            TagDetailListData(items=items, total=raw.get('total', 0))
        )

    @staticmethod
    def get_all_names():
        query = _parse_query_params(TagNameListQuery)

        result = _tag_acl.list_tag_names(
            page=query.page,
            per_page=query.per_page,
            keyword=query.keyword,
        )

        if not result.get('success'):
            return error_response(result.get('message', '查询失败'))

        raw = result.get('data') or {}
        tag_names = raw.get('items', [])

        return success_response(TagListData(items=tag_names, total=raw.get('total', 0)))

    @staticmethod
    def get_one(tag_id):
        result = _tag_acl.get_tag(tag_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到标签", 404)
            return error_response(result.get('message', '查询失败'))

        item = result.get('data') or {}
        return success_response(TagItem(**item))

    @staticmethod
    def get_tags_by_category():
        result = _tag_acl.get_tags_by_category()

        if not result.get('success'):
            return error_response(result.get('message', '查询失败'))

        return success_response(result.get('data'))
