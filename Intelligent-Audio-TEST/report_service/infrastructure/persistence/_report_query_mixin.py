# -*- coding: utf-8 -*-
"""Report 主表查询 Mixin（从 report_repository.py 拆分，P4-5 大文件拆分）。

职责：Report 主表的聚合根查询（按 ID / 按任务 / 分页列表 / 趋势数据）
与原始 PO 查询（供报告生成引擎直接使用 PO）。

依赖 self.PO_CLASS（= Report），由 ReportRepository 组合时提供。
"""
from __future__ import annotations

import json
from typing import List, Optional

from shared.infrastructure.user_context import (
    get_current_user_id,
    get_current_user_is_admin,
)
from shared.infrastructure.visibility_filter import (
    VisibilityDenied,
    check_visible,
    visible_condition,
)
from shared.models.database import get_db_session
from shared.utils.db_session import with_session

from report_service.infrastructure.persistence._report_converters import (
    _report_po_to_entity,
)


def _brief_name(name, analysis) -> str:
    """列表摘要报告名：PO.name 优先，空则回退 analysis(JSON).name。

    与逐任务 ListReports → _aggregate_to_dict 的 name 口径一致
    （'name': aggregate.name or config.get('name') or ''）。
    """
    if name:
        return name
    try:
        config = json.loads(analysis) if analysis else {}
    except (TypeError, ValueError):
        config = {}
    if isinstance(config, dict):
        return config.get('name') or ''
    return ''


