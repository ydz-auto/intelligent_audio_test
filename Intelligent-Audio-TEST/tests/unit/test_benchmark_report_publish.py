# -*- coding: utf-8 -*-
"""Benchmark 报告发布单测（INT-481：第五表 + 发布/查询端点）

覆盖：
- 发布成功：聚合排行快照 → 复用报告 7 表结构建主记录 → benchmark_reports 落库，
  快照计数（published_task_count / subject_count / metric_count）正确
- 版本递增：同 suite/category 下发布版本号 = 既有最大版本 + 1
- 校验：非法类别 / 非法双轨来源 / 非整数 task_id 拒绝，不建报告记录
- 失败回滚：快照落库失败时删除已建的报告主记录（避免半成品）
- 查询侧：列表分页筛选 + 详情（存在 / 404），严格 CQRS 只读
- 真仓储（SQLite）：发布 → 列表/详情闭环，排行快照与排行 ReadModel 一致
"""
import os
import tempfile
from datetime import datetime
from types import SimpleNamespace

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    return 'INTEGER'


import report_service.infrastructure.persistence.models  # noqa: F401  注册 benchmark_reports / report 表
import report_service.application.services.benchmark_report_service as report_svc_mod
import shared.models.database as database
from report_service.application.commands.benchmark_commands import (
    CreateBenchmarkReportCommand,
)
from report_service.application.queries.benchmark_queries import (
    GetBenchmarkReportQuery,
    ListBenchmarkReportsQuery,
)
from report_service.application.services.benchmark_report_service import (
    BenchmarkReportService,
)
from report_service.application.handlers.benchmark_handlers import (
    BenchmarkCommandHandler,
    BenchmarkQueryHandler,
)
from report_service.infrastructure.persistence.benchmark_repository import (
    BenchmarkRepositoryImpl,
)


@pytest.fixture(autouse=True)
def _no_audit_and_event(monkeypatch):
    monkeypatch.setattr(report_svc_mod, 'write_benchmark_audit', lambda *a, **k: None)
    monkeypatch.setattr(report_svc_mod, '_emit_report_event', lambda *a, **k: None)


# ==================== Fake 仓储替身（服务层单测） ====================

