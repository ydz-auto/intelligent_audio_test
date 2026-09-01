# -*- coding: utf-8 -*-
"""分类（Category）写操作 Mixin（从 evaluation_command_service.py 拆分，P4-4）。

提取 create/update/delete_category 三段 Category 写流程，
通过 self.repo 访问 Repository，不直连 DB。
"""
import logging
from typing import Any, Dict

from shared.utils.query_utils import now_cst

from evaluation_service.application.commands._command_utils import (
    command_ok,
    command_error,
)

logger = logging.getLogger(__name__)


class CategoryCommandsMixin:
    """Category 写操作：创建 / 更新 / 软删除"""

    def create_category(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建分类。"""
        name = data.get('name')
        if not name:
            return command_error('分类名称不能为空', code=400)

        try:
            existing = self.repo.get_category_by_name(name)
            if existing:
                return command_error(f'分类名称已存在: {name}', code=400)

            new_cat = self.repo.create_category({
                'name': name,
                'description': data.get('description'),
                'icon': data.get('icon'),
            })
            self.repo.commit()

            return command_ok('分类创建成功', data={'id': new_cat.id}, code=201)
        except Exception as e:
            self.repo.rollback()
            logger.error(f"创建分类失败: {e}")
            return command_error(str(e))

    def update_category(self, cat_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新分类。"""
        try:
            cat = self.repo.get_category_by_id(cat_id)
            if not cat or cat.deleted:
                return command_error('未找到分类', code=404)

            if data.get('name') is not None:
                name = data['name']
                existing = self.repo.get_category_by_name(name)
                if existing and existing.id != cat.id:
                    return command_error(f'分类名称已存在: {name}', code=400)
                cat.name = name

            if data.get('description') is not None:
                cat.description = data['description']
            if data.get('icon') is not None:
                cat.icon = data['icon']

            cat.updated_at = now_cst()
            self.repo.commit()

            return command_ok('分类更新成功')
        except Exception as e:
            self.repo.rollback()
            logger.error(f"更新分类失败: {e}")
            return command_error(str(e))

    def delete_category(self, cat_id: int) -> Dict[str, Any]:
        """软删除分类。"""
        try:
            cat = self.repo.get_category_by_id(cat_id)
            if not cat or cat.deleted:
                return command_error('未找到分类', code=404)

            now = now_cst()
            cat.deleted = True
            cat.deleted_at = now
            cat.updated_at = now
            self.repo.commit()

            return command_ok('分类已删除')
        except Exception as e:
            self.repo.rollback()
            logger.error(f"删除分类失败: {e}")
            return command_error(str(e))
