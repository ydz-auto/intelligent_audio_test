"""标签写操作 Service。

从 TagController / TagCategoryController 抽取的 CRUD、批量操作方法。
"""
import logging

from api_gateway.infrastructure.request_adapter import request
from sqlalchemy.exc import IntegrityError
from shared.models.models import Tag, TagCategory
from shared.models.database import db
from shared.utils.response import success_response, error_response
from shared.utils.query_utils import now_cst

from api_gateway.schemas.testcase import (
    TagCategoryItem,
    TagCategoryCreateSchema,
    TagCategoryUpdateSchema,
    TagItem,
    TagCreateSchema,
    TagUpdateSchema,
)

logger = logging.getLogger(__name__)

BATCH_OPERATION_LIMIT = 100
NAME_MAX_LENGTH = 50
DESCRIPTION_MAX_LENGTH = 500


def utc8now():
    return now_cst()


class TagCategoryCommandService:
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
            existing = TagCategory.query.filter_by(name=name, deleted=False).first()
            if existing:
                return error_response(f"分类名称已存在: {name}")

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
        if not cat or cat.deleted:
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
                existing = TagCategory.query.filter_by(name=name, deleted=False).first()
                if existing and existing.id != cat.id:
                    return error_response(f"分类名称已存在: {name}")
                cat.name = name

            if data.description is not None:
                cat.description = data.description[:DESCRIPTION_MAX_LENGTH] if data.description else None
            if data.color is not None:
                cat.color = data.color
            if data.sort_order is not None:
                cat.sort_order = data.sort_order

            cat.updated_at = utc8now()
            db.session.commit()

            tag_count = Tag.query.filter_by(category_id=cat.id, deleted=False).count()

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
        if not cat or cat.deleted:
            return error_response("未找到标签分类", 404)

        tag_count = Tag.query.filter_by(category_id=category_id, deleted=False).count()
        if tag_count > 0:
            return error_response(f"该分类下还有 {tag_count} 个标签，请先移除或迁移标签")

        try:
            cat_name = cat.name
            now = now_cst()
            cat.deleted = True
            cat.deleted_at = now
            cat.updated_at = now
            db.session.commit()
            logger.info(f"删除标签分类成功: {cat_name} (ID: {category_id})")
            return success_response(None, "标签分类删除成功")
        except Exception as e:
            db.session.rollback()
            logger.error(f"删除标签分类失败: {str(e)}")
            return error_response("删除失败，请稍后重试")


class TagCommandService:
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
            if not cat or cat.deleted:
                return error_response(f"未找到标签分类: {data.category_id}")

        try:
            existing = Tag.query.filter_by(name=name, deleted=False).first()
            if existing:
                return error_response(f"标签名称已存在: {name}")

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
                if cat and not cat.deleted:
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
        if not tag or tag.deleted:
            return error_response("未找到标签", 404)

        try:
            data = TagUpdateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}")

        if data.category_id is not None and data.category_id:
            cat = db.session.get(TagCategory, data.category_id)
            if not cat or cat.deleted:
                return error_response(f"未找到标签分类: {data.category_id}")

        try:
            if data.name is not None:
                name = data.name.strip()
                if not name:
                    return error_response("标签名称不能为空")
                if len(name) > NAME_MAX_LENGTH:
                    return error_response(f"标签名称不能超过 {NAME_MAX_LENGTH} 个字符")
                existing = Tag.query.filter_by(name=name, deleted=False).first()
                if existing and existing.id != tag.id:
                    return error_response(f"标签名称已存在: {name}")
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
                if cat and not cat.deleted:
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
        if not tag or tag.deleted:
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
            now = now_cst()
            tag.deleted = True
            tag.deleted_at = now
            tag.updated_at = now
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
            if not cat or cat.deleted:
                return error_response(f"未找到标签分类: {category_id}")

        try:
            update_data = {'category_id': category_id if category_id else None, 'updated_at': utc8now()}
            updated_count = Tag.query.filter(Tag.id.in_(tag_ids), Tag.deleted == False).update(update_data, synchronize_session=False)
            db.session.commit()

            logger.info(f"批量更新标签分类成功: {updated_count} 个标签 -> 分类ID {category_id}")
            return success_response(None, f"已成功更新 {updated_count} 个标签的分类")
        except Exception as e:
            db.session.rollback()
            logger.error(f"批量更新标签分类失败: {str(e)}")
            return error_response("批量更新失败，请稍后重试")