class FakeBenchmarkRepo:
    """Benchmark 仓储替身：排行 ReadModel + 报告发布记录内存版。"""

    def __init__(self, ranking_rows=None):
        self.ranking_rows = ranking_rows or []
        self.reports = []
        self.next_id = 1
        self.max_versions = {}  # (suite, category) → max version

    def query_rankings(self, filters):
        rows = self.ranking_rows
        if filters.get('suite'):
            rows = [r for r in rows if r['benchmark_suite'] == filters['suite']]
        if filters.get('category'):
            rows = [r for r in rows if r['category'] == filters['category']]
        if filters.get('source'):
            rows = [r for r in rows if r['source'] == filters['source']]
        return list(rows)

    def max_benchmark_report_version(self, suite='', category=''):
        return self.max_versions.get((suite, category), 0)

    def insert_benchmark_report(self, data):
        record = dict(data)
        record['id'] = self.next_id
        self.next_id += 1
        self.reports.append(record)
        key = (data.get('suite') or '', data.get('category') or '')
        self.max_versions[key] = max(self.max_versions.get(key, 0), int(data.get('version') or 1))
        return record

    def list_benchmark_reports(self, filters, page, per_page):
        rows = self.reports
        if filters.get('suite'):
            rows = [r for r in rows if r['suite'] == filters['suite']]
        if filters.get('category'):
            rows = [r for r in rows if r['category'] == filters['category']]
        if filters.get('source'):
            rows = [r for r in rows if r['source'] == filters['source']]
        if filters.get('task_id') is not None:
            rows = [r for r in rows if r.get('task_id') == int(filters['task_id'])]
        total = len(rows)
        start = (page - 1) * per_page
        items = [
            {k: v for k, v in r.items() if k != 'ranking_data'}
            for r in rows[start:start + per_page]
        ]
        return {'items': items, 'total': total, 'page': page, 'per_page': per_page,
                'pages': (total + per_page - 1) // per_page if total else 0}

    def get_benchmark_report(self, report_id):
        for r in self.reports:
            if r['id'] == report_id:
                return dict(r)
        return None


class FakeReportRepo:
    """报告仓储替身：聚合根 add / add_summary / hard_delete。"""

    def __init__(self):
        self.aggregates = {}
        self.summaries = {}
        self.deleted = []
        self.next_id = 1

    def add(self, aggregate):
        aggregate.id = self.next_id
        self.next_id += 1
        self.aggregates[aggregate.id] = aggregate
        return aggregate.id

    def add_summary(self, report_id, summary_data):
        self.summaries[report_id] = dict(summary_data)
        return report_id

    def hard_delete(self, report_id):
        if report_id in self.aggregates:
            self.deleted.append(report_id)
            self.aggregates.pop(report_id)
            return True
        return False


def _rank_row(subject, metric='WER', category='asr', suite='librispeech-v1',
              source='platform_test', pt_id=1, value=5.0):
    return {
        'source': source, 'published_task_id': pt_id, 'published_task_version': 1,
        'report_id': (100 + pt_id) if pt_id is not None else None,
        'baseline_id': None, 'subject_name': subject,
        'subject_type': 'app', 'device_type': 'physical', 'benchmark_suite': suite,
        'category': category, 'metric_code': metric, 'metric_name': metric,
        'metric_value': value, 'unit': '%', 'direction': 'lower_is_better',
        'rank': 1, 'total': 1, 'percentile': 100.0, 'score100': None,
        'gap_best': 0.0, 'gap_median': 0.0, 'delta_external': None,
        'scenario_key': '通用', 'computed_at': datetime(2026, 10, 16, 0, 0, 0),
    }


class TestPublish:
    def test_publish_creates_report_and_snapshot(self):
        repo = FakeBenchmarkRepo(ranking_rows=[
            _rank_row('Moshi', category='voice_llm', suite='full-duplex-v1', pt_id=1),
            _rank_row('Whisper', metric='CER', category='voice_llm', suite='full-duplex-v1', pt_id=2),
            _rank_row('Moshi', source='external_import', category='voice_llm', suite='full-duplex-v1', pt_id=None, value=6.0),
        ])
        report_repo = FakeReportRepo()
        svc = BenchmarkReportService(repo=repo, report_repo=report_repo)
        result = svc.publish(CreateBenchmarkReportCommand(
            suite='full-duplex-v1', category='voice_llm', name='Q3 Benchmark', published_by='tester'))

        assert result['success'] is True
        assert result['code'] == 0
        record = result['data']
        assert record['report_id'] == 1  # 报告主记录 ID
        assert record['suite'] == 'full-duplex-v1'
        assert record['category'] == 'voice_llm'
        assert record['version'] == 1
        assert record['published_by'] == 'tester'
        # 计数：2 个正式任务（Moshi pt_id=1, Whisper pt_id=2；外部轨无 pt_id）
        assert record['published_task_count'] == 2
        # 主体：Moshi / Whisper（双轨同一主体去重）
        assert record['subject_count'] == 2
        # 指标：WER / CER
        assert record['metric_count'] == 2
        # 快照与排行 ReadModel 一致
        snapshot = record['ranking_data']
        assert snapshot['filters'] == {'suite': 'full-duplex-v1', 'category': 'voice_llm', 'source': ''}
        assert snapshot['counts']['row_count'] == 3
        assert snapshot['counts']['published_task_count'] == 2
        assert len(snapshot['rows']) == 3

        # 报告主记录：复用报告 7 表结构（report_type='benchmark'，状态 published）
        agg = report_repo.aggregates[record['report_id']]
        assert agg.report_type == 'benchmark'
        assert agg.status == 'published'
        assert agg.name == 'Q3 Benchmark'
        # 摘要快照已写入
        assert report_repo.summaries[record['report_id']]['task_ids'] is None

    def test_publish_filters_rows_by_request(self):
        repo = FakeBenchmarkRepo(ranking_rows=[
            _rank_row('Moshi', category='voice_llm', suite='full-duplex-v1', pt_id=1),
            _rank_row('Nova', category='asr', suite='librispeech-v1', pt_id=2),
        ])
        svc = BenchmarkReportService(repo=repo, report_repo=FakeReportRepo())
        result = svc.publish(CreateBenchmarkReportCommand(
            suite='librispeech-v1', category='asr'))
        assert result['success'] is True
        record = result['data']
        assert record['published_task_count'] == 1
        assert record['subject_count'] == 1
        assert record['ranking_data']['rows'][0]['subject_name'] == 'Nova'

    def test_version_increments_per_suite_category(self):
        repo = FakeBenchmarkRepo(ranking_rows=[_rank_row('Moshi', category='asr', suite='s1', pt_id=1)])
        svc = BenchmarkReportService(repo=repo, report_repo=FakeReportRepo())
        first = svc.publish(CreateBenchmarkReportCommand(suite='s1', category='asr'))
        assert first['data']['version'] == 1
        second = svc.publish(CreateBenchmarkReportCommand(suite='s1', category='asr'))
        assert second['data']['version'] == 2
        # 不同 suite/category 独立版本序列
        other = svc.publish(CreateBenchmarkReportCommand(suite='s2', category='asr'))
        assert other['data']['version'] == 1

    def test_publish_default_name_when_unnamed(self):
        svc = BenchmarkReportService(repo=FakeBenchmarkRepo(), report_repo=FakeReportRepo())
        result = svc.publish(CreateBenchmarkReportCommand(suite='s1', category='asr'))
        assert result['success'] is True
        assert result['data']['report_id'] == 1
        # 未命名自动生成，含 suite/category
        agg = svc.report_repo.aggregates[1]
        assert agg.name.startswith('Benchmark报告_s1_asr_')


class TestPublishValidation:
    def test_invalid_category_rejected_no_report_created(self):
        report_repo = FakeReportRepo()
        svc = BenchmarkReportService(repo=FakeBenchmarkRepo(), report_repo=report_repo)
        result = svc.publish(CreateBenchmarkReportCommand(category='weibo'))
        assert result['success'] is False
        assert result['code'] == 100
        assert report_repo.aggregates == {}

    def test_invalid_source_rejected(self):
        report_repo = FakeReportRepo()
        svc = BenchmarkReportService(repo=FakeBenchmarkRepo(), report_repo=report_repo)
        result = svc.publish(CreateBenchmarkReportCommand(source='weibo'))
        assert result['success'] is False
        assert result['code'] == 101
        assert report_repo.aggregates == {}

    def test_non_integer_task_id_rejected(self):
        report_repo = FakeReportRepo()
        svc = BenchmarkReportService(repo=FakeBenchmarkRepo(), report_repo=report_repo)
        result = svc.publish(CreateBenchmarkReportCommand(task_id='abc'))
        assert result['success'] is False
        assert result['code'] == 102
        assert report_repo.aggregates == {}


class TestPublishRollback:
    def test_snapshot_failure_deletes_report_record(self):
        class _FailingBenchmarkRepo(FakeBenchmarkRepo):
            def insert_benchmark_report(self, data):
                raise RuntimeError('db down')

        report_repo = FakeReportRepo()
        svc = BenchmarkReportService(repo=_FailingBenchmarkRepo(ranking_rows=[_rank_row('Moshi', pt_id=1)]),
                                     report_repo=report_repo)
        result = svc.publish(CreateBenchmarkReportCommand())
        assert result['success'] is False
        assert result['code'] == 301
        # 半成品报告主记录已回滚删除
        assert report_repo.aggregates == {}
        assert report_repo.deleted == [1]


# ==================== 查询侧（严格 CQRS 只读） ====================

class TestQueryHandlers:
    def test_list_reports_paginated(self):
        repo = FakeBenchmarkRepo()
        repo.insert_benchmark_report({'report_id': 1, 'suite': 's1', 'category': 'asr',
                                      'ranking_data': {'rows': []}, 'version': 1})
        repo.insert_benchmark_report({'report_id': 2, 'suite': 's2', 'category': 'tts',
                                      'ranking_data': {'rows': []}, 'version': 1})
        handler = BenchmarkQueryHandler(repo=repo)
        result = handler.handle_list_reports(ListBenchmarkReportsQuery(category='asr'))
        assert result['success'] is True
        data = result['data']
        assert data['total'] == 1
        assert data['items'][0]['suite'] == 's1'
        # 列表不携带排行快照（大体积字段）
        assert 'ranking_data' not in data['items'][0]

    def test_get_report_detail_and_not_found(self):
        repo = FakeBenchmarkRepo()
        repo.insert_benchmark_report({'report_id': 1, 'suite': 's1', 'category': 'asr',
                                      'ranking_data': {'rows': [{'subject_name': 'Moshi'}]},
                                      'version': 1})
        handler = BenchmarkQueryHandler(repo=repo)
        ok = handler.handle_get_report(GetBenchmarkReportQuery(report_id=1))
        assert ok['success'] is True
        assert ok['data']['ranking_data']['rows'][0]['subject_name'] == 'Moshi'
        missing = handler.handle_get_report(GetBenchmarkReportQuery(report_id=999))
        assert missing['success'] is False
        assert missing['code'] == 404

    def test_query_side_no_write(self):
        repo = FakeBenchmarkRepo()
        handler = BenchmarkQueryHandler(repo=repo)
        handler.handle_list_reports(ListBenchmarkReportsQuery())
        handler.handle_get_report(GetBenchmarkReportQuery(report_id=1))
        assert repo.reports == []  # 查询不产生任何写副作用


# ==================== 真仓储（SQLite）发布闭环 ====================

@pytest.fixture()
def sqlite_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    engine = create_engine(f'sqlite:///{path}',
                           connect_args={'check_same_thread': False})
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(engine)
    yield database
    database.remove_db_session()
    engine.dispose()
    os.remove(path)


class TestRealRepoPublishChain:
    def test_publish_list_detail_roundtrip(self, sqlite_db):
        repo = BenchmarkRepositoryImpl()
        # 预置排行 ReadModel
        repo.replace_ranking_rows(
            [{'category': 'asr', 'metric_code': 'WER', 'scenario_key': '通用',
              'source': 'platform_test'}],
            [_rank_row('Moshi', category='asr', suite='librispeech-v1', pt_id=1),
             _rank_row('Nova', category='asr', suite='librispeech-v1', pt_id=2)])
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )
        svc = BenchmarkReportService(repo=repo, report_repo=report_repository)
        result = svc.publish(CreateBenchmarkReportCommand(
            suite='librispeech-v1', category='asr', name='ASR 2026Q3', published_by='tester'))

        assert result['success'] is True
        record_id = result['data']['id']
        report_id = result['data']['report_id']
        assert result['data']['published_task_count'] == 2
        assert result['data']['subject_count'] == 2

        # 列表：发布记录可查（不带快照）
        listed = repo.list_benchmark_reports({'suite': 'librispeech-v1', 'category': 'asr',
                                              'source': '', 'task_id': None}, 1, 20)
        assert listed['total'] == 1
        assert listed['items'][0]['id'] == record_id
        assert 'ranking_data' not in listed['items'][0]

        # 详情：含排行快照，数据与 ReadModel 一致
        detail = repo.get_benchmark_report(record_id)
        assert detail['report_id'] == report_id
        assert detail['ranking_data']['counts']['row_count'] == 2
        subjects = {r['subject_name'] for r in detail['ranking_data']['rows']}
        assert subjects == {'Moshi', 'Nova'}

        # 报告主记录：report_type='benchmark' 且状态 published（复用报告 7 表结构）
        from report_service.infrastructure.persistence.models import Report
        from shared.models.database import get_db_session
        s = get_db_session()
        po = s.query(Report).filter(Report.id == report_id).first()
        assert po.type == 'benchmark'
        assert po.status == 'published'
        assert po.name == 'ASR 2026Q3'
        s.close()

    def test_version_tracking_real_repo(self, sqlite_db):
        repo = BenchmarkRepositoryImpl()
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )
        svc = BenchmarkReportService(repo=repo, report_repo=report_repository)
        first = svc.publish(CreateBenchmarkReportCommand(suite='s1', category='asr'))
        second = svc.publish(CreateBenchmarkReportCommand(suite='s1', category='asr'))
        assert first['data']['version'] == 1
        assert second['data']['version'] == 2
        assert repo.max_benchmark_report_version('s1', 'asr') == 2
        assert repo.max_benchmark_report_version('s2', 'asr') == 0


