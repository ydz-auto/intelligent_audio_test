"""标签查询读侧 Service。

从 TagController / TagCategoryController 抽取的只读查询方法。
"""
from api_gateway.infrastructure.request_adapter import request
from sqlalchemy import func
from shared.models.models import Tag, TagCategory
from shared.models.database import db
from shared.utils.response import success_response, error_response

from api_gateway.schemas.testcase import (
    TagCategoryItem,
    TagCategoryListData,
    TagItem,
    TagDetailListData,
    TagListData,
)


def escape_like_pattern(pattern: str) -> str:
    return pattern.replace('%', '\\%').replace('_', '\\_')


class TagCategoryQueryService:
    @staticmethod
    def get_all():
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        keyword = request.args.get('keyword', type=str)

        subquery = db.session.query(
            Tag.category_id,
            func.count(Tag.id).label('tag_count')
        ).filter(Tag.deleted == False).group_by(Tag.category_id).subquery()

        query = db.session.query(
            TagCategory,
            func.coalesce(subquery.c.tag_count, 0).label('tag_count')
        ).outerjoin(
            subquery, TagCategory.id == subquery.c.category_id
        ).filter(TagCategory.deleted == False)

        if keyword:
            keyword = keyword.strip()
            if keyword:
                escaped_keyword = escape_like_pattern(keyword)
                query = query.filter(TagCategory.name.like(f'%{escaped_keyword}%', escape='\\'))

        query = query.order_by(TagCategory.sort_order, TagCategory.id)

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        items = [
            TagCategoryItem(
                id=cat.id,
                name=cat.name,
                description=cat.description,
                color=cat.color,
                sort_order=cat.sort_order or 0,
                tag_count=tag_count,
                created_at=cat.created_at.isoformat() if cat.created_at else None,
                updated_at=cat.updated_at.isoformat() if cat.updated_at else None,
            )
            for cat, tag_count in pagination.items
        ]

        return success_response(
            TagCategoryListData(items=items, total=pagination.total)
        )

    @staticmethod
    def get_one(category_id):
        cat = db.session.get(TagCategory, category_id)
        if not cat or cat.deleted:
            return error_response("未找到标签分类", 404)

        tag_count = Tag.query.filter_by(category_id=cat.id, deleted=False).count()

        return success_response(
            TagCategoryItem(
                id=cat.id,
                name=cat.name,
                description=cat.description,
                color=cat.color,
                sort_order=cat.sort_order or 0,
                tag_count=tag_count,
                created_at=cat.created_at.isoformat() if cat.created_at else None,
                updated_at=cat.updated_at.isoformat() if cat.updated_at else None,
            )
        )


class TagQueryService:
    @staticmethod
    def get_all():
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        category_id = request.args.get('category_id', type=int)
        keyword = request.args.get('keyword', type=str)

        query = Tag.query.filter(Tag.deleted == False)

        if category_id:
            query = query.filter_by(category_id=category_id)

        if keyword:
            keyword = keyword.strip()
            if keyword:
                escaped_keyword = escape_like_pattern(keyword)
                query = query.filter(Tag.name.like(f'%{escaped_keyword}%', escape='\\'))

        query = query.order_by(Tag.updated_at.desc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        tags = pagination.items

        category_ids = {t.category_id for t in tags if t.category_id}
        category_map = {}
        if category_ids:
            categories = TagCategory.query.filter(TagCategory.id.in_(category_ids), TagCategory.deleted == False).all()
            category_map = {c.id: c.name for c in categories}

        items = [
            TagItem(
                id=tag.id,
                name=tag.name,
                description=tag.description,
                color=tag.color,
                category_id=tag.category_id,
                category_name=category_map.get(tag.category_id),
                created_at=tag.created_at.isoformat() if tag.created_at else None,
                updated_at=tag.updated_at.isoformat() if tag.updated_at else None,
            )
            for tag in tags
        ]

        return success_response(
            TagDetailListData(items=items, total=pagination.total)
        )

    @staticmethod
    def get_all_names():
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 100, type=int), 500)
        keyword = request.args.get('keyword', type=str)

        query = Tag.query.filter(Tag.deleted == False)

        if keyword:
            keyword = keyword.strip()
            if keyword:
                escaped_keyword = escape_like_pattern(keyword)
                query = query.filter(Tag.name.like(f'%{escaped_keyword}%', escape='\\'))

        query = query.order_by(Tag.name)

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        tag_names = [tag.name for tag in pagination.items]

        return success_response(TagListData(items=tag_names, total=pagination.total))

    @staticmethod
    def get_one(tag_id):
        tag = db.session.get(Tag, tag_id)
        if not tag or tag.deleted:
            return error_response("未找到标签", 404)

        category_name = None
        if tag.category_id:
            cat = db.session.get(TagCategory, tag.category_id)
            if cat and not cat.deleted:
                category_name = cat.name

        return success_response(
            TagItem(
                id=tag.id,
                name=tag.name,
                description=tag.description,
                color=tag.color,
                category_id=tag.category_id,
                category_name=category_name,
                created_at=tag.created_at.isoformat() if tag.created_at else None,
                updated_at=tag.updated_at.isoformat() if tag.updated_at else None,
            )
        )

    @staticmethod
    def get_tags_by_category():
        categories = TagCategory.query.filter(TagCategory.deleted == False).order_by(TagCategory.sort_order, TagCategory.id).all()

        all_tags = Tag.query.filter(Tag.deleted == False).order_by(Tag.name).all()
        tags_by_category = {}
        uncategorized_tags = []

        for tag in all_tags:
            if tag.category_id:
                if tag.category_id not in tags_by_category:
                    tags_by_category[tag.category_id] = []
                tags_by_category[tag.category_id].append(tag)
            else:
                uncategorized_tags.append(tag)

        result = []
        for cat in categories:
            cat_tags = tags_by_category.get(cat.id, [])
            tag_items = [
                TagItem(
                    id=tag.id,
                    name=tag.name,
                    description=tag.description,
                    color=tag.color,
                    category_id=tag.category_id,
                    category_name=cat.name,
                    created_at=tag.created_at.isoformat() if tag.created_at else None,
                    updated_at=tag.updated_at.isoformat() if tag.updated_at else None,
                )
                for tag in cat_tags
            ]
            result.append({
                'category': TagCategoryItem(
                    id=cat.id,
                    name=cat.name,
                    description=cat.description,
                    color=cat.color,
                    sort_order=cat.sort_order or 0,
                    tag_count=len(cat_tags),
                    created_at=cat.created_at.isoformat() if cat.created_at else None,
                    updated_at=cat.updated_at.isoformat() if cat.updated_at else None,
                ),
                'tags': tag_items
            })

        if uncategorized_tags:
            tag_items = [
                TagItem(
                    id=tag.id,
                    name=tag.name,
                    description=tag.description,
                    color=tag.color,
                    category_id=None,
                    category_name=None,
                    created_at=tag.created_at.isoformat() if tag.created_at else None,
                    updated_at=tag.updated_at.isoformat() if tag.updated_at else None,
                )
                for tag in uncategorized_tags
            ]
            result.append({
                'category': None,
                'tags': tag_items
            })

        return success_response({'items': result, 'total': len(result)})
