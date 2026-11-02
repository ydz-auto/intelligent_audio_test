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
from shared.models.database import get_db_session, get_engine
from shared.utils.db_session import with_session

from report_service.infrastructure.persistence._report_converters import (
    _report_po_to_entity,
)


def _search_like_pattern(keyword: Optional[str]) -> Optional[str]:
    """搜索关键字 → 安全 LIKE 模式（INT-2329）；空串/纯空白返回 None（不过滤）。

    转义顺序须先反斜杠再 % / _，否则已插入的转义符会被二次转义
    （对齐 shared.utils.query_utils.escape_like_pattern 的意图，但修正其顺序）。
    """
    from shared.utils.query_utils import sanitize_keyword

    keyword = sanitize_keyword(keyword)
    if not keyword:
        return None
    escaped = (keyword.replace('\\', '\\\\')
               .replace('%', '\\%')
               .replace('_', '\\_'))
    return f'%{escaped}%'


def _analysis_text_field(column, field: str):
    """analysis 列（TEXT 存 config JSON）按字段取文本的 SQL 表达式。

    INT-2329 返工：生成报告只把名称/描述写进 config（落到 analysis 列），
    ``test_reports.name`` / ``description`` 为空，列表展示名走
    ``aggregate.name or config['name']``（servicers._aggregate_to_dict）。
    搜索必须与展示同口径，否则「列表里看得见、搜不到」。

    analysis 允许是任意文本（历史行存过纯文本结论），非法 JSON 直接取字段会让
    整条查询报错，因此先判有效性再取字段：PostgreSQL 用 ``pg_input_is_valid``
    （PG16 起提供，docker/docker-compose.yml 固定 postgres:16-alpine），
    SQLite（单测）用 ``json_valid``；非 JSON 行该表达式为 NULL（不参与命中）。
    """
    from sqlalchemy import and_, case, cast, func, literal_column

    engine = get_engine()
    dialect = engine.dialect.name if engine is not None else ''
    if dialect == 'sqlite':
        return case(
            (and_(column.isnot(None), func.json_valid(column) == 1),
             func.json_extract(column, f'$.{field}')),
            else_=None,
        )
    from sqlalchemy.dialects.postgresql import JSONB
    return case(
        (and_(column.isnot(None),
              func.pg_input_is_valid(column, literal_column("'jsonb'"))),
         func.jsonb_extract_path_text(cast(column, JSONB), field)),
        else_=None,
    )


