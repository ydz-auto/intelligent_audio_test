# -*- coding: utf-8 -*-
"""INT-844 专项：基准线管理 CRUD 补操作人 user_id。

背景（INT-844 缺陷）：报告域 CRUD（除查询）应全部带操作人 user_id（INT-141 口径）；
基准线管理四表此前缺认证 user_id——benchmark_sources.created_by 是 String(120)
客户端自报旧列，benchmark_metric_mappings / benchmark_baselines /
benchmark_reports 无 user_id 列。

覆盖（域 × 动作）：
- 数据源：create_source 写 created_by_user_id；旧 created_by 字符串列保留
- 指标映射：create 写 created_by_user_id；update 写 updated_by_user_id
- 基线导入：import_baselines 新版本行写 created_by_user_id（用户操作）
- Benchmark 报告发布：publish → insert_benchmark_report 写 created_by_user_id
- 无上下文（AUTH_MODE=off 等价）：user_id 列 NULL，不硬编码 0 充当真实用户
- 客户端自报 created_by 不覆盖认证 user_id（红线：不信任客户端自报）

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表，
对齐 test_benchmark_acceptance_t27.py / test_int299_operator_columns.py 口径。
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


import report_service.infrastructure.persistence.models  # noqa: F401  注册 benchmark 表
import report_service.application.services.benchmark_baseline_service as baseline_svc_mod
import report_service.application.services.benchmark_ranking_service as ranking_svc_mod
import report_service.application.services.benchmark_report_service as report_svc_mod
import shared.models.database as database
from shared.infrastructure.user_context import set_current_user_id, get_current_user_id
from report_service.domain.entities.benchmark import BaselineDraftEntry, RankingDirection
from report_service.application.commands.benchmark_commands import (
    CreateBenchmarkSourceCommand,
    CreateBenchmarkMetricMappingCommand,
    UpdateBenchmarkMetricMappingCommand,
    ImportBenchmarkBaselinesCommand,
)
from report_service.application.services.benchmark_baseline_service import (
    BenchmarkBaselineService,
)
from report_service.infrastructure.persistence.benchmark_repository import (
    BenchmarkRepositoryImpl,
)
from report_service.infrastructure.persistence.models import (
    BenchmarkSource,
    BenchmarkMetricMapping,
    BenchmarkBaseline,
    BenchmarkReport,
)


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


@pytest.fixture(autouse=True)
def _no_audit_and_event(monkeypatch):
    monkeypatch.setattr(baseline_svc_mod, 'write_benchmark_audit', lambda *a, **k: None)
    monkeypatch.setattr(ranking_svc_mod, 'write_benchmark_audit', lambda *a, **k: None)
    monkeypatch.setattr(report_svc_mod, 'write_benchmark_audit', lambda *a, **k: None)
    monkeypatch.setattr(report_svc_mod, '_emit_report_event', lambda *a, **k: None)
    yield
    # 上下文必清理，防止泄漏到后续用例
    set_current_user_id(None)


def _entry(**overrides):
    base = dict(model_name='Deepgram Nova', metric_code='WER', value=5.6,
                vendor='Deepgram', unit='%', direction='lower_is_better',
                scenario_tags=['普通话通用'], sample_size=1000, metric_date='2026-09-01')
    base.update(overrides)
    return BaselineDraftEntry(**base)


# ==================== 服务层：数据字典注入认证 user_id ====================

class _CapturingRepo:
    """替身：捕获传给仓储的 data / updates dict，不落库。"""

    def __init__(self):
        self.source_calls = []
        self.mapping_create_calls = []
        self.mapping_update_calls = []
        self.import_rows = []
        self.sources = {1: {'id': 1, 'name': 'Pipecat STT Benchmark'}}

    # 数据源
    def get_source(self, source_id):
        return self.sources.get(source_id)

    def create_source(self, data):
        self.source_calls.append(dict(data))
        return {'id': 99, **{k: v for k, v in data.items() if k in ('name', 'created_by')}}

    # 指标映射
    def list_metric_mappings(self, active_only=False):
        return []

    def create_metric_mapping(self, data):
        self.mapping_create_calls.append(dict(data))
        return SimpleNamespace(id=1, dimension_name=data['dimension_name'],
                               metric_code=data['metric_code'],
                               metric_name=data.get('metric_name') or data['dimension_name'],
                               unit=data.get('unit') or '', direction=RankingDirection(data['direction']),
                               scenario_tags=list(data.get('scenario_tags') or []),
                               active=bool(data.get('active', True)))

    def update_metric_mapping(self, mapping_id, updates):
        self.mapping_update_calls.append((mapping_id, dict(updates)))
        return SimpleNamespace(id=mapping_id, dimension_name='WER', metric_code='WER',
                               metric_name='WER', unit='%', direction=RankingDirection.LOWER_IS_BETTER,
                               scenario_tags=[], active=True)

    # 基线版本（幂等比对需要）
    def list_baseline_versions(self, source_id, category):
        return []

    def get_baseline_rows(self, source_id, category, version):
        return []

    def insert_baseline_version(self, rows, demote_source_id, demote_category):
        self.import_rows.extend([dict(r) for r in rows])
        return {'version': 1, 'ids': [1]}


class TestServiceInjectUserContext:
    def test_create_source_passes_authenticated_user_id(self):
        repo = _CapturingRepo()
        set_current_user_id(701)
        svc = BenchmarkBaselineService(repo)
        svc.create_source(CreateBenchmarkSourceCommand(
            name='Open ASR Leaderboard', provider='Hugging Face',
            source_type='official', created_by='front-end-self'))
        call = repo.source_calls[0]
        assert call['created_by_user_id'] == 701
        # 客户端自报值仅落旧列（V9.7.10 兼容），不作操作人依据
        assert call['created_by'] == 'front-end-self'

    def test_create_source_no_context_user_id_null(self):
        repo = _CapturingRepo()
        set_current_user_id(None)
        BenchmarkBaselineService(repo).create_source(
            CreateBenchmarkSourceCommand(name='X', source_type='manual'))
        assert repo.source_calls[0]['created_by_user_id'] is None

    def test_create_metric_mapping_passes_authenticated_user_id(self):
        repo = _CapturingRepo()
        set_current_user_id(702)
        BenchmarkBaselineService(repo).create_metric_mapping(
            CreateBenchmarkMetricMappingCommand(
                dimension_name='WER', metric_code='WER', direction='lower_is_better'))
        assert repo.mapping_create_calls[0]['created_by_user_id'] == 702

    def test_update_metric_mapping_passes_authenticated_user_id(self):
        repo = _CapturingRepo()
        set_current_user_id(703)
        BenchmarkBaselineService(repo).update_metric_mapping(
            UpdateBenchmarkMetricMappingCommand(mapping_id=5, metric_name='WER2'))
        mapping_id, updates = repo.mapping_update_calls[0]
        assert mapping_id == 5
        assert updates['updated_by_user_id'] == 703
        assert updates['metric_name'] == 'WER2'

    def test_update_metric_mapping_no_field_no_updated_by(self):
        # 无可更新字段：提前返回，不写 updated_by_user_id
        repo = _CapturingRepo()
        set_current_user_id(703)
        result = BenchmarkBaselineService(repo).update_metric_mapping(
            UpdateBenchmarkMetricMappingCommand(mapping_id=5))
        assert result['success'] is False and result['code'] == 101
        assert repo.mapping_update_calls == []

    def test_import_baselines_rows_carry_authenticated_user_id(self):
        repo = _CapturingRepo()
        set_current_user_id(704)
        svc = BenchmarkBaselineService(repo)
        result = svc.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=1, category='asr', entries=[_entry(), _entry(model_name='Whisper')]))
        assert result['success'] is True
        assert len(repo.import_rows) == 2
        assert all(r['created_by_user_id'] == 704 for r in repo.import_rows)

    def test_import_baselines_no_context_user_id_null(self):
        repo = _CapturingRepo()
        set_current_user_id(None)
        BenchmarkBaselineService(repo).import_baselines(
            ImportBenchmarkBaselinesCommand(source_id=1, category='asr', entries=[_entry()]))
        assert repo.import_rows[0]['created_by_user_id'] is None


# ==================== 真仓储（SQLite）：DB 列落库 ====================

class TestRealRepoOperatorColumns:
    def test_create_source_writes_created_by_user_id(self, sqlite_db):
        repo = BenchmarkRepositoryImpl()
        set_current_user_id(801)
        repo.create_source({'name': 'INT844 Source', 'provider': 'HF',
                            'source_type': 'official', 'created_by': 'front-end',
                            'created_by_user_id': get_current_user_id()})
        s = database.get_db_session()
        try:
            po = s.query(BenchmarkSource).first()
            assert po.created_by_user_id == 801
            assert po.created_by == 'front-end'  # 旧列保留
        finally:
            s.close()

    def test_create_metric_mapping_writes_created_by_user_id(self, sqlite_db):
        repo = BenchmarkRepositoryImpl()
        set_current_user_id(802)
        repo.create_metric_mapping({
            'dimension_name': 'WER', 'metric_code': 'WER', 'metric_name': 'WER',
            'unit': '%', 'direction': 'lower_is_better', 'scenario_tags': ['通用'],
            'created_by_user_id': get_current_user_id(),
        })
        s = database.get_db_session()
        try:
            po = s.query(BenchmarkMetricMapping).first()
            assert po.created_by_user_id == 802
            assert po.updated_by_user_id is None  # create 不写 updated_by
        finally:
            s.close()

    def test_update_metric_mapping_writes_updated_by_user_id(self, sqlite_db):
        repo = BenchmarkRepositoryImpl()
        set_current_user_id(802)
        repo.create_metric_mapping({
            'dimension_name': 'WER', 'metric_code': 'WER', 'metric_name': 'WER',
            'unit': '%', 'direction': 'lower_is_better', 'scenario_tags': ['通用'],
            'created_by_user_id': get_current_user_id(),
        })
        set_current_user_id(803)
        mapping = repo.update_metric_mapping(1, {'metric_name': 'WER2',
                                                  'updated_by_user_id': get_current_user_id()})
        s = database.get_db_session()
        try:
            po = s.query(BenchmarkMetricMapping).filter(BenchmarkMetricMapping.id == mapping.id).first()
            assert po.created_by_user_id == 802      # 创建人不变
            assert po.updated_by_user_id == 803      # 更新人正确
            assert po.metric_name == 'WER2'
        finally:
            s.close()

    def test_import_baselines_writes_created_by_user_id(self, sqlite_db):
        repo = BenchmarkRepositoryImpl()
        source = repo.create_source({'name': 'INT844 Base', 'source_type': 'official',
                                     'created_by_user_id': get_current_user_id()})
        set_current_user_id(804)
        svc = BenchmarkBaselineService(repo)
        svc.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=source['id'], category='asr', entries=[_entry()]))
        s = database.get_db_session()
        try:
            po = s.query(BenchmarkBaseline).first()
            assert po.created_by_user_id == 804
            assert po.is_current is True
        finally:
            s.close()

    def test_import_baselines_no_context_user_id_null(self, sqlite_db):
        repo = BenchmarkRepositoryImpl()
        set_current_user_id(None)
        source = repo.create_source({'name': 'INT844 Base2', 'source_type': 'official',
                                     'created_by_user_id': get_current_user_id()})
        BenchmarkBaselineService(repo).import_baselines(
            ImportBenchmarkBaselinesCommand(
                source_id=source['id'], category='asr', entries=[_entry()]))
        s = database.get_db_session()
        try:
            po = s.query(BenchmarkBaseline).first()
            assert po.created_by_user_id is None
        finally:
            s.close()


# ==================== Benchmark 报告发布：publish 注入操作人 ====================

class _FakeReportRepo:
    def __init__(self):
        self.aggregates = {}
        self.summaries = {}
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
            self.aggregates.pop(report_id)
            return True
        return False


class _FakeBenchmarkRepo:
    def query_rankings(self, filters):
        return []

    def max_benchmark_report_version(self, suite='', category=''):
        return 0

    def insert_benchmark_report(self, data):
        self.captured = dict(data)
        return {**self.captured, 'id': 1, 'created_at': datetime(2026, 10, 19, 0, 0, 0),
                'published_at': datetime(2026, 10, 19, 0, 0, 0), 'updated_at': None}


class TestReportPublishOperator:
    def test_publish_injects_authenticated_user_id(self):
        from report_service.application.services.benchmark_report_service import (
            BenchmarkReportService,
        )
        from report_service.application.commands.benchmark_commands import (
            CreateBenchmarkReportCommand,
        )
        repo = _FakeBenchmarkRepo()
        set_current_user_id(901)
        svc = BenchmarkReportService(repo=repo, report_repo=_FakeReportRepo())
        result = svc.publish(CreateBenchmarkReportCommand(
            suite='s1', category='asr', published_by='front-end'))
        assert result['success'] is True
        assert repo.captured['created_by_user_id'] == 901
        # 旧 published_by 列保留（客户端自报仅作展示，非操作人依据）
        assert repo.captured['published_by'] == 'front-end'

    def test_publish_no_context_user_id_null(self):
        from report_service.application.services.benchmark_report_service import (
            BenchmarkReportService,
        )
        from report_service.application.commands.benchmark_commands import (
            CreateBenchmarkReportCommand,
        )
        repo = _FakeBenchmarkRepo()
        set_current_user_id(None)
        svc = BenchmarkReportService(repo=repo, report_repo=_FakeReportRepo())
        svc.publish(CreateBenchmarkReportCommand(suite='s1', category='asr'))
        assert repo.captured['created_by_user_id'] is None

    def test_publish_real_repo_writes_created_by_user_id(self, sqlite_db):
        from report_service.application.services.benchmark_report_service import (
            BenchmarkReportService,
        )
        from report_service.application.commands.benchmark_commands import (
            CreateBenchmarkReportCommand,
        )
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )
        repo = BenchmarkRepositoryImpl()
        set_current_user_id(902)
        svc = BenchmarkReportService(repo=repo, report_repo=report_repository)
        result = svc.publish(CreateBenchmarkReportCommand(suite='s1', category='asr'))
        assert result['success'] is True
        s = database.get_db_session()
        try:
            po = s.query(BenchmarkReport).filter(BenchmarkReport.id == result['data']['id']).first()
            assert po.created_by_user_id == 902
        finally:
            s.close()


# ==================== 模型结构 ====================

class TestModelColumns:
    def test_benchmark_sources_has_operator_columns(self):
        assert 'created_by_user_id' in {c.name for c in BenchmarkSource.__table__.columns}
        assert 'updated_by_user_id' in {c.name for c in BenchmarkSource.__table__.columns}
        # 旧 created_by 字符串列保留（V9.7.10 兼容）
        assert 'created_by' in {c.name for c in BenchmarkSource.__table__.columns}
        col = BenchmarkSource.__table__.columns['created_by_user_id']
        assert isinstance(col.type, BigInteger)

    def test_benchmark_metric_mappings_has_operator_columns(self):
        cols = {c.name for c in BenchmarkMetricMapping.__table__.columns}
        assert 'created_by_user_id' in cols
        assert 'updated_by_user_id' in cols

    def test_benchmark_baselines_has_created_by(self):
        assert 'created_by_user_id' in {c.name for c in BenchmarkBaseline.__table__.columns}

    def test_benchmark_reports_has_created_by(self):
        assert 'created_by_user_id' in {c.name for c in BenchmarkReport.__table__.columns}
