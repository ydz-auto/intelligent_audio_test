# -*- coding: utf-8 -*-
"""INT-791 专项：报告统计分析端点（/reports/statistics*）全链贯通。

覆盖三层：
- report_service StatisticsService：统计聚合（time/task_type/device_type/
  evaluation_metric 四维度）、趋势时间序列、报表文件载荷（csv/excel/pdf/html）
- report_service gRPC servicer：GetStatistics / GetStatisticsTrend /
  GenerateStatisticsReport
- api_gateway：GET /reports/statistics、/reports/statistics/trend、
  POST /reports/statistics/report 路由与参数 schema；并锁定路由顺序
  （/statistics 注册在 /{report_id} 之前，不被捕获返回 422）

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表，
用例内自行清理，对齐 test_int262_report_task_filter.py 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)
from shared.utils.grpc_json import loads as grpc_loads, dumps as grpc_dumps

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


def _make_report(name, created_at=None, status='published', algorithm_type=None,
                 total=10, completed=8, failed=2, pass_rate=80.0, duration=120.0,
                 devices=None, apis=None, dimension_values=None, device_stats=None):
    """创建报告 + 摘要 + 元数据（+ 可选用例行）的完整统计样本。

    SQLite 下 BigInteger 主键不自动递增，子表须显式指定 id。
    """
    from datetime import datetime
    from report_service.infrastructure.persistence.models import (
        Report, ReportSummary, ReportSummaryMeta, ReportCase,
    )
    session = get_db_session()
    try:
        po = Report(name=name, type='task', status=status)
        if created_at is not None:
            po.created_at = created_at
        session.add(po)
        session.flush()

        summary = ReportSummary(
            id=po.id, report_id=po.id, total_cases=total, completed_cases=completed,
            failed_cases=failed, pass_rate=pass_rate, duration=duration)
        session.add(summary)

        meta = ReportSummaryMeta(
            id=po.id, report_id=po.id,
            dimension_values=dimension_values or [],
            devices=devices or [],
            apis=apis or [],
            all_metrics=[{'id': 1, 'name': '清晰度', 'unit': '%', 'sort_order': 0}],
        )
        session.add(meta)

        if algorithm_type:
            session.add(ReportCase(id=po.id * 100, report_id=po.id, test_case_id='c1',
                                   name=name, algorithm_type=algorithm_type))

        session.commit()
        return po.id
    finally:
        remove_db_session()


def _make_metric_stats(report_id, device_stats=None):
    from report_service.infrastructure.persistence.models import ReportMetricStats
    session = get_db_session()
    try:
        po = ReportMetricStats(id=report_id, report_id=report_id,
                               device_stats=device_stats or [])
        session.add(po)
        session.commit()
        return po.id
    finally:
        remove_db_session()


class TestStatisticsService:
    """StatisticsService 聚合计算。"""

    def setup_method(self):
        _ensure_stat_tables()

    def teardown_method(self):
        _cleanup_tables(_STAT_TABLES)

    def test_statistics_time_dimension(self):
        """time 维度：按日期分组，overview/detail/chart 口径正确。"""
        from datetime import datetime
        from report_service.application.services.report_aggregation.statistics_service import (
            statistics_service,
        )
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('r1', created_at=datetime(2026, 10, 1, 10, 0),
                     total=10, completed=9, failed=1, pass_rate=90.0, duration=100)
        _make_report('r2', created_at=datetime(2026, 10, 1, 11, 0),
                     total=20, completed=18, failed=2, pass_rate=90.0, duration=200)
        _make_report('r3', created_at=datetime(2026, 10, 2, 9, 0),
                     total=30, completed=15, failed=15, pass_rate=50.0, duration=300)

        result = statistics_service.get_statistics(
            {'dimension': 'time'}, report_repository)
        # 缺省 dimension=time 合法：返回统计结果而非错误
        assert 'overview' in result and 'detail' in result

        result = statistics_service.get_statistics(
            {'dimension': 'time', 'start_time': '2026-10-01T00:00:00',
             'end_time': '2026-10-01T23:59:59'}, report_repository)
        assert result['overview']['report_count'] == 2
        assert result['overview']['total_cases'] == 30
        assert result['overview']['pass_rate'] == 90.0
        assert result['overview']['completed_reports'] == 2
        dates = [d['group'] for d in result['detail']]
        assert dates == ['2026-10-01']
        assert result['chart']['categories'] == ['2026-10-01']
        assert result['chart']['series'][0]['name'] == '报告数量'

        # 无时间范围 → 全量
        result_all = statistics_service.get_statistics(
            {'dimension': 'time'}, report_repository)
        assert result_all['overview']['report_count'] == 3
        assert len(result_all['detail']) == 2

    def test_statistics_overview_status_semantics(self):
        """overview 状态口径：published 计已完成、draft 不计、无 failed_reports。"""
        from datetime import datetime
        from report_service.application.services.report_aggregation.statistics_service import (
            statistics_service,
        )
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('pub', created_at=datetime(2026, 10, 1), status='published', total=10)
        _make_report('draft', created_at=datetime(2026, 10, 1), status='draft', total=20)

        result = statistics_service.get_statistics(
            {'dimension': 'time'}, report_repository)
        assert result['overview']['report_count'] == 2
        assert result['overview']['completed_reports'] == 1
        assert result['overview']['total_cases'] == 30
        # 报告表无 failed 状态，overview 不含 failed_reports 字段
        assert 'failed_reports' not in result['overview']

    def test_statistics_invalid_dimension(self):
        """dimension 非法值返回错误。"""
        from report_service.application.services.report_aggregation.statistics_service import (
            statistics_service,
        )
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )
        result = statistics_service.get_statistics(
            {'dimension': 'bogus'}, report_repository)
        assert result.get('success') is False
        assert 'dimension' in result.get('message', '')

    def test_statistics_task_type_dimension(self):
        """task_type 维度：api/e2e/mixed 派生。"""
        from datetime import datetime
        from report_service.application.services.report_aggregation.statistics_service import (
            statistics_service,
        )
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('api_only', created_at=datetime(2026, 10, 1),
                     apis=[{'id': 1, 'name': 'api1'}], total=10)
        _make_report('e2e_only', created_at=datetime(2026, 10, 1),
                     devices=[{'id': 1, 'name': 'dev1', 'type': 'phone'}], total=20)
        _make_report('mixed', created_at=datetime(2026, 10, 1),
                     devices=[{'id': 2, 'name': 'dev2', 'type': 'phone'}],
                     apis=[{'id': 3, 'name': 'api3'}], total=30)

        result = statistics_service.get_statistics(
            {'dimension': 'task_type'}, report_repository)
        groups = {d['group']: d for d in result['detail']}
        assert set(groups.keys()) == {'api', 'e2e', 'mixed'}
        assert groups['api']['report_count'] == 1
        assert groups['e2e']['report_count'] == 1
        assert groups['mixed']['report_count'] == 1

    def test_statistics_device_type_dimension(self):
        """device_type 维度：按设备类型分组并统计设备数。"""
        from datetime import datetime
        from report_service.application.services.report_aggregation.statistics_service import (
            statistics_service,
        )
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('r1', created_at=datetime(2026, 10, 1),
                     devices=[{'id': 1, 'name': 'd1', 'type': 'phone'},
                              {'id': 2, 'name': 'd2', 'type': 'speaker'}],
                     total=10)
        _make_report('r2', created_at=datetime(2026, 10, 1),
                     devices=[{'id': 3, 'name': 'd3', 'type': 'phone'}],
                     total=20)

        result = statistics_service.get_statistics(
            {'dimension': 'device_type'}, report_repository)
        groups = {d['group']: d for d in result['detail']}
        assert groups['phone']['report_count'] == 2
        assert groups['phone']['device_count'] == 2
        assert groups['speaker']['report_count'] == 1
        assert groups['speaker']['device_count'] == 1
        assert groups['speaker']['total_cases'] == 10

    def test_statistics_device_type_dedupe_same_type(self):
        """device_type 维度：同报告多台同型设备去重计一次，device_count 收集全部。"""
        from datetime import datetime
        from report_service.application.services.report_aggregation.statistics_service import (
            statistics_service,
        )
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        # 同一报告含 2 台 phone + 1 台 speaker
        _make_report('r1', created_at=datetime(2026, 10, 1), total=10,
                     devices=[{'id': 1, 'name': 'd1', 'type': 'phone'},
                              {'id': 2, 'name': 'd2', 'type': 'phone'},
                              {'id': 3, 'name': 'd3', 'type': 'speaker'}])
        # 另一报告含 1 台 phone
        _make_report('r2', created_at=datetime(2026, 10, 1), total=20,
                     devices=[{'id': 4, 'name': 'd4', 'type': 'phone'}])

        result = statistics_service.get_statistics(
            {'dimension': 'device_type'}, report_repository)
        groups = {d['group']: d for d in result['detail']}
        # 同报告同型去重：phone 组 report_count=2（r1+r2）、total_cases=30 而非 40
        assert groups['phone']['report_count'] == 2
        assert groups['phone']['total_cases'] == 30
        assert groups['phone']['device_count'] == 3  # d1/d2/d4
        assert groups['speaker']['report_count'] == 1
        assert groups['speaker']['total_cases'] == 10
        assert groups['speaker']['device_count'] == 1

    def test_statistics_evaluation_metric_dimension(self):
        """evaluation_metric 维度：按评估指标聚合平均得分。"""
        from datetime import datetime
        from report_service.application.services.report_aggregation.statistics_service import (
            statistics_service,
        )
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('r1', created_at=datetime(2026, 10, 1),
                     dimension_values=[{'id': 1, 'name': '清晰度', 'average_value': 90},
                                       {'id': 2, 'name': '响应速度', 'average_value': 80}])
        _make_report('r2', created_at=datetime(2026, 10, 1),
                     dimension_values=[{'id': 1, 'name': '清晰度', 'average_value': 70}])

        result = statistics_service.get_statistics(
            {'dimension': 'evaluation_metric'}, report_repository)
        metrics = {d['metric']: d for d in result['detail']}
        assert metrics['清晰度']['report_count'] == 2
        assert metrics['清晰度']['average_value'] == 80.0
        assert metrics['清晰度']['min'] == 70.0
        assert metrics['清晰度']['max'] == 90.0
        assert metrics['响应速度']['average_value'] == 80.0
        assert result['chart']['series'][0]['name'] == '平均得分'

    def test_statistics_algorithm_type_filter(self):
        """algorithm_type 过滤：按 report_cases.algorithm_type 存在性。"""
        from datetime import datetime
        from report_service.application.services.report_aggregation.statistics_service import (
            statistics_service,
        )
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('algo_a', created_at=datetime(2026, 10, 1), algorithm_type='algoA')
        _make_report('algo_b', created_at=datetime(2026, 10, 1), algorithm_type='algoB')

        result = statistics_service.get_statistics(
            {'dimension': 'time', 'algorithm_type': 'algoA'}, report_repository)
        assert result['overview']['report_count'] == 1

        result_all = statistics_service.get_statistics(
            {'dimension': 'time'}, report_repository)
        assert result_all['overview']['report_count'] == 2

    def test_anomaly_detection(self):
        """异常统计识别：无用例 / 通过率偏低 / 数据异常。"""
        from datetime import datetime
        from report_service.application.services.report_aggregation.statistics_service import (
            statistics_service,
        )
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('empty', created_at=datetime(2026, 10, 1), total=0)
        _make_report('low_pass', created_at=datetime(2026, 10, 1),
                     total=10, completed=2, failed=8, pass_rate=20.0)
        _make_report('bad_data', created_at=datetime(2026, 10, 1),
                     total=10, completed=5, failed=5, pass_rate=120.0)

        result = statistics_service.get_statistics(
            {'dimension': 'time'}, report_repository)
        types = {a['type'] for a in result['anomaly']}
        assert 'no_cases' in types
        assert 'low_pass_rate' in types
        assert 'data_error' in types

    def test_trend_time(self):
        """time 趋势：按日期序列。"""
        from datetime import datetime
        from report_service.application.services.report_aggregation.statistics_service import (
            statistics_service,
        )
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('r1', created_at=datetime(2026, 10, 1), total=10, pass_rate=90.0)
        _make_report('r2', created_at=datetime(2026, 10, 2), total=20, pass_rate=50.0)

        result = statistics_service.get_trend(
            {'trend_type': 'time'}, report_repository)
        assert result['trend_type'] == 'time'
        assert [p['date'] for p in result['time_trend']] == ['2026-10-01', '2026-10-02']
        assert result['time_trend'][0]['report_count'] == 1
        assert result['time_trend'][0]['pass_rate'] == 90.0
        assert result['dimension_trend'] == []

    def test_trend_dimension(self):
        """dimension 趋势：按评估指标展开时间序列。"""
        from datetime import datetime
        from report_service.application.services.report_aggregation.statistics_service import (
            statistics_service,
        )
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('r1', created_at=datetime(2026, 10, 1),
                     dimension_values=[{'id': 1, 'name': '清晰度', 'average_value': 90}])
        _make_report('r2', created_at=datetime(2026, 10, 2),
                     dimension_values=[{'id': 1, 'name': '清晰度', 'average_value': 70}])

        result = statistics_service.get_trend(
            {'trend_type': 'dimension', 'metric': '清晰度'}, report_repository)
        assert result['trend_type'] == 'dimension'
        assert result['metric'] == '清晰度'
        assert len(result['dimension_trend']) == 1
        assert result['dimension_trend'][0]['metric'] == '清晰度'
        points = result['dimension_trend'][0]['points']
        assert [p['date'] for p in points] == ['2026-10-01', '2026-10-02']
        assert points[0]['value'] == 90.0

    def test_trend_invalid_type(self):
        from report_service.application.services.report_aggregation.statistics_service import (
            statistics_service,
        )
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )
        result = statistics_service.get_trend(
            {'trend_type': 'bogus'}, report_repository)
        assert result.get('success') is False

    def test_generate_report_csv(self):
        """报表生成：csv 载荷结构。"""
        from datetime import datetime
        from report_service.application.services.report_aggregation.statistics_service import (
            statistics_service,
        )
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('r1', created_at=datetime(2026, 10, 1), total=10, pass_rate=90.0)
        result = statistics_service.generate_report(
            {'report_type': 'case_execution', 'format': 'csv',
             'time_range': {'start_time': '2026-10-01', 'end_time': '2026-10-31'}},
            report_repository)
        assert result['content_base64']
        assert result['format'] == 'csv'
        assert result['filename'].endswith('.csv')
        assert result['mime_type'] == 'text/csv'

    def test_generate_report_html_and_excel(self):
        """报表生成：html/excel 载荷。"""
        from datetime import datetime
        from report_service.application.services.report_aggregation.statistics_service import (
            statistics_service,
        )
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_report('r1', created_at=datetime(2026, 10, 1), total=10)
        result_html = statistics_service.generate_report(
            {'report_type': 'report_count', 'format': 'html'}, report_repository)
        assert result_html['format'] == 'html'
        assert result_html['mime_type'] == 'text/html'

        result_excel = statistics_service.generate_report(
            {'report_type': 'report_count', 'format': 'excel'}, report_repository)
        assert result_excel['format'] == 'excel'
        assert result_excel['filename'].endswith('.xlsx')

    def test_generate_report_device_performance(self):
        """报表生成：device_performance 走 device_stats 快照。"""
        from datetime import datetime
        from report_service.application.services.report_aggregation.statistics_service import (
            statistics_service,
        )
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        rid = _make_report('r1', created_at=datetime(2026, 10, 1), total=10)
        _make_metric_stats(rid, device_stats=[
            {'id': 1, 'name': 'dev1', 'type': 'phone', 'model': 'M1',
             'total_cases': 6, 'completed_cases': 6, 'failed_cases': 0,
             'success_rate': 100.0},
        ])
        result = statistics_service.generate_report(
            {'report_type': 'device_performance', 'format': 'csv'}, report_repository)
        import base64
        csv_text = base64.b64decode(result['content_base64']).decode('utf-8-sig')
        assert '设备名称' in csv_text
        assert 'dev1' in csv_text

    def test_generate_report_invalid_params(self):
        from report_service.application.services.report_aggregation.statistics_service import (
            statistics_service,
        )
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )
        assert statistics_service.generate_report(
            {'report_type': 'bogus'}, report_repository).get('success') is False
        assert statistics_service.generate_report(
            {'report_type': 'report_count', 'format': 'bogus'},
            report_repository).get('success') is False


class TestStatisticsServicer:
    """gRPC servicer：三新 RPC 透传。"""

    def setup_method(self):
        _ensure_stat_tables()

    def teardown_method(self):
        _cleanup_tables(_STAT_TABLES)

    def test_get_statistics_servicer(self):
        """GetStatistics RPC 返回统一信封。"""
        from datetime import datetime
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        _make_report('r1', created_at=datetime(2026, 10, 1), total=10)

        resp = ReportServicer().GetStatistics(
            report_pb.GetStatisticsRequest(
                data=grpc_dumps({'dimension': 'time'})), context=None)
        assert resp.success is True
        data = grpc_loads(resp.data, {}) or {}
        assert data['overview']['report_count'] == 1
        assert 'detail' in data and 'chart' in data and 'anomaly' in data

    def test_get_statistics_servicer_invalid(self):
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer
        resp = ReportServicer().GetStatistics(
            report_pb.GetStatisticsRequest(
                data=grpc_dumps({'dimension': 'bogus'})), context=None)
        assert resp.success is False

    def test_get_statistics_trend_servicer(self):
        from datetime import datetime
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        _make_report('r1', created_at=datetime(2026, 10, 1), total=10)
        resp = ReportServicer().GetStatisticsTrend(
            report_pb.GetStatisticsTrendRequest(
                data=grpc_dumps({'trend_type': 'time'})), context=None)
        assert resp.success is True
        data = grpc_loads(resp.data, {}) or {}
        assert len(data['time_trend']) == 1

    def test_generate_statistics_report_servicer(self):
        from datetime import datetime
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        _make_report('r1', created_at=datetime(2026, 10, 1), total=10)
        resp = ReportServicer().GenerateStatisticsReport(
            report_pb.GenerateStatisticsReportRequest(
                data=grpc_dumps({'report_type': 'report_count', 'format': 'csv'})),
            context=None)
        assert resp.success is True
        data = grpc_loads(resp.data, {}) or {}
        assert data.get('content_base64')


class _FakeStub:
    """report_config_service.stub 桩：记录请求并返回预设响应。"""

    def __init__(self, resp=None):
        self.resp = resp
        self.calls = []

    def GetStatistics(self, req):
        self.calls.append(req)
        return self.resp

    def GetStatisticsTrend(self, req):
        self.calls.append(req)
        return self.resp

    def GenerateStatisticsReport(self, req):
        self.calls.append(req)
        return self.resp


def _install_fake_stub(monkeypatch, resp):
    from api_gateway.infrastructure.grpc_proxies import report_proxies
    fake = _FakeStub(resp)
    monkeypatch.setattr(report_proxies, 'get_report_config_service_stub',
                        lambda: fake)
    return fake


@pytest.fixture()
def gw_client():
    """挂载真实 report_bp 路由的迷你网关（注入 admin 权限 + 请求适配中间件）。"""
    from api_gateway.routes.report_bp import router as report_router
    from api_gateway.middleware import RequestAdapterMiddleware

    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _inject_permissions(request, call_next):
        request.state.permissions = ['*']
        return await call_next(request)

    app.include_router(report_router, prefix='/api/v1/reports')
    return TestClient(app, raise_server_exceptions=False)


class TestGatewayStatisticsRoutes:
    """api_gateway：三端点路由 + schema + 二进制下载 + 路由顺序。"""

    def test_get_statistics_route(self, gw_client, monkeypatch):
        """GET /reports/statistics → gRPC 透传 + 统一信封。"""
        from shared.proto import report_service_pb2 as report_pb

        stats_data = {
            'dimension': 'time',
            'overview': {'report_count': 2},
            'detail': [{'group': '2026-10-01', 'report_count': 2}],
            'chart': {'categories': ['2026-10-01'], 'series': []},
            'anomaly': [],
        }
        resp = report_pb.ReportConfigResponse(
            success=True, message='ok', data=grpc_dumps(stats_data))
        fake = _install_fake_stub(monkeypatch, resp)

        r = gw_client.get('/api/v1/reports/statistics',
                          params={'dimension': 'time', 'start_time': '2026-10-01'})
        assert r.status_code == 200
        assert fake.calls and fake.calls[0].data
        body = r.json()
        assert body['success'] is True
        assert body['data']['dimension'] == 'time'
        assert body['data']['overview']['report_count'] == 2

    def test_get_statistics_not_captured_by_report_id(self, gw_client, monkeypatch):
        """路由顺序：/statistics 不被 /{report_id} 捕获（返回 200 而非 422）。"""
        from shared.proto import report_service_pb2 as report_pb

        resp = report_pb.ReportConfigResponse(
            success=True, message='ok',
            data=grpc_dumps({'dimension': 'time', 'overview': {}, 'detail': [],
                             'chart': {}, 'anomaly': []}))
        _install_fake_stub(monkeypatch, resp)

        r = gw_client.get('/api/v1/reports/statistics')
        assert r.status_code == 200
        assert r.json()['success'] is True

    def test_get_statistics_trend_route(self, gw_client, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb

        trend_data = {'trend_type': 'time', 'time_trend': [{'date': '2026-10-01',
                                                            'report_count': 1}],
                      'dimension_trend': []}
        resp = report_pb.ReportConfigResponse(
            success=True, message='ok', data=grpc_dumps(trend_data))
        fake = _install_fake_stub(monkeypatch, resp)

        r = gw_client.get('/api/v1/reports/statistics/trend',
                          params={'trend_type': 'time'})
        assert r.status_code == 200
        assert fake.calls and fake.calls[0].data
        assert r.json()['data']['time_trend'][0]['report_count'] == 1

    def test_generate_statistics_report_route_binary(self, gw_client, monkeypatch):
        """POST /reports/statistics/report → binary 下载响应。"""
        import base64 as b64
        from shared.proto import report_service_pb2 as report_pb

        csv_bytes = '﻿日期,报告数量\n2026-10-01,1\n'.encode('utf-8')
        resp = report_pb.ReportConfigResponse(
            success=True, message='ok', data=grpc_dumps({
                'filename': 'statistics_report_20261001.csv',
                'format': 'csv',
                'content_base64': b64.b64encode(csv_bytes).decode(),
                'mime_type': 'text/csv',
            }))
        fake = _install_fake_stub(monkeypatch, resp)

        r = gw_client.post('/api/v1/reports/statistics/report',
                           json={'report_type': 'report_count', 'format': 'csv'})
        assert r.status_code == 200
        assert fake.calls and fake.calls[0].data
        assert r.headers['content-type'].startswith('text/csv')
        assert 'attachment' in r.headers.get('content-disposition', '')
        assert '报告数量' in r.content.decode('utf-8-sig')

    def test_generate_statistics_report_schema_validation(self, gw_client, monkeypatch):
        """schema 校验：time_range 非法类型 → 400。"""
        from shared.proto import report_service_pb2 as report_pb
        _install_fake_stub(monkeypatch, report_pb.ReportConfigResponse(
            success=True, message='ok', data='{}'))

        r = gw_client.post('/api/v1/reports/statistics/report',
                           json={'report_type': 'report_count',
                                 'format': 'csv', 'time_range': 'invalid'})
        # time_range=字符串不可强转为对象 → schema 校验失败 → 400
        assert r.status_code == 400
        assert r.json()['success'] is False
