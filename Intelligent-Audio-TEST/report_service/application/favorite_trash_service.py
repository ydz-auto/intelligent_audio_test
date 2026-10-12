# -*- coding: utf-8 -*-
"""收藏 / 回收站应用服务（INT-141，report_service 分治域：report）。"""
from __future__ import annotations

import logging

from shared.infrastructure.user_context import get_current_user_id
from report_service.infrastructure.persistence.report_favorite_trash_repository import (
    report_favorite_trash_repository,
)

logger = logging.getLogger(__name__)


class ReportFavoriteTrashService:
    """收藏 / 回收站应用服务（report）。"""

    def __init__(self, repository=report_favorite_trash_repository):
        self.repository = repository

    # ==================== 收藏 ====================

    def favorite(self, user_id, report_id) -> dict:
        """收藏报告（幂等：重复收藏返回成功 + already_favorited）。"""
        try:
            if not user_id:
                return {'success': False, 'message': '未认证用户禁止收藏',
                        'data': None, 'code': 401}
            result = self.repository.add(user_id, report_id)
            if not result.get('success'):
                return {'success': False, 'message': result.get('message', '报告不存在'),
                        'data': None, 'code': result.get('code', 404)}
            return {'success': True, 'message': result.get('message', '收藏成功'),
                    'data': {'entity_type': 'report', 'report_id': int(report_id),
                             'already_favorited': result.get('already_favorited', False)}}
        except Exception as e:
            logger.error(f"收藏报告失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def unfavorite(self, user_id, report_id) -> dict:
        """取消收藏（幂等：未收藏同样成功）。"""
        try:
            if not user_id:
                return {'success': False, 'message': '未认证用户禁止操作',
                        'data': None, 'code': 401}
            result = self.repository.remove(user_id, report_id)
            return {'success': True, 'message': '取消收藏成功',
                    'data': {'entity_type': 'report', 'report_id': int(report_id),
                             'removed': result.get('removed', 0)}}
        except Exception as e:
            logger.error(f"取消收藏报告失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def list_favorite_ids(self, user_id) -> dict:
        """当前用户收藏的报告 ID 列表。"""
        try:
            if not user_id:
                return {'success': False, 'message': '未认证用户', 'data': None, 'code': 401}
            ids = self.repository.list_ids(user_id)
            return {'success': True, 'message': 'ok',
                    'data': {'entity_type': 'report', 'ids': [str(i) for i in ids]}}
        except Exception as e:
            logger.error(f"查询收藏报告列表失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    # ==================== 回收站 ====================

    def list_deleted_reports(self, page: int = 1, per_page: int = 20, search: str | None = None) -> dict:
        """回收站报告列表（含删除人/删除时间）。"""
        try:
            result = self.repository.list_deleted_reports(page, per_page, search)
            return {'success': True, 'message': 'ok', 'data': result}
        except Exception as e:
            logger.error(f"查询报告回收站失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def restore_reports(self, report_ids: list) -> dict:
        """恢复报告（单个+批量统一入口）。"""
        try:
            if not report_ids:
                return {'success': False, 'message': '缺少 report_ids', 'data': None, 'code': 400}
            restored = self.repository.restore_reports(report_ids)
            return {'success': True, 'message': f'成功恢复 {restored} 个报告',
                    'data': {'restored_count': restored}}
        except Exception as e:
            logger.error(f"恢复报告失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def purge_reports(self, report_ids: list) -> dict:
        """彻底删除报告（物理删除；权限：admin 或 owner，INT-141）。"""
        try:
            if not report_ids:
                return {'success': False, 'message': '缺少 report_ids', 'data': None, 'code': 400}
            from shared.infrastructure.user_context import (
                get_current_user_id, get_current_user_is_admin,
            )
            purged = self.repository.purge_reports(
                report_ids,
                user_id=get_current_user_id(),
                is_admin=get_current_user_is_admin())
            return {'success': True, 'message': f'彻底删除 {purged} 个报告',
                    'data': {'purged_count': purged}}
        except PermissionError as e:
            return {'success': False, 'message': str(e) or '权限不足',
                    'data': {'code': 403}, 'code': 403}
        except Exception as e:
            logger.error(f"彻底删除报告失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}


# 模块级单例
report_favorite_trash_service = ReportFavoriteTrashService()
