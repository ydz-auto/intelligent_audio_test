from api_gateway.controllers.request_adapter import request
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from shared.models.models import Tag, TagCategory
from shared.models.database import db
from shared.utils.response import success_response, error_response
from api_gateway.schemas.testcase import (
    TagCategoryItem,
    TagCategoryListData,
    TagCategoryCreateSchema,
    TagCategoryUpdateSchema,
    TagItem,
    TagDetailListData,
    TagCreateSchema,
    TagUpdateSchema,
    TagListData,
)
from datetime import datetime, timezone, timedelta
from shared.utils.query_utils import now_cst
import logging

logger = logging.getLogger(__name__)

BATCH_OPERATION_LIMIT = 100
NAME_MAX_LENGTH = 50
DESCRIPTION_MAX_LENGTH = 500

def utc8now():
    return now_cst()

def escape_like_pattern(pattern: str) -> str:
    return pattern.replace('%', '\\%').replace('_', '\\_')

class TagCategoryController:
    @staticmethod
    def get_all():
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        keyword = request.args.get('keyword', type=str)
        
        subquery = db.session.query(
            Tag.category_id,
            func.count(Tag.id).label('tag_count')
        ).group_by(Tag.category_id).subquery()
        
        query = db.session.query(
            TagCategory,
            func.coalesce(subquery.c.tag_count, 0).label('tag_count')
        ).outerjoin(
            subquery, TagCategory.id == subquery.c.category_id
        )
        
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
        if not cat:
            return error_response("未找到标签分类", 404)
        
        tag_count = Tag.query.filter_by(category_id=cat.id).count()
        
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
    
    @staticmethod
    def create():
        try:
            data = TagCategoryCreateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}")
        
        name = data.name.strip() if data.name else ''
        if not name:
            return error_response("分类名称不能为空")
        if len(name) > NAME_MAX_LENGTH:
            return error_response(f"分类名称不能超过 {NAME_MAX_LENGTH} 个字符")
        
        try:
            cat = TagCategory(
                name=name,
                description=data.description[:DESCRIPTION_MAX_LENGTH] if data.description else None,
                color=data.color,
                sort_order=data.sort_order or 0,
            )
            db.session.add(cat)
            db.session.commit()
            
            logger.info(f"创建标签分类成功: {name} (ID: {cat.id})")
            
            return success_response(
                TagCategoryItem(
                    id=cat.id,
                    name=cat.name,
                    description=cat.description,
                    color=cat.color,
                    sort_order=cat.sort_order or 0,
                    tag_count=0,
                    created_at=cat.created_at.isoformat() if cat.created_at else None,
                    updated_at=cat.updated_at.isoformat() if cat.updated_at else None,
                ),
                "标签分类创建成功",
                0,
                201
            )
        except IntegrityError:
            db.session.rollback()
            return error_response(f"分类名称已存在: {name}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"创建标签分类失败: {str(e)}")
            return error_response("创建失败，请稍后重试")
    
    @staticmethod
    def update(category_id):
        cat = db.session.get(TagCategory, category_id)
        if not cat:
            return error_response("未找到标签分类", 404)
        
        try:
            data = TagCategoryUpdateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}")
        
        try:
            if data.name is not None:
                name = data.name.strip()
                if not name:
                    return error_response("分类名称不能为空")
                if len(name) > NAME_MAX_LENGTH:
                    return error_response(f"分类名称不能超过 {NAME_MAX_LENGTH} 个字符")
                cat.name = name
            
            if data.description is not None:
                cat.description = data.description[:DESCRIPTION_MAX_LENGTH] if data.description else None
            if data.color is not None:
                cat.color = data.color
            if data.sort_order is not None:
                cat.sort_order = data.sort_order
            
            cat.updated_at = utc8now()
            db.session.commit()
            
            tag_count = Tag.query.filter_by(category_id=cat.id).count()
            
            logger.info(f"更新标签分类成功: {cat.name} (ID: {cat.id})")
            
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
                ),
                "标签分类更新成功"
            )
        except IntegrityError:
            db.session.rollback()
            return error_response(f"分类名称已存在: {data.name}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"更新标签分类失败: {str(e)}")
            return error_response("更新失败，请稍后重试")
    
    @staticmethod
    def delete(category_id):
        cat = db.session.get(TagCategory, category_id)
        if not cat:
            return error_response("未找到标签分类", 404)
        
        tag_count = Tag.query.filter_by(category_id=category_id).count()
        if tag_count > 0:
            return error_response(f"该分类下还有 {tag_count} 个标签，请先移除或迁移标签")
        
        try:
            cat_name = cat.name
            db.session.delete(cat)
            db.session.commit()
            logger.info(f"删除标签分类成功: {cat_name} (ID: {category_id})")
            return success_response(None, "标签分类删除成功")
        except Exception as e:
            db.session.rollback()
            logger.error(f"删除标签分类失败: {str(e)}")
            return error_response("删除失败，请稍后重试")


class TagController:
    @staticmethod
    def get_all():
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        category_id = request.args.get('category_id', type=int)
        keyword = request.args.get('keyword', type=str)
        
        query = Tag.query
        
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
            categories = TagCategory.query.filter(TagCategory.id.in_(category_ids)).all()
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
        
        query = Tag.query
        
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
        if not tag:
            return error_response("未找到标签", 404)
        
        category_name = None
        if tag.category_id:
            cat = db.session.get(TagCategory, tag.category_id)
            if cat:
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
    def create():
        try:
            data = TagCreateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}")
        
        name = data.name.strip() if data.name else ''
        if not name:
            return error_response("标签名称不能为空")
        if len(name) > NAME_MAX_LENGTH:
            return error_response(f"标签名称不能超过 {NAME_MAX_LENGTH} 个字符")
        
        if data.category_id:
            cat = db.session.get(TagCategory, data.category_id)
            if not cat:
                return error_response(f"未找到标签分类: {data.category_id}")
        
        try:
            tag = Tag(
                name=name,
                description=data.description[:DESCRIPTION_MAX_LENGTH] if data.description else None,
                color=data.color,
                category_id=data.category_id,
            )
            db.session.add(tag)
            db.session.commit()
            
            category_name = None
            if tag.category_id:
                cat = db.session.get(TagCategory, tag.category_id)
                if cat:
                    category_name = cat.name
            
            logger.info(f"创建标签成功: {name} (ID: {tag.id})")
            
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
                ),
                "标签创建成功",
                0,
                201
            )
        except IntegrityError:
            db.session.rollback()
            return error_response(f"标签名称已存在: {name}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"创建标签失败: {str(e)}")
            return error_response("创建失败，请稍后重试")
    
    @staticmethod
    def update(tag_id):
        tag = db.session.get(Tag, tag_id)
        if not tag:
            return error_response("未找到标签", 404)
        
        try:
            data = TagUpdateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}")
        
        if data.category_id is not None and data.category_id:
            cat = db.session.get(TagCategory, data.category_id)
            if not cat:
                return error_response(f"未找到标签分类: {data.category_id}")
        
        try:
            if data.name is not None:
                name = data.name.strip()
                if not name:
                    return error_response("标签名称不能为空")
                if len(name) > NAME_MAX_LENGTH:
                    return error_response(f"标签名称不能超过 {NAME_MAX_LENGTH} 个字符")
                tag.name = name
            
            if data.description is not None:
                tag.description = data.description[:DESCRIPTION_MAX_LENGTH] if data.description else None
            if data.color is not None:
                tag.color = data.color
            if data.category_id is not None:
                tag.category_id = data.category_id if data.category_id else None
            
            tag.updated_at = utc8now()
            db.session.commit()
            
            category_name = None
            if tag.category_id:
                cat = db.session.get(TagCategory, tag.category_id)
                if cat:
                    category_name = cat.name
            
            logger.info(f"更新标签成功: {tag.name} (ID: {tag.id})")
            
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
                ),
                "标签更新成功"
            )
        except IntegrityError:
            db.session.rollback()
            return error_response(f"标签名称已存在: {data.name}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"更新标签失败: {str(e)}")
            return error_response("更新失败，请稍后重试")
    
    @staticmethod
    def delete(tag_id):
        tag = db.session.get(Tag, tag_id)
        if not tag:
            return error_response("未找到标签", 404)
        
        from shared.models.models import TestCaseTag, AudioTag, DeviceTag, TaskTag
        
        case_count = TestCaseTag.query.filter_by(tag_id=tag_id).count()
        audio_count = AudioTag.query.filter_by(tag_id=tag_id).count()
        device_count = DeviceTag.query.filter_by(tag_id=tag_id).count()
        task_count = TaskTag.query.filter_by(tag_id=tag_id).count()
        
        total_usage = case_count + audio_count + device_count + task_count
        if total_usage > 0:
            usage_info = []
            if case_count > 0:
                usage_info.append(f"用例 {case_count} 个")
            if audio_count > 0:
                usage_info.append(f"音频 {audio_count} 个")
            if device_count > 0:
                usage_info.append(f"设备 {device_count} 个")
            if task_count > 0:
                usage_info.append(f"任务 {task_count} 个")
            return error_response(f"该标签正在被使用（{', '.join(usage_info)}），请先移除关联")
        
        try:
            tag_name = tag.name
            db.session.delete(tag)
            db.session.commit()
            logger.info(f"删除标签成功: {tag_name} (ID: {tag_id})")
            return success_response(None, "标签删除成功")
        except Exception as e:
            db.session.rollback()
            logger.error(f"删除标签失败: {str(e)}")
            return error_response("删除失败，请稍后重试")
    
    @staticmethod
    def batch_update_category():
        data = request.get_json()
        tag_ids = data.get('tag_ids', [])
        category_id = data.get('category_id')
        
        if not tag_ids:
            return error_response("请选择要操作的标签")
        
        if len(tag_ids) > BATCH_OPERATION_LIMIT:
            return error_response(f"单次最多操作 {BATCH_OPERATION_LIMIT} 个标签")
        
        if category_id is not None and category_id:
            cat = db.session.get(TagCategory, category_id)
            if not cat:
                return error_response(f"未找到标签分类: {category_id}")
        
        try:
            update_data = {'category_id': category_id if category_id else None, 'updated_at': utc8now()}
            updated_count = Tag.query.filter(Tag.id.in_(tag_ids)).update(update_data, synchronize_session=False)
            db.session.commit()
            
            logger.info(f"批量更新标签分类成功: {updated_count} 个标签 -> 分类ID {category_id}")
            return success_response(None, f"已成功更新 {updated_count} 个标签的分类")
        except Exception as e:
            db.session.rollback()
            logger.error(f"批量更新标签分类失败: {str(e)}")
            return error_response("批量更新失败，请稍后重试")
    
    @staticmethod
    def get_tags_by_category():
        categories = TagCategory.query.order_by(TagCategory.sort_order, TagCategory.id).all()
        
        all_tags = Tag.query.order_by(Tag.name).all()
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