# ==================== gRPC servicer 直接驱动（真仓储 SQLite） ====================

class TestGrpcServicer:
    """直接驱动 BenchmarkServicer（report_service gRPC 端口）→ handler → 真仓储 SQLite。"""

    def test_servicer_publish_list_get_roundtrip(self, sqlite_db):
        import json
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import BenchmarkServicer
        from report_service.infrastructure.persistence.benchmark_repository import (
            BenchmarkRepositoryImpl,
        )

        repo = BenchmarkRepositoryImpl()
        repo.replace_ranking_rows(
            [{'category': 'asr', 'metric_code': 'WER', 'scenario_key': '通用',
              'source': 'platform_test'}],
            [_rank_row('Moshi', category='asr', suite='librispeech-v1', pt_id=1)])

        servicer = BenchmarkServicer()
        # 发布
        resp = servicer.CreateBenchmarkReport(
            report_pb.BenchmarkCommandRequest(data=json.dumps(
                {'suite': 'librispeech-v1', 'category': 'asr',
                 'name': 'gRPC 发布', 'publishedBy': 'tester'})))
        assert resp.success is True
        record = json.loads(resp.data)
        assert record['report_id'] == 1
        assert record['published_task_count'] == 1

        # 列表
        list_resp = servicer.ListBenchmarkReports(
            report_pb.BenchmarkQueryRequest(data=json.dumps(
                {'category': 'asr'})))
        assert list_resp.success is True
        listed = json.loads(list_resp.data)
        assert listed['total'] == 1

        # 详情（含快照）
        get_resp = servicer.GetBenchmarkReport(
            report_pb.BenchmarkQueryRequest(data=json.dumps(
                {'reportId': record['id']})))
        assert get_resp.success is True
        detail = json.loads(get_resp.data)
        assert detail['ranking_data']['rows'][0]['subject_name'] == 'Moshi'

        # 404
        missing = servicer.GetBenchmarkReport(
            report_pb.BenchmarkQueryRequest(data=json.dumps({'reportId': 999})))
        assert missing.success is False
        assert missing.code == 404