class ReportQueryMixin:
    """Report 主表查询（依赖 PO_CLASS 与 _report_po_to_entity）。"""

    PO_CLASS = None  # 由 ReportRepository 提供（Report）

    @with_session
    def get_by_id(self, report_id: int) -> Optional[object]:
        """按 ID 加载报告聚合根（不含子实体集合）。

        Returns:
            ReportAggregate 或 None（报告不存在 / 已软删除 / 私有非 owner 不可见）。
        """
        session = get_db_session()
        po = session.get(self.PO_CLASS, report_id)
        if po is None or po.deleted:
            return None
        # INT-423 行级可见性：私有报告仅 owner/admin 可见，越权按不存在处理（防探测）
        try:
            check_visible(
                po.created_by_user_id, po.visibility,
                get_current_user_id(), get_current_user_is_admin())
        except VisibilityDenied:
            return None
        return _report_po_to_entity(po)

    @with_session
    def get_by_id_unchecked(self, report_id: int) -> Optional[object]:
        """按 ID 加载报告聚合根（不做行级可见性过滤，INT-1043 分享读取专用）。

        有效未撤销的分享链接是 owner 的显式授权：GetSharedReport 成功路径
        直取未删报告详情，不受 report.visibility 行级过滤拦截（授权不因
        visibility 收回）；分享有效性已在 report_share_service.get_shared_report
        校验。报告不存在 / 已软删除仍返回 None（调用方映射 404）。
        """
        session = get_db_session()
        po = session.get(self.PO_CLASS, report_id)
        if po is None or po.deleted:
            return None
        return _report_po_to_entity(po)

    @with_session
    def get_by_task(self, task_id: int) -> Optional[object]:
        """按任务 ID 加载报告聚合根（取最新一条未删除报告）。

        一个任务可能对应多个报告版本，取最新创建的一条。
        """
        session = get_db_session()
        po = (
            session.query(self.PO_CLASS)
            .filter(self.PO_CLASS.task_id == task_id, self.PO_CLASS.deleted == False)  # noqa: E712
            .order_by(self.PO_CLASS.created_at.desc())
            .first()
        )
        if po is None:
            return None
        # INT-423 行级可见性：私有报告仅 owner/admin 可见，越权按不存在处理
        try:
            check_visible(
                po.created_by_user_id, po.visibility,
                get_current_user_id(), get_current_user_is_admin())
        except VisibilityDenied:
            return None
        return _report_po_to_entity(po)

    @with_session
    def list_reports(
        self,
        status: Optional[str] = None,
        report_types: Optional[List[str]] = None,
        task_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
        favorite: bool = False,
        deleted: bool = False,
        user_id: Optional[int] = None,
    ) -> List[object]:
        """分页列出报告聚合根。

        Args:
            status: 可选状态过滤（pending/generating/completed/failed）
            report_types: 可选类型集合过滤（IN 口径，INT-280 对比视图多类型；
                空集合或 None 不过滤）
            task_id: 可选任务 ID 精确过滤（INT-262）
            page: 页码（从 1 开始）
            page_size: 每页数量
            favorite: 可选（INT-141）仅当前用户收藏
            deleted: 可选（INT-141）仅回收站软删除项
            user_id: 可选，收藏过滤/标记用当前用户

        Returns:
            聚合根列表（不含子实体集合）。
        """
        from sqlalchemy import select as sa_select, cast as sa_cast, String
        from shared.models.common_enums import EntityType

        session = get_db_session()
        query = session.query(self.PO_CLASS).filter(
            self.PO_CLASS.deleted == (True if deleted else False))  # noqa: E712
        # INT-423 行级过滤：admin 全量 / 共享全可见 / 私有仅 owner（user_id 取 x-user-id context）
        query = query.filter(visible_condition(
            self.PO_CLASS.created_by_user_id,
            self.PO_CLASS.visibility,
            get_current_user_id(),
            get_current_user_is_admin(),
        ))
        if status:
            query = query.filter(self.PO_CLASS.status == status)
        if report_types:
            query = query.filter(self.PO_CLASS.type.in_(report_types))
        if task_id:
            query = query.filter(self.PO_CLASS.task_id == task_id)
        if favorite:
            from report_service.infrastructure.persistence.models import ReportFavorite
            if not user_id:
                return []
            query = query.filter(sa_select(ReportFavorite.id)
                                 .where(ReportFavorite.user_id == user_id,
                                        ReportFavorite.entity_type == EntityType.REPORT.value,
                                        ReportFavorite.entity_id == sa_cast(self.PO_CLASS.id, String))
                                 .correlate(self.PO_CLASS)
                                 .exists())
        query = query.order_by(self.PO_CLASS.created_at.desc())
        # 分页：limit/offset（避免依赖 Flask-SQLAlchemy paginate）
        page = max(page, 1)
        page_size = max(page_size, 1)
        rows = query.limit(page_size).offset((page - 1) * page_size).all()
        return [_report_po_to_entity(po) for po in rows]

    @with_session
    def list_report_briefs_by_task_ids(
        self, task_ids: List[int], per_task_limit: int = 100,
    ) -> dict:
        """页级批量：一次查询取回整页任务的报告摘要（INT-1462）。

        与 list_reports 同一套软删/可见性口径；不加载摘要子表，
        只投影列表页需要的 id/name/status/type/created_at。

        Args:
            task_ids: 页面任务 ID 集合
            per_task_limit: 每个任务最多返回条数（超出部分不计入列表徽标）

        Returns:
            {task_id(int): [{id,name,status,type,created_at}, ...]}；
            无报告的任务不出现在结果中。
        """
        ids = [int(t) for t in task_ids or []]
        if not ids:
            return {}
        limit = max(int(per_task_limit or 100), 1)
        session = get_db_session()
        query = session.query(
            self.PO_CLASS.id,
            self.PO_CLASS.task_id,
            self.PO_CLASS.name,
            self.PO_CLASS.type,
            self.PO_CLASS.status,
            self.PO_CLASS.created_at,
            # 报告名历史约定：PO.name 为空时回退 analysis(JSON) 里的 name
            # （与 list_reports → _aggregate_to_dict 同名口径）
            self.PO_CLASS.analysis,
        ).filter(
            self.PO_CLASS.deleted == False,  # noqa: E712
            self.PO_CLASS.task_id.in_(ids),
        )
        # 行级可见性：与 list_reports 同口径（admin 全量 / 共享全可见 / 私有仅 owner）
        query = query.filter(visible_condition(
            self.PO_CLASS.created_by_user_id,
            self.PO_CLASS.visibility,
            get_current_user_id(),
            get_current_user_is_admin(),
        ))
        query = query.order_by(
            self.PO_CLASS.task_id,
            self.PO_CLASS.created_at.desc(),
            self.PO_CLASS.id.desc(),
        )
        briefs: dict = {}
        for row in query.all():
            bucket = briefs.setdefault(int(row.task_id), [])
            if len(bucket) >= limit:
                continue
            bucket.append({
                'id': row.id,
                'name': _brief_name(row.name, row.analysis),
                'status': row.status,
                'type': row.type,
                'created_at': str(row.created_at) if row.created_at is not None else None,
            })
        return briefs

    @with_session
    def count_reports(
        self,
        status: Optional[str] = None,
        report_types: Optional[List[str]] = None,
        task_id: Optional[int] = None,
        favorite: bool = False,
        deleted: bool = False,
        user_id: Optional[int] = None,
    ) -> int:
        """按 list_reports 同一套过滤条件计数（INT-297：分页信封补 total/pages）。

        Args:
            status/report_types/task_id/favorite/deleted/user_id: 与 list_reports 口径一致。

        Returns:
            满足过滤条件的报告总数。
        """
        from sqlalchemy import select as sa_select, cast as sa_cast, String
        from shared.models.common_enums import EntityType

        session = get_db_session()
        query = session.query(self.PO_CLASS).filter(
            self.PO_CLASS.deleted == (True if deleted else False))  # noqa: E712
        # INT-423 行级过滤：与 list_reports 同一套可见性口径（分页 total 对齐）
        query = query.filter(visible_condition(
            self.PO_CLASS.created_by_user_id,
            self.PO_CLASS.visibility,
            get_current_user_id(),
            get_current_user_is_admin(),
        ))
        if status:
            query = query.filter(self.PO_CLASS.status == status)
        if report_types:
            query = query.filter(self.PO_CLASS.type.in_(report_types))
        if task_id:
            query = query.filter(self.PO_CLASS.task_id == task_id)
        if favorite:
            from report_service.infrastructure.persistence.models import ReportFavorite
            if not user_id:
                return 0
            query = query.filter(sa_select(ReportFavorite.id)
                                 .where(ReportFavorite.user_id == user_id,
                                        ReportFavorite.entity_type == EntityType.REPORT.value,
                                        ReportFavorite.entity_id == sa_cast(self.PO_CLASS.id, String))
                                 .correlate(self.PO_CLASS)
                                 .exists())
        return query.count()

    @with_session
    def count_reports_by_tabs(self, deleted: bool = False) -> dict:
        """四个视图 Tab 的计数（INT-1463：单条条件聚合 SQL，替代 4 次 CountReports）。

        Tab 口径与 Tab 过滤映射一致（与 count_reports 同一套可见性/软删过滤）：
        - all:        无过滤
        - draft:      status = draft
        - published:  status = published
        - comparison: type IN (comparison, secondary_comparison)

        Args:
            deleted: 是否统计回收站软删除项（默认 False，与列表活跃口径一致）

        Returns:
            {'all': N, 'draft': N, 'published': N, 'comparison': N}
        """
        from sqlalchemy import case as sa_case, func as sa_func

        from shared.models.common_enums import ReportStatus, ReportType

        session = get_db_session()
        comparison_types = [ReportType.COMPARISON.value, ReportType.SECONDARY_COMPARISON.value]
        row = (
            session.query(
                sa_func.count(self.PO_CLASS.id),
                sa_func.coalesce(
                    sa_func.sum(sa_case((self.PO_CLASS.status == ReportStatus.DRAFT.value, 1),
                                        else_=0)), 0),
                sa_func.coalesce(
                    sa_func.sum(sa_case((self.PO_CLASS.status == ReportStatus.PUBLISHED.value, 1),
                                        else_=0)), 0),
                sa_func.coalesce(
                    sa_func.sum(sa_case((self.PO_CLASS.type.in_(comparison_types), 1),
                                        else_=0)), 0),
            )
            .filter(self.PO_CLASS.deleted == (True if deleted else False))  # noqa: E712
            .filter(visible_condition(
                self.PO_CLASS.created_by_user_id,
                self.PO_CLASS.visibility,
                get_current_user_id(),
                get_current_user_is_admin(),
            ))
            .one()
        )
        return {
            'all': int(row[0] or 0),
            'draft': int(row[1] or 0),
            'published': int(row[2] or 0),
            'comparison': int(row[3] or 0),
        }

    # ---- 可见性辅助（INT-423，供命令侧 check_visible / 批量 filter_visible_owners） ----

    @with_session
    def get_report_visibility_info(self, report_id: int) -> Optional[tuple]:
        """按 ID 查询报告可见性三元信息（未删除行）。

        Returns:
            (created_by_user_id, visibility) 或 None（报告不存在/已软删除）。
            命令侧（update/delete）先取本信息做 check_visible：私有非 owner
            抛 VisibilityDenied（网关映射 403），区别于不存在（返回 False → 404）。
        """
        session = get_db_session()
        row = (
            session.query(self.PO_CLASS.created_by_user_id, self.PO_CLASS.visibility)
            .filter(self.PO_CLASS.id == report_id,
                    self.PO_CLASS.deleted == False)  # noqa: E712
            .first()
        )
        return (row[0], row[1]) if row else None

    @with_session
    def list_report_visibility_rows(self, report_ids: List[int]) -> List[tuple]:
        """批量查询报告可见性三元组 [(id, created_by_user_id, visibility), ...]。

        供批量操作（BatchActionReports）逐行过滤：不可见行跳过，不整批放行。
        """
        session = get_db_session()
        if not report_ids:
            return []
        rows = (
            session.query(self.PO_CLASS.id, self.PO_CLASS.created_by_user_id,
                          self.PO_CLASS.visibility)
            .filter(self.PO_CLASS.id.in_(report_ids),
                    self.PO_CLASS.deleted == False)  # noqa: E712
            .all()
        )
        return [tuple(r) for r in rows]

    # ---- 原始 PO 查询（供报告生成引擎直接使用 PO） ----

    @with_session
    def get_report_by_id_raw(self, report_id: int):
        """按 ID 查询原始 Report PO（不转换为实体）。

        供报告生成引擎检查已存在报告使用，返回 PO 或 None。
        """
        session = get_db_session()
        return session.get(self.PO_CLASS, report_id)

    @with_session
    def get_report_by_task_id_raw(self, task_id: int):
        """按 task_id 查询原始 Report PO（不转换为实体）。

        取最新一条未删除报告，返回 PO 或 None。
        """
        session = get_db_session()
        return (
            session.query(self.PO_CLASS)
            .filter(self.PO_CLASS.task_id == task_id, self.PO_CLASS.deleted == False)  # noqa: E712
            .order_by(self.PO_CLASS.created_at.desc())
            .first()
        )

    @with_session
    def get_cases_by_report_id(self, report_id: int) -> list:
        """按 report_id 查询原始 ReportCase PO 列表。

        供报告生成引擎读取已存用例数据使用，返回 PO 列表。
        """
        from report_service.infrastructure.persistence.models import ReportCase

        session = get_db_session()
        return (
            session.query(ReportCase)
            .filter(ReportCase.report_id == report_id)
            .all()
        )

    @with_session
    def get_trend_data(
        self,
        report_type: Optional[str] = None,
        task_id: Optional[int] = None,
        limit: int = 50,
    ) -> list:
        """查询报告趋势数据。

        按 created_at 升序返回已完成报告及其摘要，用于计算成功率/时长趋势。

        Args:
            report_type: 可选报告类型过滤（如 'task'）
            task_id: 可选任务 ID 过滤
            limit: 最多返回条数

        Returns:
            list[dict]: 每条含 report_id/name/created_at/pass_rate/duration
        """
        from report_service.infrastructure.persistence.models import ReportSummary

        session = get_db_session()
        query = (
            session.query(self.PO_CLASS, ReportSummary)
            .outerjoin(ReportSummary, self.PO_CLASS.id == ReportSummary.report_id)
            .filter(self.PO_CLASS.deleted == False)  # noqa: E712
        )
        # INT-465 修复（P2）：趋势查询注入行级过滤，与 list_reports/count_reports
        # 同一口径——私有报告的名称/成功率/时长不得进入非 owner 的趋势结果
        query = query.filter(visible_condition(
            self.PO_CLASS.created_by_user_id,
            self.PO_CLASS.visibility,
            get_current_user_id(),
            get_current_user_is_admin(),
        ))
        if report_type:
            query = query.filter(self.PO_CLASS.type == report_type)
        if task_id:
            query = query.filter(self.PO_CLASS.task_id == task_id)
        query = query.order_by(self.PO_CLASS.created_at.asc()).limit(limit)
        rows = query.all()
        return [
            {
                'report_id': r.id,
                'name': r.name,
                'created_at': r.created_at,
                'pass_rate': s.pass_rate if s else 0,
                'duration': s.duration if s else 0,
            }
            for r, s in rows
        ]

    # ---- 统计分析基础行（INT-791：/reports/statistics*） ----

    @with_session
    def get_statistics_rows(self, start_time=None, end_time=None, algorithm_type=None):
        """查询统计用报告基础行（主表 + 摘要 + 元数据，外连接）。

        Args:
            start_time: datetime 或 None，created_at >= start_time
            end_time: datetime 或 None，created_at <= end_time
            algorithm_type: str 或 None，按 report_cases.algorithm_type 存在性过滤
                （报告无 algorithm_type 列，以用例级算法类型归属）

        Returns:
            list[tuple(Report, ReportSummary|None, ReportSummaryMeta|None)]，
            按 created_at 升序。
        """
        from sqlalchemy import select as sa_select

        from report_service.infrastructure.persistence.models import (
            ReportCase,
            ReportSummary,
            ReportSummaryMeta,
        )

        session = get_db_session()
        query = (
            session.query(self.PO_CLASS, ReportSummary, ReportSummaryMeta)
            .outerjoin(ReportSummary, self.PO_CLASS.id == ReportSummary.report_id)
            .outerjoin(ReportSummaryMeta, self.PO_CLASS.id == ReportSummaryMeta.report_id)
            .filter(self.PO_CLASS.deleted == False)  # noqa: E712
        )
        if start_time is not None:
            query = query.filter(self.PO_CLASS.created_at >= start_time)
        if end_time is not None:
            query = query.filter(self.PO_CLASS.created_at <= end_time)
        if algorithm_type:
            query = query.filter(
                sa_select(ReportCase.id)
                .where(ReportCase.report_id == self.PO_CLASS.id,
                       ReportCase.algorithm_type == algorithm_type)
                .correlate(self.PO_CLASS)
                .exists()
            )
        query = query.order_by(self.PO_CLASS.created_at.asc())
        return query.all()

    @with_session
    def get_metric_stats_for_report_ids(self, report_ids):
        """按 report_id 批量加载 ReportMetricStats，返回 {report_id: po}。

        供统计分析报表生成（device_performance 类型）读取设备/API 统计快照。
        """
        if not report_ids:
            return {}
        from report_service.infrastructure.persistence.models import ReportMetricStats
        session = get_db_session()
        rows = (
            session.query(ReportMetricStats)
            .filter(ReportMetricStats.report_id.in_(report_ids))
            .all()
        )
        return {po.report_id: po for po in rows}
