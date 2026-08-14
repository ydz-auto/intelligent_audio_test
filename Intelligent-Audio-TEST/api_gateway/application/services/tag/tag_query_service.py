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
)


class TagCategoryQueryService:
    """标签分类查询读侧 Service。"""

    @staticmethod
    def get_all():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        keyword = request.args.get('keyword', type=str)

        result = _tag_acl.list_categories(
            page=page,
            per_page=per_page,
            keyword=keyword,
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
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        category_id = request.args.get('category_id', type=int)
        keyword = request.args.get('keyword', type=str)

        result = _tag_acl.list_tags(
            page=page,
            per_page=per_page,
            category_id=category_id,
            keyword=keyword,
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
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 100, type=int)
        keyword = request.args.get('keyword', type=str)

        result = _tag_acl.list_tag_names(
            page=page,
            per_page=per_page,
            keyword=keyword,
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
