# -*- coding: utf-8 -*-
"""测试用例批量标签操作 Mixin — TestCaseTagMixin。

从 testcase_batch_service.py 按职责拆分，承担标签批量操作：
- 添加标签（_batch_add_tags）
- 移除标签（_batch_remove_tags）
- 重命名标签（_batch_rename_tag）

由 TestCaseBatchService 组合复用，不单独实例化。
"""
from __future__ import annotations


class TestCaseTagMixin:
    """测试用例批量标签操作 Mixin。"""

    def _batch_add_tags(self, data, common=None):
        """批量添加标签。"""
        ids = data.get('ids', [])
        tags_to_add = data.get('tags') or []
        if not tags_to_add:
            return ("添加标签需要 'tags' 参数", True)
        self.repo.add_tags_to_testcases(ids, tags_to_add)
        return f"已成功为 {len(ids)} 个用例添加标签"

    def _batch_remove_tags(self, data, common=None):
        """批量移除标签。"""
        ids = data.get('ids', [])
        tags_to_remove = data.get('tags') or []
        if not tags_to_remove:
            return ("移除标签需要 'tags' 参数", True)
        self.repo.remove_tags_from_testcases(ids, tags_to_remove)
        return f"已成功为 {len(ids)} 个用例移除标签"

    def _batch_rename_tag(self, data, common=None):
        """批量重命名标签（校验旧名/新名并委托仓储）。"""
        old_tag_name = data.get('old_tag_name')
        new_tag_name = data.get('new_tag_name')
        if not old_tag_name or not new_tag_name:
            return ("重命名标签需要 'old_tag_name' 和 'new_tag_name' 参数", True)
        if old_tag_name == new_tag_name:
            return ("新标签名不能与原标签名相同", True)

        result = self.repo.rename_tag(old_tag_name, new_tag_name)
        if result is None:
            return (f"未找到标签: {old_tag_name}", True)
        old_tag, new_tag_exists = result
        if new_tag_exists:
            return (f"标签名 {new_tag_name} 已存在", True)
        self.repo.update_tag_name(old_tag, new_tag_name)
        return f"已成功将标签 {old_tag_name} 重命名为 {new_tag_name}"
