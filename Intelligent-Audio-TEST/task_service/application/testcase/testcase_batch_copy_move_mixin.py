# -*- coding: utf-8 -*-
"""测试用例批量复制/删除/移动 Mixin — TestCaseCopyMoveMixin。

从 testcase_batch_service.py 按职责拆分，承担：
- 批量删除（软删除）
- 批量移动到分组
- 批量复制到指定分组 / 原地复制 / 按分组整体复制
- 自动命名

复制用例的公共逻辑抽取为 _copy_one_testcase，消除三处重复代码。
由 TestCaseBatchService 组合复用，不单独实例化。
"""
from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


class TestCaseCopyMoveMixin:
    """测试用例批量复制/删除/移动 Mixin。"""

    def _batch_delete(self, data, common=None):
        """批量删除（软删除）。"""
        ids = data.get('ids', [])
        self.repo.soft_delete_testcases_by_ids(ids)
        return f"已成功批量删除 {len(ids)} 个用例"

    def _batch_move_to_group(self, data, common=None):
        """批量移动用例到目标分组。"""
        ids = data.get('ids', [])
        target_group_id = data.get('target_group_id')
        if not target_group_id:
            return ("移动操作需要 'target_group_id'", True)
        self.repo.update_testcase_group_id_by_ids(ids, target_group_id)
        return f"已成功将 {len(ids)} 个用例移动至目标分组"

    def _copy_one_testcase(self, tc, group_id, name=None):
        """复制单个用例到指定分组（含标签关联与参考参数刷新），返回新用例。

        name 为 None 时沿用原用例名称；复制场景需创建时即带 _copy 后缀。
        """
        new_id = str(uuid.uuid4())
        new_tc = self.repo.create_testcase({
            'id': new_id,
            'name': name if name is not None else tc.name,
            'description': tc.description,
            'group_id': group_id,
            'config': tc.config.copy() if tc.config else {},
            'algorithm_type': tc.algorithm_type,
            'test_type': tc.test_type or 'api',
        })
        # 复制标签关联
        for tag in tc.tags:
            new_tc.tags.append(tag)
        try:
            from task_service.application.testcase.testcase_batch_reference_mixin import (
                _apply_reference_params_to_config,
            )
            _apply_reference_params_to_config(new_tc)
        except Exception:
            logger.warning("复制用例时刷新参考文本失败 tc_id=%s", tc.id, exc_info=True)
        return new_tc

    def _batch_copy_to_group(self, data, common=None):
        """批量复制用例到指定分组。"""
        ids = data.get('ids', [])
        target_group_id = data.get('target_group_id')
        if not target_group_id:
            return ("复制到分组操作需要 'target_group_id'", True)

        target_group = self.repo.get_group_by_id(target_group_id)
        if not target_group:
            return (f"未找到目标分组: {target_group_id}", True)

        copied_count = 0
        for tc_id in ids:
            tc = self.repo.get_testcase(tc_id)
            if tc:
                self._copy_one_testcase(tc, target_group_id)
                copied_count += 1
        return f"已成功复制 {copied_count} 个用例到分组 '{target_group.name}'"

    def _batch_copy(self, data, common=None):
        """批量复制用例（保留原分组，名称追加 _copy）。"""
        ids = data.get('ids', [])
        copied_count = 0
        for tc_id in ids:
            tc = self.repo.get_testcase(tc_id)
            if tc:
                new_tc = self._copy_one_testcase(tc, tc.group_id)
                new_tc.name = f"{tc.name}_copy"
                copied_count += 1
        return f"已成功批量复制 {copied_count} 个用例"

    def _batch_copy_by_group(self, data, common=None):
        """按分组整体复制（复制分组下全部用例到新分组）。"""
        group_name = data.get('group_name')
        if not group_name:
            return ("复制分组操作需要 'group_name'", True)

        source_group = self.repo.get_group_by_name(group_name)
        if not source_group:
            return (f"未找到分组: {group_name}", True)

        new_group_name = f"{group_name}_copy"
        existing_group = self.repo.get_group_by_name(new_group_name)
        if existing_group:
            new_group = existing_group
        else:
            new_group = self.repo.create_group(
                str(uuid.uuid4()), new_group_name, source_group.description
            )

        test_cases = self.repo.list_testcases_by_group(source_group.id)
        copied_count = 0
        for tc in test_cases:
            self._copy_one_testcase(tc, new_group.id)
            copied_count += 1
        return f"已成功复制分组 '{new_group_name}' 的 {copied_count} 个用例"

    def _batch_copy_by_tag(self, data, common=None):
        """按标签整体复制（复制标签下全部用例到 'tag_name_copy' 标签）。

        copy_to_new_group 为 true 时另建 'tag_name_copy' 分组，否则保留原分组。
        """
        tag_name = data.get('tag_name')
        if not tag_name:
            return ("复制标签操作需要 'tag_name'", True)

        source_tag = self.repo.get_active_tag_by_name(tag_name)
        if not source_tag:
            return (f"未找到标签: {tag_name}", True)

        new_tag_name = f"{tag_name}_copy"
        new_tag = self.repo.get_active_tag_by_name(new_tag_name)
        if not new_tag:
            new_tag = self.repo.get_or_create_tag(new_tag_name)

        new_group = None
        if data.get('copy_to_new_group'):
            new_group_name = f"{tag_name}_copy"
            new_group = self.repo.get_group_by_name(new_group_name)
            if not new_group:
                new_group = self.repo.create_group(
                    str(uuid.uuid4()), new_group_name, f"从标签 '{tag_name}' 复制"
                )

        test_cases = self.repo.query_testcases_by_tag_ids([source_tag.id])
        copied_count = 0
        for tc in test_cases:
            group_id = new_group.id if new_group else tc.group_id
            new_tc = self._copy_one_testcase(tc, group_id)
            if new_tag not in new_tc.tags:
                new_tc.tags.append(new_tag)
            copied_count += 1
        return f"已成功复制标签 '{new_tag_name}' 的 {copied_count} 个用例"

    def _batch_auto_generate_name(self, data, common=None):
        """批量自动生成用例名称。"""
        ids = data.get('ids', [])
        self.repo.auto_generate_names_by_tag_order(ids)
        return f"已成功为 {len(ids)} 个用例自动生成名称"