def _report_search_condition(po_class, pattern: str):
    """INT-2329：报告关键字过滤条件（列表与 count 共用，保证同口径）。

    匹配范围与列表展示一致：名称/描述取物理列，为空时展示回退 analysis
    JSON 里的 ``name`` / ``description``，故两处一并纳入。
    """
    from sqlalchemy import or_

    return or_(
        po_class.name.ilike(pattern, escape='\\'),
        po_class.description.ilike(pattern, escape='\\'),
        _analysis_text_field(po_class.analysis, 'name').ilike(pattern, escape='\\'),
        _analysis_text_field(po_class.analysis, 'description').ilike(
            pattern, escape='\\'),
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
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        favorite: bool = False,
        deleted: bool = False,
        user_id: Optional[int] = None,
    ) -> List[object]:
        """分页列出报告聚合根。

        Args:
            status: 可选状态过滤（draft / published）
            report_types: 可选类型集合过滤（IN 口径，INT-280 对比视图多类型；
                空集合或 None 不过滤）
            task_id: 可选任务 ID 精确过滤（INT-262）
            search: 可选关键字（INT-2329：报告名称/描述模糊匹配，忽略大小写；
                名称/描述为空时按展示口径回退 analysis JSON 的同名字段；
                空白不过滤）
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
        pattern = _search_like_pattern(search)
        if pattern:
            # INT-2329：名称/描述关键字模糊匹配（与 count_reports 同口径，
            # 含 analysis JSON 里展示名/描述的回退字段）
            query = query.filter(_report_search_condition(self.PO_CLASS, pattern))
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
        search: Optional[str] = None,
        favorite: bool = False,
        deleted: bool = False,
        user_id: Optional[int] = None,
    ) -> int:
        """按 list_reports 同一套过滤条件计数（INT-297：分页信封补 total/pages）。

        Args:
            status/report_types/task_id/search/favorite/deleted/user_id:
                与 list_reports 口径一致（search 见 INT-2329）。

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
        pattern = _search_like_pattern(search)
        if pattern:
            # INT-2329：与 list_reports 同一套名称/描述关键字匹配
            query = query.filter(_report_search_condition(self.PO_CLASS, pattern))
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
    def count_reports_by_tabs(
        self,
        search: Optional[str] = None,
        favorite: bool = False,
        deleted: bool = False,
        user_id: Optional[int] = None,
    ) -> dict:
        """Tab / 类型 / 收藏计数（INT-1463 单条聚合；INT-2339 随筛选收缩）。

        计数入参只有 search / favorite / deleted + 当前用户可见性；
        status / report_type 属 Tab 自身维度，不参与过滤：
        - all:        无 status/type 过滤
        - draft:      status = draft
        - published:  status = published
        - comparison: type IN (comparison, secondary_comparison)
        - types:      ReportType 四值分别计数
        - favorite:   当前用户收藏且命中同一筛选集的条数（无 user_id 为 0）

        Args:
            search: 关键字（与 list_reports / count_reports 同一套
                ``_report_search_condition`` 口径）
            favorite: 仅当前用户收藏（与 count_reports.favorite 一致；
                无 user_id 时与列表一致返回全 0，不退回全量）
            deleted: 是否统计回收站软删除项（默认 False，与列表活跃口径一致）
            user_id: 当前用户（收藏过滤/计数；x-user-id metadata）

        Returns:
            {'all': N, 'draft': N, 'published': N, 'comparison': N,
             'types': {'task': N, 'comparison': N, 'secondary_comparison': N,
                       'benchmark': N},
             'favorite': N}
        """
        from sqlalchemy import (
            String,
            case as sa_case,
            cast as sa_cast,
            false as sa_false,
            func as sa_func,
            literal as sa_literal,
            select as sa_select,
        )

        from shared.models.common_enums import EntityType, ReportStatus, ReportType

        session = get_db_session()
        comparison_types = [ReportType.COMPARISON.value,
                            ReportType.SECONDARY_COMPARISON.value]
        type_values = [ReportType.TASK.value, ReportType.COMPARISON.value,
                       ReportType.SECONDARY_COMPARISON.value, ReportType.BENCHMARK.value]

        fav_exists = None
        if user_id:
            from report_service.infrastructure.persistence.models import ReportFavorite
            fav_exists = (
                sa_select(ReportFavorite.id)
                .where(ReportFavorite.user_id == user_id,
                       ReportFavorite.entity_type == EntityType.REPORT.value,
                       ReportFavorite.entity_id == sa_cast(self.PO_CLASS.id, String))
                .correlate(self.PO_CLASS)
                .exists()
            )

        def _count_if(condition):
            return sa_func.coalesce(
                sa_func.sum(sa_case((condition, 1), else_=0)), 0)

        row = (
            session.query(
                sa_func.count(self.PO_CLASS.id),
                _count_if(self.PO_CLASS.status == ReportStatus.DRAFT.value),
                _count_if(self.PO_CLASS.status == ReportStatus.PUBLISHED.value),
                _count_if(self.PO_CLASS.type.in_(comparison_types)),
                # INT-2339：ReportType 四值分别计数
                *[_count_if(self.PO_CLASS.type == value) for value in type_values],
                # INT-2339：当前用户收藏数（无 user_id 时为 0）
                _count_if(fav_exists) if fav_exists is not None else sa_literal(0),
            )
            .filter(self.PO_CLASS.deleted == (True if deleted else False))  # noqa: E712
            .filter(visible_condition(
                self.PO_CLASS.created_by_user_id,
                self.PO_CLASS.visibility,
                get_current_user_id(),
                get_current_user_is_admin(),
            ))
        )
        pattern = _search_like_pattern(search)
        if pattern:
            # INT-2339：与列表同一套名称/描述关键字口径
            row = row.filter(_report_search_condition(self.PO_CLASS, pattern))
        if favorite:
            # 与 count_reports.favorite 一致：未认证用户没有收藏，返回全 0
            row = row.filter(fav_exists if fav_exists is not None else sa_false())
        row = row.one()
        return {
            'all': int(row[0] or 0),
            'draft': int(row[1] or 0),
            'published': int(row[2] or 0),
            'comparison': int(row[3] or 0),
            'types': {value: int(row[4 + idx] or 0)
                      for idx, value in enumerate(type_values)},
            'favorite': int(row[8] or 0),
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
    def get_report_by_id_visible(self, report_id: int):
        """按 ID 查询原始 Report PO，带软删 + 行级可见性过滤。

        INT-2236：二次对比等「读源报告内容再复制」的链路用本方法，不得复用
        ``get_report_by_id_raw``（那是不带过滤的生成引擎口径）。不存在 / 已软删 /
        私有非 owner 一律返回 None，由调用方整批拒绝（与 INT-423 防探测口径一致，
        不区分「不存在」与「无权」）。
        """
        session = get_db_session()
        po = session.get(self.PO_CLASS, report_id)
        if po is None or po.deleted:
            return None
        try:
            check_visible(
                po.created_by_user_id, po.visibility,
                get_current_user_id(), get_current_user_is_admin())
        except VisibilityDenied:
            return None
        return po

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
        """按 report_id 查询 ReportCase 行列表（对比 / 挑选合并 / 导出复用）。

        供报告生成引擎读取已存用例数据使用，返回行对象列表（属性名与 PO 一致）。

        INT-1994（档4 R1）：默认按快照解引用（一次批量取 ``payload_gz``）。
        INT-1995（档4 M1）：9 个内容列已 DROP，恒走快照解引用。

        INT-2041：显式 ``ORDER BY report_cases.id``——无 ORDER BY 时行序跟堆物理
        序，回填 UPDATE 即可整体换序，对比 / 挑选合并的用例顺序会跟着漂。补
        ORDER BY 后顺序 = id 序（≈插入序），是确定化而非回归。
        """
        from report_service.infrastructure.persistence.models import ReportCase
        from report_service.infrastructure.persistence.report_case_snapshot_store import (
            resolve_rows,
        )

        session = get_db_session()
        rows = (
            session.query(ReportCase)
            .filter(ReportCase.report_id == report_id)
            .order_by(ReportCase.id.asc())
            .all()
        )
        return resolve_rows(session, rows, report_id=report_id)

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
    def get_statistics_rows(self, start_time=None, end_time=None, algorithm_type=None,
                            limit=None):
        """查询统计用报告基础行（主表 + 摘要 + 元数据，外连接）。

        Args:
            start_time: datetime 或 None，created_at >= start_time
            end_time: datetime 或 None，created_at <= end_time
            algorithm_type: str 或 None，按 report_cases.algorithm_type 存在性过滤
                （报告无 algorithm_type 列，以用例级算法类型归属）
            limit: int 或 None，最多返回行数（服务端上限由应用层传入，
                超限判定后显式报错，不做静默截断）

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
        # INT-2237 修复（P1）：统计/趋势/报表生成三入口共用本基础行，必须注入
        # 行级过滤，与 list_reports/count_reports/get_trend_data 同一口径——
        # 私有报告的名称/通过率/时长/设备不得并入非 owner 的统计聚合
        query = query.filter(visible_condition(
            self.PO_CLASS.created_by_user_id,
            self.PO_CLASS.visibility,
            get_current_user_id(),
            get_current_user_is_admin(),
        ))
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
        if limit is not None:
            query = query.limit(limit)
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