# ==================== RBAC 种子（INT-481 两码已 seed 并授权） ====================

class TestRbacSeed:
    def test_report_permissions_seeded_and_granted(self):
        import importlib.util
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            'seed_rbac', str(Path(__file__).resolve().parents[2]
                             / 'scripts' / 'migrations' / '202608' / 'seed_rbac.py'))
        seed_rbac = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(seed_rbac)

        perm_names = {name for name, _ in seed_rbac.PERMISSIONS}
        assert 'benchmark:report:read' in perm_names
        assert 'benchmark:report:publish' in perm_names
        # tester / algo_engineer 均获授
        assert 'benchmark:report:read' in seed_rbac.TESTER_PERMS
        assert 'benchmark:report:publish' in seed_rbac.TESTER_PERMS
        assert 'benchmark:report:read' in seed_rbac.ALGO_ENGINEER_PERMS
        assert 'benchmark:report:publish' in seed_rbac.ALGO_ENGINEER_PERMS
        # admin 超级通配 * 仍可用
        assert '*' in seed_rbac.PERMISSIONS[-1]


# ==================== report_service HTTP 直连（FastAPI 路由） ====================

class TestHttpDirect:
    """report_service 直连 HTTP 端口：路由 → 请求解析 → handler 委托。"""

    def test_post_reports_route_delegates(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import report_service.interfaces.api.benchmark_routes as routes_mod

        captured = {}

        class _FakeCommandHandler:
            def handle_create_report(self, command):
                captured['suite'] = command.suite
                captured['category'] = command.category
                captured['name'] = command.name
                return {'success': True, 'message': 'ok', 'data': {'id': 1, 'report_id': 2},
                        'code': 0}

        monkeypatch.setattr(routes_mod, '_command_handler', _FakeCommandHandler())
        app = FastAPI()
        app.include_router(routes_mod.router)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post('/api/benchmarks/reports', json={
            'suite': 'full-duplex-v1', 'category': 'voice_llm',
            'algorithmSet': '6algo', 'name': 'HTTP 直连',
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body['success'] is True
        assert body['data']['report_id'] == 2
        # 请求体 camelCase alias 正确解析到命令
        assert captured['suite'] == 'full-duplex-v1'
        assert captured['category'] == 'voice_llm'
        assert captured['name'] == 'HTTP 直连'

    def test_get_reports_list_route(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import report_service.interfaces.api.benchmark_routes as routes_mod

        class _FakeQueryHandler:
            def handle_list_reports(self, query):
                return {'success': True, 'message': 'ok',
                        'data': {'items': [], 'total': 0, 'page': query.page,
                                 'per_page': query.per_page, 'pages': 0},
                        'code': 0}

        monkeypatch.setattr(routes_mod, '_query_handler', _FakeQueryHandler())
        app = FastAPI()
        app.include_router(routes_mod.router)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.get('/api/benchmarks/reports?category=asr&perPage=10')
        assert resp.status_code == 200
        assert resp.json()['data']['per_page'] == 10


# ==================== 网关 BFF（发布人注入 + 非法 source 拦截） ====================

class TestGatewayBff:
    """对齐 test_benchmark_gateway_operator.py 的网关审计注入模式（INT-481 BFF 路径）。"""

    @pytest.fixture(autouse=True)
    def _fake_request(self, monkeypatch):
        from api_gateway.infrastructure import request_adapter

        class _State:
            def __init__(self, json_body, username):
                self._json_body = json_body
                self.username = username

        class _FakeRequest:
            def __init__(self, json_body, username):
                self.state = _State(json_body, username)

        def _set(json_body=None, username='audit_operator'):
            request_adapter.set_current_request(_FakeRequest(json_body, username))

        yield _set
        request_adapter.set_current_request(None)

    def test_gateway_create_report_injects_published_by(self, _fake_request, monkeypatch):
        import api_gateway.application.services.benchmark.benchmark_service as gw
        captured = {}

        def _create(payload):
            captured['create'] = dict(payload)
            return {'success': True, 'data': {'id': 1, 'report_id': 2}, 'message': 'ok', 'code': 0}

        monkeypatch.setattr(gw, '_benchmark_acl', SimpleNamespace(create_report=_create))
        _fake_request({'suite': 's1', 'category': 'asr'}, 'audit_operator')

        result = gw.BenchmarkService.create_report()
        assert captured['create']['published_by'] == 'audit_operator'
        assert captured['create']['suite'] == 's1'
        assert result[1] == 201  # 成功返回 201

    def test_gateway_list_reports_rejects_invalid_source(self, _fake_request, monkeypatch):
        import api_gateway.application.services.benchmark.benchmark_service as gw

        _fake_request(None, 'audit_operator')
        monkeypatch.setattr(gw, '_parse_query_params', lambda: {'source': 'weibo'})

        result = gw.BenchmarkService.list_reports()
        assert result[1] == 400  # 非法 source 拦截

    def test_gateway_get_report_not_found_maps_404(self, _fake_request, monkeypatch):
        import api_gateway.application.services.benchmark.benchmark_service as gw

        def _get(report_id):
            return {'success': False, 'message': 'Benchmark 报告不存在', 'data': None, 'code': 404}

        monkeypatch.setattr(gw, '_benchmark_acl', SimpleNamespace(get_report=_get))
        result = gw.BenchmarkService.get_report(999)
        assert result[1] == 404
