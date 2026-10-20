# -*- coding: utf-8 -*-
"""报告分享仓储（INT-971）

report_shares 表读写。业务校验（报告存在/权限/密码/过期）在应用服务层完成，
本仓储只做 PO 级读写与计数副作用（@with_session 管理事务）。
"""
from __future__ import annotations

import logging
from typing import List, Optional

from shared.models.database import get_db_session, utc8now
from shared.utils.db_session import with_session

logger = logging.getLogger(__name__)


class ReportShareRepository:
    """report_shares 读写"""

    @with_session(auto_commit=False)
    def report_exists(self, report_id: int) -> bool:
        """报告存在且未逻辑删除。"""
        from report_service.infrastructure.persistence.models import Report
        session = get_db_session()
        po = session.query(Report.id).filter(
            Report.id == int(report_id),
            Report.deleted == False,  # noqa: E712
        ).first()
        return po is not None

    @with_session(auto_commit=True)
    def create(
        self,
        report_id: int,
        token: str,
        access: str,
        expires_at,
        password_hash: Optional[str],
        recipients,
        created_by_user_id,
    ) -> int:
        """新增分享记录，返回主键 ID。"""
        from report_service.infrastructure.persistence.models import ReportShare
        session = get_db_session()
        share = ReportShare(
            report_id=int(report_id),
            token=token,
            access=access,
            expires_at=expires_at,
            password_hash=password_hash,
            recipients=recipients or None,
            created_by_user_id=created_by_user_id,
        )
        session.add(share)
        session.flush()
        return share.id

    @with_session(auto_commit=False)
    def get_report_visibility_info(self, report_id: int) -> Optional[tuple]:
        """按 ID 查询报告可见性二元信息（未删除行），供分享三操作行级可见性校验。

        Returns:
            (created_by_user_id, visibility) 或 None（报告不存在/已软删除）。
        """
        from report_service.infrastructure.persistence.models import Report
        session = get_db_session()
        row = (
            session.query(Report.created_by_user_id, Report.visibility)
            .filter(Report.id == int(report_id),
                    Report.deleted == False)  # noqa: E712
            .first()
        )
        return (row[0], row[1]) if row else None

    @with_session(auto_commit=False)
    def list_by_report(self, report_id: int) -> List:
        """报告的全部分享记录（含已撤销，按 created_at 倒序）。"""
        from report_service.infrastructure.persistence.models import ReportShare
        session = get_db_session()
        return session.query(ReportShare).filter(
            ReportShare.report_id == int(report_id),
        ).order_by(ReportShare.created_at.desc()).all()

    @with_session(auto_commit=False)
    def get_by_token(self, token: str):
        """按 token 读取分享记录（含已撤销/过期，鉴权判定在应用层）。"""
        from report_service.infrastructure.persistence.models import ReportShare
        session = get_db_session()
        return session.query(ReportShare).filter(
            ReportShare.token == token,
        ).first()

    @with_session(auto_commit=True)
    def revoke(self, report_id: int, token: str) -> bool:
        """软撤销分享（幂等：已撤销/不存在返回 False 由调用方归一 404 语义）。

        返回 True 表示该 token 属于该报告且本操作将其置为已撤销。
        """
        from report_service.infrastructure.persistence.models import ReportShare
        session = get_db_session()
        share = session.query(ReportShare).filter(
            ReportShare.report_id == int(report_id),
            ReportShare.token == token,
        ).first()
        if share is None:
            return False
        if not share.revoked:
            share.revoked = True
        return True

    @with_session(auto_commit=True)
    def increment_visits(self, share_id: int) -> None:
        """公开读取 200 放行时原子递增访问计数 + 更新最近访问时间（唯一计数入口）。

        用 UPDATE visits = visits + 1 表达式，避免读-改-写竞态（并发同 token
        读取各自 +1，不互相覆盖）。
        """
        from report_service.infrastructure.persistence.models import ReportShare
        session = get_db_session()
        session.query(ReportShare).filter(
            ReportShare.id == share_id,
        ).update({
            ReportShare.visits: ReportShare.visits + 1,
            # 落 naive UTC+8（对齐 expires_at 口径，SQLite 读回无时区）
            ReportShare.last_visited_at: utc8now().replace(tzinfo=None),
        }, synchronize_session=False)


# 模块级单例
report_share_repository = ReportShareRepository()
