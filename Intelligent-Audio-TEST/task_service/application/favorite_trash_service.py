# -*- coding: utf-8 -*-
"""收藏 / 回收站应用服务（INT-141，task_service 分治域：task|testcase）。

CQRS：写侧命令经本服务落库；读侧查询走查询服务（列表 favorite/deleted 过滤
在 read_model / query mixin）。所有方法返回 dict: {success, message, data, code?}。
"""
from __future__ import annotations

import logging

from shared.models.common_enums import EntityType
from task_service.infrastructure.persistence.favorite_repository import favorite_repository
from task_service.infrastructure.persistence.trash_repository import trash_repository

logger = logging.getLogger(__name__)

_TASK_ENTITY_TYPES = frozenset({EntityType.TASK.value, EntityType.TESTCASE.value})


class FavoriteTrashService:
    """收藏 / 回收站应用服务（task|testcase）。"""

    # ==================== 收藏 ====================

    def favorite(self, user_id, entity_type: str, entity_id: str) -> dict:
        """收藏（幂等：重复收藏返回成功 + already_favorited）。"""
        try:
            if entity_type not in _TASK_ENTITY_TYPES:
                return {'success': False,
                        'message': f'非法实体类型: {entity_type}（task_service 仅支持 task/testcase）',
                        'data': {'code': 400}, 'code': 400}
            result = favorite_repository.add(user_id, entity_type, str(entity_id))
            if not result.get('success'):
                code = result.get('code', 404)
                return {'success': False, 'message': result.get('message', '实体不存在'),
                        'data': {'code': code}, 'code': code}
            return {'success': True, 'message': result.get('message', '收藏成功'),
                    'data': {'entity_type': entity_type, 'entity_id': str(entity_id),
                             'already_favorited': result.get('already_favorited', False)}}
        except ValueError as e:
            return {'success': False, 'message': str(e), 'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"收藏失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def unfavorite(self, user_id, entity_type: str, entity_id: str) -> dict:
        """取消收藏（幂等：未收藏同样成功）。"""
        try:
            if entity_type not in _TASK_ENTITY_TYPES:
                return {'success': False,
                        'message': f'非法实体类型: {entity_type}（task_service 仅支持 task/testcase）',
                        'data': {'code': 400}, 'code': 400}
            result = favorite_repository.remove(user_id, entity_type, str(entity_id))
            return {'success': True, 'message': '取消收藏成功',
                    'data': {'entity_type': entity_type, 'entity_id': str(entity_id),
                             'removed': result.get('removed', 0)}}
        except ValueError as e:
            return {'success': False, 'message': str(e), 'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"取消收藏失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': {'code': 500}, 'code': 500}

    def list_favorite_ids(self, user_id, entity_type: str | None = None) -> dict:
        """当前用户收藏的实体 ID 列表（字符串化）。"""
        try:
            ids = favorite_repository.list_ids(user_id, entity_type or None)
            return {'success': True, 'message': 'ok',
                    'data': {'entity_type': entity_type, 'ids': [str(i) for i in ids]}}
        except ValueError as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}
        except Exception as e:
            logger.error(f"查询收藏列表失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    # ==================== 回收站 ====================

    def list_deleted_tasks(self, page: int = 1, per_page: int = 20, search: str | None = None) -> dict:
        """回收站任务列表（含删除人/删除时间）。"""
        try:
            result = trash_repository.list_deleted_tasks(page, per_page, search)
            return {'success': True, 'message': 'ok', 'data': result}
        except Exception as e:
            logger.error(f"查询任务回收站失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def restore_tasks(self, task_ids: list) -> dict:
        """恢复任务（单个+批量统一入口）。"""
        try:
            if not task_ids:
                return {'success': False, 'message': '缺少 task_ids', 'data': {'code': 400}, 'code': 400}
            restored = trash_repository.restore_tasks(task_ids)
            self._refresh_stats_cache()
            return {'success': True, 'message': f'成功恢复 {restored} 个任务',
                    'data': {'restored_count': restored}}
        except Exception as e:
            logger.error(f"恢复任务失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def purge_tasks(self, task_ids: list) -> dict:
        """彻底删除任务（物理删除；权限：admin 或 owner，INT-141）。"""
        try:
            if not task_ids:
                return {'success': False, 'message': '缺少 task_ids', 'data': {'code': 400}, 'code': 400}
            from shared.infrastructure.user_context import (
                get_current_user_id, get_current_user_is_admin,
            )
            purged = trash_repository.purge_tasks(
                task_ids,
                user_id=get_current_user_id(),
                is_admin=get_current_user_is_admin())
            self._refresh_stats_cache()
            return {'success': True, 'message': f'彻底删除 {purged} 个任务',
                    'data': {'purged_count': purged}}
        except PermissionError as e:
            # code 经 data JSON 透传（gRPC TaskConfigResponse 仅 success/message/data 三字段）
            return {'success': False, 'message': str(e) or '权限不足', 'data': {'code': 403}, 'code': 403}
        except Exception as e:
            logger.error(f"彻底删除任务失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def list_deleted_testcases(self, page: int = 1, per_page: int = 20, keyword: str | None = None) -> dict:
        """回收站用例列表（含删除人/删除时间）。"""
        try:
            result = trash_repository.list_deleted_testcases(page, per_page, keyword)
            return {'success': True, 'message': 'ok', 'data': result}
        except Exception as e:
            logger.error(f"查询用例回收站失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def restore_testcases(self, case_ids: list) -> dict:
        """恢复用例（单个+批量统一入口）。"""
        try:
            if not case_ids:
                return {'success': False, 'message': '缺少 case_ids', 'data': {'code': 400}, 'code': 400}
            restored = trash_repository.restore_testcases(case_ids)
            self._refresh_stats_cache()
            return {'success': True, 'message': f'成功恢复 {restored} 个用例',
                    'data': {'restored_count': restored}}
        except Exception as e:
            logger.error(f"恢复用例失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def purge_testcases(self, case_ids: list) -> dict:
        """彻底删除用例（物理删除；权限：admin 或 owner，INT-141）。"""
        try:
            if not case_ids:
                return {'success': False, 'message': '缺少 case_ids', 'data': {'code': 400}, 'code': 400}
            from shared.infrastructure.user_context import (
                get_current_user_id, get_current_user_is_admin,
            )
            purged = trash_repository.purge_testcases(
                case_ids,
                user_id=get_current_user_id(),
                is_admin=get_current_user_is_admin())
            self._refresh_stats_cache()
            return {'success': True, 'message': f'彻底删除 {purged} 个用例',
                    'data': {'purged_count': purged}}
        except PermissionError as e:
            return {'success': False, 'message': str(e) or '权限不足', 'data': {'code': 403}, 'code': 403}
        except Exception as e:
            logger.error(f"彻底删除用例失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    @staticmethod
    def _refresh_stats_cache():
        try:
            from api_gateway.application.services.stats_cache import refresh_stats_cache
            refresh_stats_cache()
        except Exception:
            logger.debug("回收站操作后刷新统计缓存失败", exc_info=True)


# 模块级单例
favorite_trash_service = FavoriteTrashService()
