# -*- coding: utf-8 -*-
"""TagCrudService - 标签及标签分类 CRUD 服务（写模型 + 读模型）。

职责：
- TagCategory CRUD（创建/更新/删除/查询）
- Tag CRUD（创建/更新/删除/批量更新分类/查询）

整改说明：
- 引入 Repository 模式，消除所有 session 直连 DB（参见 testcase_repository.py）
- 通过 self.repo 调用 Repository，不直连 DB
- 模块级单例 tag_crud_service 保持可用，方法签名与返回格式不变
- 保留软删除模式（deleted=True + deleted_at）

所有方法返回 dict: {success, message, data, code?}
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from sqlalchemy.exc import IntegrityError

from task_service.domain.repositories.testcase_group_repository import TestCaseGroupRepositoryABC
from task_service.infrastructure.persistence.testcase_repository import testcase_repository

logger = logging.getLogger(__name__)

BATCH_OPERATION_LIMIT = 100
NAME_MAX_LENGTH = 50
DESCRIPTION_MAX_LENGTH = 500


class TagCrudService:
    """标签及标签分类 CRUD 服务。"""

    def __init__(self, repo: TestCaseGroupRepositoryABC = None):
        self.repo = repo or testcase_repository

    # ==================== TagCategory 写操作 ====================

    def create_category(self, data: Dict[str, Any]) -> Dict[str, Any]:
        name = (data.get('name') or '').strip()
        if not name:
            return {'success': False, 'message': '分类名称不能为空', 'code': 400}
        if len(name) > NAME_MAX_LENGTH:
            return {'success': False, 'message': f'分类名称不能超过 {NAME_MAX_LENGTH} 个字符', 'code': 400}

        try:
            existing = self.repo.get_tag_category_by_name(name)
            if existing:
                return {'success': False, 'message': f'分类名称已存在: {name}', 'code': 400}

            cat = self.repo.create_tag_category({
                'name': name,
                'description': (data.get('description') or '')[:DESCRIPTION_MAX_LENGTH] if data.get('description') else None,
                'color': data.get('color'),
                'sort_order': data.get('sort_order') or 0,
            })
            self.repo.commit()

            return {
                'success': True,
                'message': '标签分类创建成功',
                'data': self._category_to_dict(cat, 0),
                'code': 201,
            }
        except IntegrityError:
            self.repo.rollback()
            return {'success': False, 'message': f'分类名称已存在: {name}', 'code': 400}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"创建标签分类失败: {e}")
            return {'success': False, 'message': '创建失败，请稍后重试', 'code': 500}

    def update_category(self, category_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            cat = self.repo.get_tag_category_by_id(category_id)
            if not cat or cat.deleted:
                return {'success': False, 'message': '未找到标签分类', 'code': 404}

            if data.get('name') is not None:
                name = (data['name'] or '').strip()
                if not name:
                    return {'success': False, 'message': '分类名称不能为空', 'code': 400}
                if len(name) > NAME_MAX_LENGTH:
                    return {'success': False, 'message': f'分类名称不能超过 {NAME_MAX_LENGTH} 个字符', 'code': 400}
                existing = self.repo.get_tag_category_by_name(name)
                if existing and existing.id != cat.id:
                    return {'success': False, 'message': f'分类名称已存在: {name}', 'code': 400}
                cat.name = name

            if data.get('description') is not None:
                cat.description = (data['description'] or '')[:DESCRIPTION_MAX_LENGTH] if data['description'] else None
            if data.get('color') is not None:
                cat.color = data['color']
            if data.get('sort_order') is not None:
                cat.sort_order = data['sort_order']

            from shared.utils.query_utils import now_cst
            cat.updated_at = now_cst()
            self.repo.commit()

            tag_count = self.repo.count_tags_by_category(cat.id)

            return {
                'success': True,
                'message': '标签分类更新成功',
                'data': self._category_to_dict(cat, tag_count),
            }
        except IntegrityError:
            self.repo.rollback()
            return {'success': False, 'message': f'分类名称已存在: {data.get("name", "")}', 'code': 400}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"更新标签分类失败: {e}")
            return {'success': False, 'message': '更新失败，请稍后重试', 'code': 500}

    def delete_category(self, category_id: int) -> Dict[str, Any]:
        try:
            cat = self.repo.get_tag_category_by_id(category_id)
            if not cat or cat.deleted:
                return {'success': False, 'message': '未找到标签分类', 'code': 404}

            tag_count = self.repo.count_tags_by_category(category_id)
            if tag_count > 0:
                return {'success': False, 'message': f'该分类下还有 {tag_count} 个标签，请先移除或迁移标签', 'code': 400}

            self.repo.soft_delete_tag_category(cat)
            self.repo.commit()

            return {'success': True, 'message': '标签分类删除成功'}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"删除标签分类失败: {e}")
            return {'success': False, 'message': '删除失败，请稍后重试', 'code': 500}

    # ==================== Tag 写操作 ====================

    def create_tag(self, data: Dict[str, Any]) -> Dict[str, Any]:
        name = (data.get('name') or '').strip()
        if not name:
            return {'success': False, 'message': '标签名称不能为空', 'code': 400}
        if len(name) > NAME_MAX_LENGTH:
            return {'success': False, 'message': f'标签名称不能超过 {NAME_MAX_LENGTH} 个字符', 'code': 400}

        category_id = data.get('category_id')

        try:
            if category_id:
                cat = self.repo.get_tag_category_by_id(category_id)
                if not cat or cat.deleted:
                    return {'success': False, 'message': f'未找到标签分类: {category_id}', 'code': 400}

            existing = self.repo.get_active_tag_by_name(name)
            if existing:
                return {'success': False, 'message': f'标签名称已存在: {name}', 'code': 400}

            tag = self.repo.create_tag({
                'name': name,
                'description': (data.get('description') or '')[:DESCRIPTION_MAX_LENGTH] if data.get('description') else None,
                'color': data.get('color'),
                'category_id': category_id,
            })
            self.repo.commit()

            return {
                'success': True,
                'message': '标签创建成功',
                'data': self._tag_to_dict(tag),
                'code': 201,
            }
        except IntegrityError:
            self.repo.rollback()
            return {'success': False, 'message': f'标签名称已存在: {name}', 'code': 400}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"创建标签失败: {e}")
            return {'success': False, 'message': '创建失败，请稍后重试', 'code': 500}

    def update_tag(self, tag_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            tag = self.repo.get_tag_by_id(tag_id)
            if not tag or tag.deleted:
                return {'success': False, 'message': '未找到标签', 'code': 404}

            category_id = data.get('category_id')
            if category_id is not None and category_id:
                cat = self.repo.get_tag_category_by_id(category_id)
                if not cat or cat.deleted:
                    return {'success': False, 'message': f'未找到标签分类: {category_id}', 'code': 400}

            if data.get('name') is not None:
                name = (data['name'] or '').strip()
                if not name:
                    return {'success': False, 'message': '标签名称不能为空', 'code': 400}
                if len(name) > NAME_MAX_LENGTH:
                    return {'success': False, 'message': f'标签名称不能超过 {NAME_MAX_LENGTH} 个字符', 'code': 400}
                existing = self.repo.get_active_tag_by_name(name)
                if existing and existing.id != tag.id:
                    return {'success': False, 'message': f'标签名称已存在: {name}', 'code': 400}
                tag.name = name

            if data.get('description') is not None:
                tag.description = (data['description'] or '')[:DESCRIPTION_MAX_LENGTH] if data['description'] else None
            if data.get('color') is not None:
                tag.color = data['color']
            if data.get('category_id') is not None:
                tag.category_id = category_id if category_id else None

            from shared.utils.query_utils import now_cst
            tag.updated_at = now_cst()
            self.repo.commit()

            return {
                'success': True,
                'message': '标签更新成功',
                'data': self._tag_to_dict(tag),
            }
        except IntegrityError:
            self.repo.rollback()
            return {'success': False, 'message': f'标签名称已存在: {data.get("name", "")}', 'code': 400}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"更新标签失败: {e}")
            return {'success': False, 'message': '更新失败，请稍后重试', 'code': 500}

    def delete_tag(self, tag_id: int) -> Dict[str, Any]:
        try:
            tag = self.repo.get_tag_by_id(tag_id)
            if not tag or tag.deleted:
                return {'success': False, 'message': '未找到标签', 'code': 404}

            case_count = self.repo.count_tag_usage_in_cases(tag_id)
            audio_count = self.repo.count_tag_usage_in_audios(tag_id)
            device_count = self.repo.count_tag_usage_in_devices(tag_id)
            task_count = self.repo.count_tag_usage_in_tasks(tag_id)

            total_usage = case_count + audio_count + device_count + task_count
            if total_usage > 0:
                usage_info = []
                if case_count > 0:
                    usage_info.append(f'用例 {case_count} 个')
                if audio_count > 0:
                    usage_info.append(f'音频 {audio_count} 个')
                if device_count > 0:
                    usage_info.append(f'设备 {device_count} 个')
                if task_count > 0:
                    usage_info.append(f'任务 {task_count} 个')
                return {'success': False, 'message': f'该标签正在被使用（{", ".join(usage_info)}），请先移除关联', 'code': 400}

            self.repo.soft_delete_tag(tag)
            self.repo.commit()

            return {'success': True, 'message': '标签删除成功'}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"删除标签失败: {e}")
            return {'success': False, 'message': '删除失败，请稍后重试', 'code': 500}

    def batch_update_category(self, data: Dict[str, Any]) -> Dict[str, Any]:
        tag_ids = data.get('tag_ids', [])
        category_id = data.get('category_id')

        if not tag_ids:
            return {'success': False, 'message': '请选择要操作的标签', 'code': 400}

        if len(tag_ids) > BATCH_OPERATION_LIMIT:
            return {'success': False, 'message': f'单次最多操作 {BATCH_OPERATION_LIMIT} 个标签', 'code': 400}

        try:
            if category_id is not None and category_id:
                cat = self.repo.get_tag_category_by_id(category_id)
                if not cat or cat.deleted:
                    return {'success': False, 'message': f'未找到标签分类: {category_id}', 'code': 400}

            updated_count = self.repo.batch_update_tag_category(tag_ids, category_id)
            self.repo.commit()

            return {'success': True, 'message': f'已成功更新 {updated_count} 个标签的分类'}
        except Exception as e:
            self.repo.rollback()
            logger.error(f"批量更新标签分类失败: {e}")
            return {'success': False, 'message': '批量更新失败，请稍后重试', 'code': 500}

    # ==================== 读操作 ====================

    def list_categories(self, page: int = 1, per_page: int = 20, keyword: str = None) -> Dict[str, Any]:
        per_page = min(per_page, 100)
        try:
            pagination = self.repo.list_tag_categories_paginated(page=page, per_page=per_page, keyword=keyword)
            items = [self._category_to_dict(cat, tc) for cat, tc in pagination.items]

            return {
                'success': True,
                'message': '',
                'data': {
                    'items': items,
                    'total': pagination.total,
                },
            }
        except Exception as e:
            logger.error(f"查询标签分类列表失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def get_category(self, category_id: int) -> Dict[str, Any]:
        try:
            cat = self.repo.get_tag_category_by_id(category_id)
            if not cat or cat.deleted:
                return {'success': False, 'message': '未找到标签分类', 'code': 404}

            tag_count = self.repo.count_tags_by_category(cat.id)
            return {
                'success': True,
                'message': '',
                'data': self._category_to_dict(cat, tag_count),
            }
        except Exception as e:
            logger.error(f"获取标签分类失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def list_tags(self, page: int = 1, per_page: int = 20, category_id: int = None, keyword: str = None) -> Dict[str, Any]:
        per_page = min(per_page, 100)
        try:
            pagination = self.repo.list_tags_paginated_with_filter(
                page=page, per_page=per_page, category_id=category_id, keyword=keyword
            )
            tags = pagination.items

            cat_ids = {t.category_id for t in tags if t.category_id}
            cat_map = self.repo.get_category_name_map(cat_ids) if cat_ids else {}

            items = [self._tag_to_dict(t, cat_map) for t in tags]

            return {
                'success': True,
                'message': '',
                'data': {
                    'items': items,
                    'total': pagination.total,
                },
            }
        except Exception as e:
            logger.error(f"查询标签列表失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def list_tag_names(self, page: int = 1, per_page: int = 100, keyword: str = None) -> Dict[str, Any]:
        per_page = min(per_page, 500)
        try:
            pagination = self.repo.list_tag_names_paginated(page=page, per_page=per_page, keyword=keyword)
            tag_names = [t.name for t in pagination.items]

            return {
                'success': True,
                'message': '',
                'data': {
                    'items': tag_names,
                    'total': pagination.total,
                },
            }
        except Exception as e:
            logger.error(f"查询标签名称列表失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def get_tag(self, tag_id: int) -> Dict[str, Any]:
        try:
            tag = self.repo.get_tag_by_id(tag_id)
            if not tag or tag.deleted:
                return {'success': False, 'message': '未找到标签', 'code': 404}
            return {
                'success': True,
                'message': '',
                'data': self._tag_to_dict(tag),
            }
        except Exception as e:
            logger.error(f"获取标签失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    def get_tags_by_category(self) -> Dict[str, Any]:
        try:
            categories = self.repo.list_tag_categories_ordered()
            all_tags = self.repo.list_all_tags_ordered_by_name()

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
                tag_items = [self._tag_to_dict(t, {cat.id: cat.name}) for t in cat_tags]
                result.append({
                    'category': self._category_to_dict(cat, len(cat_tags)),
                    'tags': tag_items,
                })

            if uncategorized_tags:
                tag_items = [self._tag_to_dict(t) for t in uncategorized_tags]
                result.append({
                    'category': None,
                    'tags': tag_items,
                })

            return {
                'success': True,
                'message': '',
                'data': {'items': result, 'total': len(result)},
            }
        except Exception as e:
            logger.error(f"获取按分类分组的标签失败: {e}")
            return {'success': False, 'message': str(e), 'code': 500}

    # ==================== 内部辅助 ====================

    @staticmethod
    def _category_to_dict(cat, tag_count: int = 0) -> Dict[str, Any]:
        return {
            'id': cat.id,
            'name': cat.name,
            'description': cat.description,
            'color': cat.color,
            'sort_order': cat.sort_order or 0,
            'tag_count': tag_count,
            'created_at': cat.created_at.isoformat() if cat.created_at else None,
            'updated_at': cat.updated_at.isoformat() if cat.updated_at else None,
        }

    def _tag_to_dict(self, tag, cat_map: Dict = None) -> Dict[str, Any]:
        category_name = None
        if cat_map and tag.category_id:
            category_name = cat_map.get(tag.category_id)
        elif tag.category_id:
            category_name = self.repo.get_category_name_by_id(tag.category_id)

        return {
            'id': tag.id,
            'name': tag.name,
            'description': tag.description,
            'color': tag.color,
            'category_id': tag.category_id,
            'category_name': category_name,
            'created_at': tag.created_at.isoformat() if tag.created_at else None,
            'updated_at': tag.updated_at.isoformat() if tag.updated_at else None,
        }


# 模块级单例
tag_crud_service = TagCrudService()
