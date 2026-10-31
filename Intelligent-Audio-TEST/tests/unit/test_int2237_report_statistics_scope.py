# -*- coding: utf-8 -*-
"""INT-2237 专项：报告统计聚合的行级可见性 / 默认时间窗 / 服务端上限。

验收口径（对齐原卡）：
1. 造 1 条他人私有报告 → 非 owner 的统计值不包含它；admin 口径不变
2. 无时间参数时默认窗生效（近 REPORT_STATISTICS_DEFAULT_WINDOW_DAYS 天）
3. 基础行超过服务端上限 → 显式报错（绝不静默截断成部分聚合）
4. 三入口（统计 / 趋势 / 报表生成）同口径，均走 get_statistics_rows

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表，
用例内自行清理（对齐 test_int791_report_statistics.py）。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.infrastructure.user_context import (
    set_current_user_id,
    set_current_user_is_admin,
)
from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)

USER_A = 1001
USER_B = 1002

_STAT_TABLES = None


def _ensure_stat_tables():
    init_db(pool_size=2)
    global _STAT_TABLES
    if _STAT_TABLES is None:
        from report_service.infrastructure.persistence.models import (
            Report, ReportSummary, ReportSummaryMeta, ReportMetricStats, ReportCase,
        )
        _STAT_TABLES = [t.__table__ for t in (
            Report, ReportSummary, ReportSummaryMeta, ReportMetricStats, ReportCase,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_STAT_TABLES)
    return _STAT_TABLES


def _cleanup_tables(tables):
    session = get_db_session()
    try:
        for table in tables:
            session.execute(table.delete())
        session.commit()
    finally:
        remove_db_session()


@pytest.fixture(autouse=True)
def _clean_user_context():
    """每个用例前后清空 user context（防跨用例串号）。"""
    set_current_user_id(None)
    set_current_user_is_admin(False)
    yield
    set_current_user_id(None)
    set_current_user_is_admin(False)


def _make_report(name, created_by=None, visibility='shared', created_at=None,
                 total=10, completed=8, failed=2, pass_rate=80.0, duration=120.0,
                 status='published'):
    """创建报告 + 摘要基础样本（SQLite 下 BigInteger 主键不自增，显式给子表 id）。"""
    from report_service.infrastructure.persistence.models import (
        Report, ReportSummary, ReportSummaryMeta,
    )
    session = get_db_session()
    try:
        po = Report(name=name, type='task', status=status,
                    created_by_user_id=created_by, visibility=visibility)
        if created_at is not None:
            po.created_at = created_at
        session.add(po)
        session.flush()

        session.add(ReportSummary(
            id=po.id, report_id=po.id, total_cases=total, completed_cases=completed,
            failed_cases=failed, pass_rate=pass_rate, duration=duration))
        session.add(ReportSummaryMeta(
            id=po.id, report_id=po.id, dimension_values=[], devices=[], apis=[],
            all_metrics=[]))
        session.commit()
        return po.id
    finally:
        remove_db_session()


def _statistics(repository, **params):
    from report_service.application.services.report_aggregation.statistics_service import (
        statistics_service,
    )
    return statistics_service.get_statistics(params, repository)


def _trend(repository, **params):
    from report_service.application.services.report_aggregation.statistics_service import (
        statistics_service,
    )
    return statistics_service.get_trend(params, repository)


def _generate(repository, **params):
    from report_service.application.services.report_aggregation.statistics_service import (
        statistics_service,
    )
    return statistics_service.generate_report(params, repository)


@pytest.fixture()
def repo():
    from report_service.infrastructure.persistence.report_repository import (
        report_repository,
    )
    return report_repository


class TestStatisticsVisibility:
    """验收①：私有报告不并入非 owner 统计；owner / admin 口径不变。"""

    def setup_method(self):
        _ensure_stat_tables()

    def teardown_method(self):
        _cleanup_tables(_STAT_TABLES)

    def test_private_report_excluded_from_non_owner_statistics(self, repo):
        """非 owner 的 overview/detail 不含他人私有报告；共享报告照常计入。"""
        # 私有报告故意造成异常样本（通过率偏低），用于核对 anomaly 也按可见性过滤
        _make_report('A私有报告', USER_A, 'private', total=10,
                     completed=2, failed=8, pass_rate=20.0)
        _make_report('B共享报告', USER_B, 'shared', total=20)

        # 非 owner（USER_B）视角：只看到共享报告（total_cases=20）
        set_current_user_id(USER_B)
        result = _statistics(repo, dimension='time')
        assert result['overview']['report_count'] == 1
        assert result['overview']['total_cases'] == 20
        names_b = {a.get('report_name') for a in result['anomaly']}
        assert 'A私有报告' not in names_b

        # owner（USER_A）视角：自己的私有报告计入（+共享 = 2 条），异常也可见
        set_current_user_id(USER_A)
        result_a = _statistics(repo, dimension='time')
        assert result_a['overview']['report_count'] == 2
        assert result_a['overview']['total_cases'] == 30
        assert 'A私有报告' in {a.get('report_name') for a in result_a['anomaly']}

        # 未认证（guest）视角：仅 shared
        set_current_user_id(None)
        assert _statistics(repo, dimension='time')['overview']['report_count'] == 1

        # admin 口径不变：两条都在
        set_current_user_id(USER_B)
        set_current_user_is_admin(True)
        result_admin = _statistics(repo, dimension='time')
        assert result_admin['overview']['report_count'] == 2
        assert result_admin['overview']['total_cases'] == 30

    def test_trend_and_report_generation_share_visibility(self, repo):
        """趋势 / 报表生成同口径：私有报告不进非 owner 结果。"""
        _make_report('A私有报告', USER_A, 'private', total=10)
        _make_report('B共享报告', USER_B, 'shared', total=20)

        set_current_user_id(USER_B)
        trend = _trend(repo, trend_type='time')
        points = trend['time_trend']
        assert sum(p['report_count'] for p in points) == 1
        assert sum(p['total_cases'] for p in points) == 20

        # 报表生成：同一日期分组只计 1 条报告（私有报告被过滤）
        payload = _generate(repo, report_type='report_count', format='csv')
        import base64
        csv_text = base64.b64decode(payload['content_base64']).decode('utf-8-sig')
        data_lines = [ln for ln in csv_text.strip().splitlines()[1:] if ln.strip()]
        assert len(data_lines) == 1
        assert data_lines[0].split(',')[1] == '1'  # 报告数量 = 1


class TestStatisticsDefaultWindow:
    """验收②：无时间参数时默认窗生效，窗口外报告不计入。"""

    def setup_method(self):
        _ensure_stat_tables()

    def teardown_method(self):
        _cleanup_tables(_STAT_TABLES)

    def test_default_window_excludes_old_reports(self, repo):
        from datetime import datetime, timedelta

        from report_service.application.services.report_aggregation.statistics_service import (
            _default_window_start,
        )
        from shared.infrastructure.config import BaseConfig

        days = int(BaseConfig.REPORT_STATISTICS_DEFAULT_WINDOW_DAYS)
        assert days > 0  # 默认配置必须开启窗口（INT-2237）

        window_start = _default_window_start(days)
        fresh = datetime.now() - timedelta(days=1)
        stale = window_start - timedelta(days=1)

        _make_report('近窗内', USER_A, 'shared', created_at=fresh, total=10)
        _make_report('窗口外', USER_A, 'shared', created_at=stale, total=20)

        # 无时间参数 → 默认窗生效，只统计窗内报告，并回显生效窗口
        set_current_user_id(USER_A)
        result = _statistics(repo, dimension='time')
        assert result['overview']['report_count'] == 1
        assert result['overview']['total_cases'] == 10
        echoed = result['time_range']
        assert echoed['start_time'] is not None
        echoed_start = datetime.fromisoformat(echoed['start_time'])
        assert abs((echoed_start - window_start).total_seconds()) < 60
        assert echoed['end_time'] is None

        # 显式给更早的 start_time → 窗口外报告重新计入（窗口可覆盖）
        explicit_start = (window_start - timedelta(days=400)).isoformat()
        result_all = _statistics(repo, dimension='time', start_time=explicit_start)
        assert result_all['overview']['report_count'] == 2
        assert datetime.fromisoformat(
            result_all['time_range']['start_time']) == datetime.fromisoformat(
            explicit_start)

    def test_trend_respects_default_window(self, repo):
        from datetime import datetime, timedelta

        from report_service.application.services.report_aggregation.statistics_service import (
            _default_window_start,
        )
        from shared.infrastructure.config import BaseConfig

        window_start = _default_window_start(
            int(BaseConfig.REPORT_STATISTICS_DEFAULT_WINDOW_DAYS))
        _make_report('近窗内', USER_A, 'shared',
                     created_at=datetime.now() - timedelta(days=1))
        _make_report('窗口外', USER_A, 'shared',
                     created_at=window_start - timedelta(days=1))

        set_current_user_id(USER_A)
        trend = _trend(repo, trend_type='time')
        assert sum(p['report_count'] for p in trend['time_trend']) == 1
        assert trend['time_range']['start_time'] is not None


class TestStatisticsRowCap:
    """验收③：基础行超服务端上限 → 显式报错，不静默截断。"""

    def setup_method(self):
        _ensure_stat_tables()

    def teardown_method(self):
        _cleanup_tables(_STAT_TABLES)

    @pytest.fixture(autouse=True)
    def _small_cap(self, monkeypatch):
        from shared.infrastructure.config import BaseConfig
        monkeypatch.setattr(BaseConfig, 'REPORT_STATISTICS_MAX_ROWS', 1)

    def test_over_limit_returns_explicit_error(self, repo):
        _make_report('r1', USER_A, 'shared')
        _make_report('r2', USER_A, 'shared')

        set_current_user_id(USER_A)
        result = _statistics(repo, dimension='time')
        assert result.get('success') is False
        assert result.get('code') == 400
        assert '统计范围过大' in result.get('message', '')

        trend = _trend(repo, trend_type='time')
        assert trend.get('success') is False
        assert '统计范围过大' in trend.get('message', '')

        generated = _generate(repo, report_type='report_count', format='csv')
        assert generated.get('success') is False
        assert '统计范围过大' in generated.get('message', '')

    def test_under_limit_returns_full_aggregation(self, repo):
        _make_report('r1', USER_A, 'shared', total=10)
        set_current_user_id(USER_A)
        result = _statistics(repo, dimension='time')
        assert result.get('success') is not False
        assert result['overview']['report_count'] == 1
        assert result['overview']['total_cases'] == 10
