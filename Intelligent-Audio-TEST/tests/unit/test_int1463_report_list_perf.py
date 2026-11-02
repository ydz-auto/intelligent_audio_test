# -*- coding: utf-8 -*-
"""INT-1463 专项：报告列表 / Tab 计数性能优化的行为锁定。

背景：压测显示 GET /reports 并发下 p50 与 p95 差距大、GET /reports/tab-counts
400ms+。定位到两处结构性问题：

1. ListReports 逐条 load_summaries —— 每页 20 条即 20 次额外查询（N+1）；
2. tab-counts 由 api_gateway 串行发起 4 次 CountReports RPC（每次全量 count）。

本文件锁定优化后的契约：

- 仓储：load_summaries_batch 单次 IN 查询按 report_id 分组（空入参不发查询）
- 处理器：handle_list 走批量加载，不再调用逐条 load_summaries
- 仓储/处理器/gRPC：count_reports_by_tabs 一条条件聚合 SQL 给出四 Tab 计数，
  口径与 CountReports 一致（all/draft/published/comparison，活跃 + 可见性过滤）

DB：进程级 SQLite（tests/conftest.py 注入），对齐 test_int280 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.database import (  # noqa: E402
    Base, init_db, get_engine, get_db_session, remove_db_session,
)
from shared.utils.grpc_json import loads as grpc_loads  # noqa: E402

_REPORT_TABLES = None


def _ensure_report_tables():
    init_db(pool_size=2)
    global _REPORT_TABLES
    if _REPORT_TABLES is None:
        from report_service.infrastructure.persistence.models import (
            Report, ReportSummary, ReportSummaryMeta, ReportRawData,
            ReportCase, ReportMetricStats, ReportComparisonMatrix, ReportFavorite,
        )
        _REPORT_TABLES = [t.__table__ for t in (
            Report, ReportSummary, ReportSummaryMeta, ReportRawData,
            ReportCase, ReportMetricStats, ReportComparisonMatrix, ReportFavorite,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_REPORT_TABLES)
    return _REPORT_TABLES


def _cleanup_tables(tables):
    session = get_db_session()
    try:
        for table in tables:
            session.execute(table.delete())
        session.commit()
    finally:
        remove_db_session()


def _make_report(name, type_='task', status='draft', deleted=False):
    from report_service.infrastructure.persistence.models import Report
    session = get_db_session()
    try:
        po = Report(name=name, type=type_, status=status, deleted=deleted,
                    visibility='shared')
        session.add(po)
        session.commit()
        return po.id
    finally:
        remove_db_session()


def _make_summary(report_id, total_cases=1, pass_rate=100.0):
    from report_service.infrastructure.persistence.models import ReportSummary
    session = get_db_session()
    try:
        # SQLite 不给 BigInteger 主键自增（INTEGER PRIMARY KEY 才自增），显式给 id
        next_id = (session.query(ReportSummary.id).order_by(
            ReportSummary.id.desc()).first() or (0,))[0] + 1
        po = ReportSummary(id=next_id, report_id=report_id,
                           total_cases=total_cases, pass_rate=pass_rate)
        session.add(po)
        session.commit()
        return po.id
    finally:
        remove_db_session()


class TestSummariesBatchLoad:
    """仓储：摘要批量加载（列表页 N+1 → 单查询）。"""

    def setup_method(self):
        _ensure_report_tables()

    def teardown_method(self):
        _cleanup_tables(_REPORT_TABLES)

    def test_batch_groups_by_report_id(self):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        rid_a = _make_report('INT1463_batch_a')
        rid_b = _make_report('INT1463_batch_b')
        rid_c = _make_report('INT1463_batch_c')  # 无摘要
        _make_summary(rid_a, total_cases=7, pass_rate=88.5)
        _make_summary(rid_b, total_cases=3, pass_rate=50.0)

        grouped = report_repository.load_summaries_batch([rid_a, rid_b, rid_c])
        assert set(grouped) == {rid_a, rid_b}          # 无摘要报告不出现
        assert len(grouped[rid_a]) == 1
        assert grouped[rid_a][0].metadata.get('total_cases') == 7
        assert grouped[rid_b][0].metadata.get('total_cases') == 3

    def test_batch_empty_input_skips_query(self):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        assert report_repository.load_summaries_batch([]) == {}
        assert report_repository.load_summaries_batch(None) == {}


class TestHandleListNoNPlusOne:
    """处理器：handle_list 走批量加载，不再逐条查摘要。"""

    def setup_method(self):
        _ensure_report_tables()

    def teardown_method(self):
        _cleanup_tables(_REPORT_TABLES)

    def test_handle_list_does_not_call_per_report_load(self, monkeypatch):
        from report_service.application.handlers.report_handlers import (
            ReportQueryHandler,
        )
        from report_service.application.queries.report_queries import ListReportsQuery
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        rid = _make_report('INT1463_list_a')
        _make_summary(rid, total_cases=11, pass_rate=72.0)

        def _forbidden(*args, **kwargs):  # pragma: no cover - 触发即缺陷回归
            raise AssertionError('handle_list 不得再逐条 load_summaries（N+1 回归）')

        monkeypatch.setattr(report_repository, 'load_summaries', _forbidden)

        aggregates = ReportQueryHandler().handle_list(ListReportsQuery(page=1, page_size=20))
        assert len(aggregates) == 1
        assert aggregates[0].summaries, '批量加载后摘要不得为空'
        assert aggregates[0].flat_summary()['total_cases'] == 11


class TestCountReportsByTabs:
    """仓储 / 处理器 / gRPC：四 Tab 一次聚合计数。"""

    def setup_method(self):
        _ensure_report_tables()

    def teardown_method(self):
        _cleanup_tables(_REPORT_TABLES)

    def test_repository_counts_four_tabs(self):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('INT1463_tabs_task_draft', type_='task', status='draft')
        _make_report('INT1463_tabs_task_pub', type_='task', status='published')
        _make_report('INT1463_tabs_cmp_draft', type_='comparison', status='draft')
        _make_report('INT1463_tabs_sec_pub', type_='secondary_comparison',
                     status='published')
        _make_report('INT1463_tabs_deleted', type_='task', status='draft', deleted=True)

        counts = report_repository.count_reports_by_tabs()
        # 活跃行 4 条，软删 1 条不计入
        assert counts['all'] == 4
        assert counts['draft'] == 2
        assert counts['published'] == 2
        assert counts['comparison'] == 2
        # INT-2339：类型计数四值分开，收藏数为 0（无 user_id）
        assert counts['types'] == {'task': 2, 'comparison': 1,
                                   'secondary_comparison': 1, 'benchmark': 0}
        assert counts['favorite'] == 0

    def test_repository_matches_count_reports_per_tab(self):
        """聚合口径与 CountReports（逐 Tab）一致，防两套口径漂移。"""
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('INT1463_parity_a', type_='task', status='draft')
        _make_report('INT1463_parity_b', type_='comparison', status='published')
        _make_report('INT1463_parity_c', type_='secondary_comparison', status='draft')

        tabs = report_repository.count_reports_by_tabs()
        assert tabs['all'] == report_repository.count_reports()
        assert tabs['draft'] == report_repository.count_reports(status='draft')
        assert tabs['published'] == report_repository.count_reports(status='published')
        assert tabs['comparison'] == report_repository.count_reports(
            report_types=['comparison', 'secondary_comparison'])

    def test_grpc_count_reports_by_tabs(self):
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        _make_report('INT1463_grpc_cmp', type_='comparison', status='draft')
        _make_report('INT1463_grpc_task', type_='task', status='published')

        resp = ReportServicer().CountReportsByTabs(
            report_pb.CountReportsByTabsRequest(), context=None)
        assert resp.success is True
        data = grpc_loads(resp.data, {}) or {}
        assert data == {
            'all': 2, 'draft': 1, 'published': 1, 'comparison': 1,
            'types': {'task': 1, 'comparison': 1,
                      'secondary_comparison': 0, 'benchmark': 0},
            'favorite': 0,
        }


def _make_favorite(report_id, user_id):
    from report_service.infrastructure.persistence.models import ReportFavorite
    session = get_db_session()
    try:
        session.add(ReportFavorite(user_id=user_id, entity_type='report',
                                   entity_id=str(report_id)))
        session.commit()
    finally:
        remove_db_session()


class _FakeGrpcContext:
    """最小 gRPC context：只提供 invocation_metadata。"""

    def __init__(self, user_id=None, is_admin=False):
        self._meta = [('x-user-is-admin', 'true' if is_admin else 'false')]
        if user_id is not None:
            self._meta.append(('x-user-id', str(user_id)))

    def invocation_metadata(self):
        return self._meta


class TestCountReportsByTabsFiltered:
    """INT-2339：Tab / 类型 / 收藏计数与列表同口径，随 keyword 收缩。"""

    def setup_method(self):
        _ensure_report_tables()

    def teardown_method(self):
        _cleanup_tables(_REPORT_TABLES)

    def test_search_shrinks_tabs_and_matches_list_total(self):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('INT2339_话轮接管_任务报告', type_='task', status='draft')
        _make_report('INT2339_话轮接管_对比报告', type_='comparison',
                     status='published')
        _make_report('INT2339_无关报告', type_='task', status='published')

        counts = report_repository.count_reports_by_tabs(search='话轮接管')
        assert counts['all'] == 2
        assert counts['draft'] == 1
        assert counts['published'] == 1
        assert counts['comparison'] == 1
        assert counts['types'] == {'task': 1, 'comparison': 1,
                                   'secondary_comparison': 0, 'benchmark': 0}
        # 与列表 total 同口径（INT-2339 验收第 2 条）
        assert counts['all'] == report_repository.count_reports(search='话轮接管')

    def test_types_sum_equals_all(self):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('INT2339_类型_task', type_='task')
        _make_report('INT2339_类型_cmp', type_='comparison')
        _make_report('INT2339_类型_sec', type_='secondary_comparison')
        _make_report('INT2339_类型_bench', type_='benchmark')
        _make_report('INT2339_类型_软删', type_='task', deleted=True)

        counts = report_repository.count_reports_by_tabs()
        assert counts['types'] == {'task': 1, 'comparison': 1,
                                   'secondary_comparison': 1, 'benchmark': 1}
        assert sum(counts['types'].values()) == counts['all'] == 4

    def test_search_no_match_returns_all_zero(self):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('INT2339_存在报告')

        counts = report_repository.count_reports_by_tabs(search='zzzz_no_such')
        assert counts['all'] == counts['draft'] == counts['published'] == 0
        assert counts['comparison'] == counts['favorite'] == 0
        assert sum(counts['types'].values()) == 0

    def test_favorite_requires_user_and_does_not_fall_back_to_full(self):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        hit = _make_report('INT2339_收藏命中', type_='task', status='draft')
        _make_report('INT2339_收藏无关')
        _make_favorite(hit, 7)

        # 有 user_id：收藏数与列表同口径
        counts = report_repository.count_reports_by_tabs(search='收藏命中',
                                                         user_id=7)
        assert counts['all'] == 1
        assert counts['favorite'] == 1

        # favorite=True 作为入参：整组计数收窄到收藏集
        only = report_repository.count_reports_by_tabs(favorite=True, user_id=7)
        assert only['all'] == 1
        assert only['favorite'] == 1

        # 无 user_id：与 count_reports(favorite=True) 一致，全 0 不退回全量
        none_user = report_repository.count_reports_by_tabs(favorite=True)
        assert none_user['all'] == 0
        assert none_user['favorite'] == 0
        assert report_repository.count_reports(favorite=True) == 0

    def test_favorite_count_follows_search_scope(self):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        rid_a = _make_report('INT2339_收藏子集_甲')
        rid_b = _make_report('INT2339_收藏子集_乙')
        _make_favorite(rid_a, 9)
        _make_favorite(rid_b, 9)
        _make_report('INT2339_他人报告')

        counts = report_repository.count_reports_by_tabs(search='收藏子集',
                                                         user_id=9)
        assert counts['all'] == 2
        assert counts['favorite'] == 2

        other_scope = report_repository.count_reports_by_tabs(search='他人',
                                                              user_id=9)
        assert other_scope['all'] == 1
        assert other_scope['favorite'] == 0

    def test_deleted_passthrough(self):
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('INT2339_活跃')
        _make_report('INT2339_回收站', deleted=True)

        assert report_repository.count_reports_by_tabs()['all'] == 1
        assert report_repository.count_reports_by_tabs(deleted=True)['all'] == 1

    def test_grpc_forwards_search_favorite_and_user(self):
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        hit = _make_report('INT2339_gRPC_话轮接管')
        _make_report('INT2339_gRPC_无关')
        _make_favorite(hit, 7)

        resp = ReportServicer().CountReportsByTabs(
            report_pb.CountReportsByTabsRequest(search='话轮接管', favorite=True),
            context=_FakeGrpcContext(user_id=7))
        assert resp.success is True
        data = grpc_loads(resp.data, {}) or {}
        assert data['all'] == 1
        assert data['favorite'] == 1
        assert data['types']['task'] == 1

    def test_grpc_without_params_keeps_full_counts(self):
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        _make_report('INT2339_gRPC_全量A')
        _make_report('INT2339_gRPC_全量B')

        resp = ReportServicer().CountReportsByTabs(
            report_pb.CountReportsByTabsRequest(), context=None)
        data = grpc_loads(resp.data, {}) or {}
        assert data['all'] == 2
        assert data['favorite'] == 0

    def test_grpc_failure_degrades_to_zero_including_new_keys(self, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer
        from report_service.application.handlers.report_handlers import (
            ReportQueryHandler,
        )

        def _boom(self, query):  # pragma: no cover - 触发即降级路径
            raise RuntimeError('db down')

        monkeypatch.setattr(ReportQueryHandler,
                            'handle_count_reports_by_tabs', _boom)

        resp = ReportServicer().CountReportsByTabs(
            report_pb.CountReportsByTabsRequest(search='x'), context=None)
        assert resp.success is False
        data = grpc_loads(resp.data, {}) or {}
        assert data['all'] == data['draft'] == data['published'] == 0
        assert data['comparison'] == data['favorite'] == 0
        assert data['types'] == {'task': 0, 'comparison': 0,
                                 'secondary_comparison': 0, 'benchmark': 0}
