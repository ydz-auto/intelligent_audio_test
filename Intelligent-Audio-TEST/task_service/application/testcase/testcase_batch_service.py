# -*- coding: utf-8 -*-
"""TestCaseBatchService — 测试用例批量操作应用服务。

从 testcase_crud_service 拆分，承担所有批量动作（删除/移动/复制/参数更新/
播放设备/声压/维度/噪声/自动命名/标签增删改/参考参数刷新）。

约定：
- 所有方法返回 dict: {success, message, data, code?}
- 通过 self.repo 调用 Repository，不直连 DB
- 保留软删除模式（deleted=True + deleted_at）

按职责拆分为 Mixin 组合（对外 API 不变，导入路径保持本模块）：
- testcase_batch_reference_mixin.TestCaseReferenceRefreshMixin: 参考参数刷新（含模块级辅助函数）
- testcase_batch_copy_move_mixin.TestCaseCopyMoveMixin: 删除/移动/复制/自动命名
- testcase_batch_config_update_mixin.TestCaseConfigUpdateMixin: 专属参数/播放设备/声压/维度/噪声更新
- testcase_batch_tag_mixin.TestCaseTagMixin: 标签批量操作
- 本文件保留 batch_action 动作调度入口与依赖注入。
"""
from __future__ import annotations

import logging
from typing import Tuple

from task_service.domain.repositories.testcase_group_repository import TestCaseGroupRepositoryABC
from task_service.infrastructure.persistence.testcase_repository import testcase_repository

from task_service.application.testcase.testcase_batch_reference_mixin import (
    TestCaseReferenceRefreshMixin,
    _REF_PARAMS_BUCKET,
    _build_ref_params_key,
    _apply_reference_params_to_config,
)
from task_service.application.testcase.testcase_batch_copy_move_mixin import TestCaseCopyMoveMixin
from task_service.application.testcase.testcase_batch_config_update_mixin import TestCaseConfigUpdateMixin
from task_service.application.testcase.testcase_batch_tag_mixin import TestCaseTagMixin

logger = logging.getLogger(__name__)

# 模块级公共符号再导出（保持向后兼容：_REF_PARAMS_BUCKET / _build_ref_params_key /
# _apply_reference_params_to_config 仍可从本模块导入）
__all__ = [
    'TestCaseBatchService',
    '_REF_PARAMS_BUCKET',
    '_build_ref_params_key',
    '_apply_reference_params_to_config',
]


class TestCaseBatchService(
    TestCaseReferenceRefreshMixin,
    TestCaseCopyMoveMixin,
    TestCaseConfigUpdateMixin,
    TestCaseTagMixin,
):
    """测试用例批量操作应用服务。

    职责拆分为四个 Mixin 组合：
    - TestCaseReferenceRefreshMixin: 参考参数刷新
    - TestCaseCopyMoveMixin: 删除/移动/复制/自动命名
    - TestCaseConfigUpdateMixin: 配置更新（参数/设备/声压/维度/噪声）
    - TestCaseTagMixin: 标签批量操作
    """

    def __init__(self, repo: TestCaseGroupRepositoryABC = None):
        self.repo = repo or testcase_repository

    def batch_action(self, data: dict) -> dict:
        """批量操作。

        Args:
            data: {action, ids, ...} — 已通过网关 Pydantic 校验

        Returns:
            {success, message, data, code?}
        """
        from shared.utils import testcase_helpers as common

        action = data.get('action')
        ids = data.get('ids', [])

        handlers = {
            'delete': self._batch_delete,
            'move_to_group': self._batch_move_to_group,
            'copy_to_group': self._batch_copy_to_group,
            'copy': self._batch_copy,
            'copy_by_group': self._batch_copy_by_group,
            'update_algorithm_params': self._batch_update_algorithm_params,
            'update_playback_devices': self._batch_update_playback_devices,
            'update_spl': self._batch_update_spl,
            'update_dimensions': self._batch_update_dimensions,
            'update_noise': self._batch_update_noise,
            'auto_generate_name': self._batch_auto_generate_name,
            'add_tags': self._batch_add_tags,
            'remove_tags': self._batch_remove_tags,
            'rename_tag': self._batch_rename_tag,
            'refresh_reference': self._batch_refresh_reference,
        }

        handler = handlers.get(action)
        if not handler:
            return {'success': False, 'message': f"不支持的操作类型: {action}", 'data': None, 'code': 400}

        try:
            result = handler(data, common=common)
            # handler 返回 dict 表示提前返回（如异步任务提交）
            if isinstance(result, dict):
                return {'success': True, 'message': result.get('message', ''), 'data': result, 'code': 0}
            # handler 返回 (message, is_error) tuple
            if isinstance(result, tuple) and len(result) == 2:
                message, is_error = result
                if is_error:
                    return {'success': False, 'message': message, 'data': None, 'code': 400}
                # 正常 message，继续 commit
                message = result[0]
            else:
                message = result

            self.repo.commit()

            try:
                from api_gateway.application.services.stats_cache import refresh_stats_cache
                refresh_stats_cache()
            except Exception:
                logger.warning("批量操作后刷新统计缓存失败", exc_info=True)

            return {'success': True, 'message': message, 'data': None}
        except Exception as e:
            logger.error(f"批量操作失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}
