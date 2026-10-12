# -*- coding: utf-8 -*-
"""收藏 / 回收站仓储（INT-141，report_service 分治域：report）。

- 收藏表 report_favorites（单库部署下表名全局唯一，task_service 已占用
  favorites，本服务按开发计划文档先例命名 report_favorites）
- 回收站：list_deleted_reports / restore_reports / purge_reports
  （purge 复用 ReportPersistMixin.hard_delete 的子→父顺序）
"""
from sqlalchemy import text, bindparam

from shared.infrastructure.purge_permission import check_purge_permission
from shared.models.common_enums import EntityType
from shared.models.database import get_db_session, utc8now
from shared.utils.db_session import with_session


def _bind_in(sql: str):
    return text(sql).bindparams(bindparam('ids', expanding=True))


class ReportFavoriteTrashRepository:
    """report_favorites 与报告回收站读写"""

    # ==================== 收藏 ====================

    @with_session(auto_commit=True)
    def add(self, user_id, report_id) -> dict:
        """收藏报告（幂等；报告不存在返回 404 语义）"""
        if not user_id:
            raise ValueError("未认证用户禁止收藏（user_id 缺失）")
        session = get_db_session()
        from report_service.infrastructure.persistence.models import Report, ReportFavorite
        po = session.query(Report.id).filter(
            Report.id == int(report_id), Report.deleted == False).first()  # noqa: E712
        if po is None:
            return {'success': False, 'message': '报告不存在或已删除', 'code': 404}
        existing = session.query(ReportFavorite.id).filter(
            ReportFavorite.user_id == user_id,
            ReportFavorite.entity_type == EntityType.REPORT.value,
            ReportFavorite.entity_id == str(report_id),
        ).first()
        if existing:
            return {'success': True, 'already_favorited': True, 'message': '已收藏'}
        try:
            session.add(ReportFavorite(
                user_id=user_id,
                entity_type=EntityType.REPORT.value,
                entity_id=str(report_id)))
            session.flush()
        except Exception:
            session.rollback()
            return {'success': True, 'already_favorited': True, 'message': '已收藏'}
        return {'success': True, 'already_favorited': False, 'message': '收藏成功'}

    @with_session(auto_commit=True)
    def remove(self, user_id, report_id) -> dict:
        """取消收藏（幂等：未收藏同样成功）"""
        session = get_db_session()
        from report_service.infrastructure.persistence.models import ReportFavorite
        deleted = session.query(ReportFavorite).filter(
            ReportFavorite.user_id == user_id,
            ReportFavorite.entity_type == EntityType.REPORT.value,
            ReportFavorite.entity_id == str(report_id),
        ).delete(synchronize_session=False)
        return {'success': True, 'removed': int(deleted or 0), 'message': '取消收藏成功'}

    @with_session(auto_commit=False)
    def list_ids(self, user_id) -> list:
        """当前用户收藏的报告 ID 列表（字符串化）"""
        session = get_db_session()
        from report_service.infrastructure.persistence.models import ReportFavorite
        rows = session.query(ReportFavorite.entity_id).filter(
            ReportFavorite.user_id == user_id,
            ReportFavorite.entity_type == EntityType.REPORT.value,
        ).all()
        return [r[0] for r in rows]

    # ==================== 回收站 ====================

    @with_session(auto_commit=False)
    def list_deleted_reports(self, page: int = 1, per_page: int = 20, search: str | None = None) -> dict:
        """回收站报告列表（含删除人/删除时间）"""
        session = get_db_session()
        from report_service.infrastructure.persistence.models import Report
        where = "WHERE deleted = TRUE"
        params = {}
        if search:
            where += " AND (lower(name) LIKE lower(:kw) OR lower(CAST(id AS VARCHAR)) LIKE lower(:kw))"
            params['kw'] = f"%{search}%"
        total = session.execute(
            text(f"SELECT COUNT(*) FROM test_reports {where}"), params).scalar() or 0
        rows = session.execute(text(
            f"SELECT id, name, type, status, task_id, deleted_at, deleted_by_user_id "
            f"FROM test_reports {where} "
            f"ORDER BY deleted_at DESC LIMIT :lim OFFSET :off"),
            {**params, 'lim': per_page, 'off': (page - 1) * per_page}).mappings().all()
        return {'total': int(total), 'items': [dict(r) for r in rows]}

    @with_session(auto_commit=True)
    def restore_reports(self, report_ids: list) -> int:
        """恢复报告（仅恢复当前处于软删除状态的行）"""
        if not report_ids:
            return 0
        session = get_db_session()
        count = session.execute(
            text("UPDATE test_reports SET deleted = FALSE, deleted_at = NULL "
                 "WHERE id IN :ids AND deleted = TRUE").bindparams(
                bindparam('ids', expanding=True)),
            {"ids": [int(i) for i in report_ids]}).rowcount
        return int(count or 0)

    @with_session(auto_commit=True)
    def purge_reports(self, report_ids: list, user_id=None, is_admin: bool = False) -> int:
        """彻底删除报告及子表（子→父，仅针对软删除行；复用 hard_delete 顺序）。

        权限收敛（INT-141）：仅 admin 或 owner（创建人/删除人）。
        """
        if not report_ids:
            return 0
        session = get_db_session()
        from report_service.infrastructure.persistence.models import (
            Report, ReportSummary, ReportSummaryMeta, ReportRawData,
            ReportCase, ReportMetricStats, ReportComparisonMatrix, ReportFavorite,
        )
        ids = [int(i) for i in report_ids]
        rows = session.query(
            Report.id, Report.created_by_user_id, Report.deleted_by_user_id,
        ).filter(Report.id.in_(ids), Report.deleted == True).all()  # noqa: E712
        if not rows:
            return 0
        check_purge_permission(
            user_id, is_admin,
            [r[1] for r in rows] + [r[2] for r in rows])
        purgeable = [r[0] for r in rows]
        for model in (ReportSummary, ReportSummaryMeta, ReportRawData,
                      ReportCase, ReportMetricStats, ReportComparisonMatrix):
            session.query(model).filter(model.report_id.in_(purgeable)).delete(
                synchronize_session=False)
        session.query(ReportFavorite).filter(
            ReportFavorite.entity_type == EntityType.REPORT.value,
            ReportFavorite.entity_id.in_([str(i) for i in purgeable]),
        ).delete(synchronize_session=False)
        session.query(Report).filter(Report.id.in_(purgeable)).delete(
            synchronize_session=False)
        return len(purgeable)


# 单例
report_favorite_trash_repository = ReportFavoriteTrashRepository()
