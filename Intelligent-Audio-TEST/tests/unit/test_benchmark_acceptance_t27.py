# -*- coding: utf-8 -*-
"""INT-27 验收独立测试（测试工程师补充，不依赖开发自测的替身实现）

与开发自测的差异：直接对真实 SQLAlchemy 仓储（SQLite 临时库）验证事务语义，
覆盖开发单测中 FakeRepo 无法证明的部分：
- 验收标准 3：insert_baseline_version 同事务 demote、旧行内容不可变、
  仓储接口面无修改/删除基线行的方法、部分子集重复导入建新版本
- 验收标准 1：双轨并存两行的竞赛指标（rank/total/percentile/score100/gap）完全一致，
  delta = 实测 − 导入；全并列组 score100 统一 100
- 验收标准 2：服务层组装边界——空数据全量重算 0 行、缺失映射跳过并标记 no_mapping
- 行为快照：组内条目全部消失后全量重算，旧排行行保留（ReadModel 按 key 刷新的
  已知边界，报告中作为观察项说明）
"""
import os
import tempfile

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
import shared.models.database as database
from report_service.domain.entities.benchmark import RankingDirection
from report_service.application.commands.benchmark_commands import (
    ComputeBenchmarkRankingCommand,
    ImportBenchmarkBaselinesCommand,
)
from report_service.application.services.benchmark_baseline_service import (
    BenchmarkBaselineService,
)
from report_service.application.services.benchmark_ranking_service import (
    BenchmarkRankingService,
)
from report_service.infrastructure.persistence.benchmark_repository import (
    BenchmarkRepositoryImpl,
)
from report_service.domain.repositories.benchmark_repository_abc import (
    BenchmarkRepository,
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
def _no_audit(monkeypatch):
    monkeypatch.setattr(baseline_svc_mod, 'write_benchmark_audit', lambda *a, **k: None)
    monkeypatch.setattr(ranking_svc_mod, 'write_benchmark_audit', lambda *a, **k: None)


def _entry(**overrides):
    base = dict(model_name='Deepgram Nova', metric_code='WER', value=5.6,
                vendor='Deepgram', unit='%', direction='lower_is_better',
                scenario_tags=['普通话通用'], sample_size=1000, metric_date='2026-09-01')
    base.update(overrides)
    from report_service.domain.entities.benchmark import BaselineDraftEntry
    return BaselineDraftEntry(**base)


def _seed_source(repo, name='Open ASR Leaderboard'):
    return repo.create_source({'name': name, 'provider': 'Hugging Face',
                               'source_type': 'official'})


def _seed_mapping(repo, dimension='WER', metric_code='WER',
                  direction=RankingDirection.LOWER_IS_BETTER, unit='%',
                  scenario_tags=('普通话通用',)):
    from report_service.infrastructure.persistence.models import BenchmarkMetricMapping
    from shared.models.database import get_db_session
    s = get_db_session()
    po = BenchmarkMetricMapping(
        dimension_name=dimension, metric_code=metric_code, metric_name='Word Error Rate',
        unit=unit, direction=direction.value, scenario_tags=list(scenario_tags), active=True)
    s.add(po)
    s.commit()
    s.close()


class _FakePtAcl:
    """实测轨 ACL 替身（gRPC 层由集成测试覆盖，此处验证服务+真仓储编排）。"""

    def __init__(self, tasks):
        self._tasks = tasks

    def list_benchmark_published_tasks(self):
        return [dict(t) for t in self._tasks]

    def get_published_task_detail(self, published_task_id):
        for t in self._tasks:
            if t.get('id') == published_task_id:
                return t
        return None


def _platform_task(pt_id, name, wer_value, version=1):
    return {
        'id': pt_id, 'name': name, 'version': version,
        'snapshot_config': {'benchmark': True, 'benchmarkSuite': 'librispeech-v1',
                            'benchmarkCategory': 'asr'},
        'report_snapshot': {
            'reportId': 100 + pt_id,
            'summary': {
                'dimensionValues': [{'name': 'WER', 'average_value': wer_value}],
                'devices': [{'name': '测试手机', 'app_name': name, 'type': 'phone'}],
                'apis': [],
            },
        },
    }


# ==================== 验收标准 3：真仓储层不可变快照 ====================

class TestRepoImmutableSnapshot:
    def test_insert_version_demotes_current_atomically(self, sqlite_db):
        repo = BenchmarkRepositoryImpl()
        source = _seed_source(repo)
        svc = BenchmarkBaselineService(repo)
        svc.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=source['id'], category='asr', entries=[_entry(value=5.6)]))

        v1_before = repo.get_baseline_rows(source['id'], 'asr', 1)
        second = svc.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=source['id'], category='asr', entries=[_entry(value=5.9)]))
        assert second['data']['is_new_version'] is True
        assert second['data']['version'] == 2

        v1_after = repo.get_baseline_rows(source['id'], 'asr', 1)
        assert len(v1_after) == len(v1_before) == 1
        for field in ('model_name', 'vendor', 'metric_code', 'value', 'unit',
                      'direction', 'scenario_tags', 'sample_size', 'metric_date'):
            assert v1_after[0][field] == v1_before[0][field]
        assert v1_after[0]['is_current'] is False
        assert repo.get_baseline_rows(source['id'], 'asr', 2)[0]['is_current'] is True

    def test_repository_interface_has_no_mutation_path(self):
        # 仓储接口面无修改/删除基线行内容的方法 → 行只插不改有结构性保证
        methods = {name for name in dir(BenchmarkRepository) if not name.startswith('_')}
        forbidden = {'update_baseline', 'delete_baseline', 'update_baseline_row',
                     'delete_baseline_rows', 'upsert_baseline'}
        assert not methods & forbidden
        for name in ('list_baseline_versions', 'get_baseline_rows',
                     'insert_baseline_version', 'list_current_baselines',
                     'list_all_current_baselines'):
            assert name in methods

    def test_partial_subset_import_creates_new_version(self, sqlite_db):
        # 重复导入既有版本的真子集（内容不同）→ 建新版本，不误判幂等
        repo = BenchmarkRepositoryImpl()
        source = _seed_source(repo)
        svc = BenchmarkBaselineService(repo)
        svc.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=source['id'], category='asr',
            entries=[_entry(value=5.6), _entry(model_name='Whisper', value=8.1)]))

        subset = svc.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=source['id'], category='asr', entries=[_entry(value=5.6)]))
        assert subset['data']['is_new_version'] is True
        assert subset['data']['version'] == 2

        versions = repo.list_baseline_versions(source['id'], 'asr')
        assert [v['version'] for v in versions] == [2, 1]
        assert versions[0]['is_current'] is True and versions[1]['is_current'] is False

    def test_version_isolated_by_category(self, sqlite_db):
        repo = BenchmarkRepositoryImpl()
        source = _seed_source(repo)
        svc = BenchmarkBaselineService(repo)
        svc.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=source['id'], category='asr', entries=[_entry(value=5.6)]))
        second = svc.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=source['id'], category='tts', entries=[_entry(value=5.6)]))
        # 同源不同类别：各自独立版本序列，不误判幂等
        assert second['data']['is_new_version'] is True
        assert second['data']['version'] == 1


# ==================== 验收标准 1：双轨合并口径一致（真仓储） ====================

class TestDualTrackConsistencyRealRepo:
    def test_dual_track_rows_share_competition_metrics(self, sqlite_db):
        repo = BenchmarkRepositoryImpl()
        _seed_mapping(repo)
        source = _seed_source(repo)
        svc = BenchmarkBaselineService(repo)
        svc.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=source['id'], category='asr',
            entries=[_entry(model_name='Moshi', value=6.0),
                     _entry(model_name='Whisper', value=8.5)]))

        pt_acl = _FakePtAcl([_platform_task(1, 'Moshi', 7.2)])
        ranking_svc = BenchmarkRankingService(repo=repo, pt_acl=pt_acl)
        result = ranking_svc.compute_ranking(
            ComputeBenchmarkRankingCommand())
        assert result['success'] is True
        assert result['data']['rows_written'] == 3

        rows = repo.query_rankings({'category': 'asr', 'metric_code': 'WER'})
        by = {(r['subject_name'], r['source']): r for r in rows}
        assert set(by) == {('Moshi', 'platform_test'), ('Moshi', 'external_import'),
                           ('Whisper', 'external_import')}

        moshi_pt = by[('Moshi', 'platform_test')]
        moshi_ext = by[('Moshi', 'external_import')]
        whisper = by[('Whisper', 'external_import')]

        # 排名以实测值参与排序：Moshi 7.2 < Whisper 8.5 → rank 1 / 2
        assert moshi_pt['rank'] == 1 and whisper['rank'] == 2
        assert moshi_ext['rank'] == 1
        # 口径一致：双轨两行的竞赛指标完全相同（同组同值，不因来源不同而漂移）
        for field in ('rank', 'total', 'percentile', 'score100', 'gap_best', 'gap_median',
                      'direction', 'metric_code', 'unit'):
            assert moshi_pt[field] == moshi_ext[field], field
        # 仅值来源不同：实测 7.2 / 导入 6.0，delta = 1.2 两行同值承载
        assert moshi_pt['metric_value'] == pytest.approx(7.2)
        assert moshi_ext['metric_value'] == pytest.approx(6.0)
        assert moshi_pt['delta_external'] == pytest.approx(1.2)
        assert moshi_ext['delta_external'] == pytest.approx(1.2)
        # 无实测的主体 delta 为空
        assert whisper['delta_external'] is None

    def test_all_tied_group_scores_uniform(self, sqlite_db):
        # 全并列（无极差）：rank 共享 1，score100 统一 100
        repo = BenchmarkRepositoryImpl()
        _seed_mapping(repo)
        source = _seed_source(repo)
        svc = BenchmarkBaselineService(repo)
        svc.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=source['id'], category='asr',
            entries=[_entry(model_name='A', value=5.0),
                     _entry(model_name='B', value=5.0)]))

        ranking_svc = BenchmarkRankingService(repo=repo, pt_acl=_FakePtAcl([]))
        result = ranking_svc.compute_ranking(
            ComputeBenchmarkRankingCommand())
        assert result['success'] is True

        rows = repo.query_rankings({'category': 'asr', 'metric_code': 'WER'})
        assert len(rows) == 2
        assert all(r['rank'] == 1 and r['score100'] == pytest.approx(100.0)
                   and r['gap_best'] == 0 for r in rows)


# ==================== 验收标准 2：服务层组装边界 ====================

class TestServiceEdgesRealRepo:
    def test_empty_board_writes_nothing(self, sqlite_db):
        repo = BenchmarkRepositoryImpl()
        ranking_svc = BenchmarkRankingService(repo=repo, pt_acl=_FakePtAcl([]))
        result = ranking_svc.compute_ranking(
            ComputeBenchmarkRankingCommand())
        assert result['success'] is True
        assert result['data']['rows_written'] == 0
        assert repo.query_rankings({}) == []

    def test_missing_mapping_marked_no_mapping(self, sqlite_db):
        # 已发布任务维度无映射配置 → 跳过并标记 no_mapping，不写入排行
        repo = BenchmarkRepositoryImpl()
        pt_acl = _FakePtAcl([_platform_task(1, 'Moshi', 7.2)])
        ranking_svc = BenchmarkRankingService(repo=repo, pt_acl=pt_acl)
        result = ranking_svc.compute_ranking(
            ComputeBenchmarkRankingCommand())
        assert result['success'] is True
        assert result['data']['rows_written'] == 0
        assert any(s['reason'] == 'no_mapping' and s['metric'] == 'WER'
                   for s in result['data']['skipped'])
        assert repo.query_rankings({}) == []


# ==================== 行为快照：ReadModel 按 key 刷新的已知边界 ====================

class TestReadModelRefreshSemantics:
    def test_replace_scoped_to_keys_only(self, sqlite_db):
        # replace 只作用于本次计算涉及的组 key：来源部分重算时另一来源行不受影响
        repo = BenchmarkRepositoryImpl()
        _seed_mapping(repo)
        source = _seed_source(repo)
        svc = BenchmarkBaselineService(repo)
        svc.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=source['id'], category='asr',
            entries=[_entry(model_name='A', value=5.0)]))

        pt_acl = _FakePtAcl([_platform_task(1, 'A', 7.0)])
        ranking_svc = BenchmarkRankingService(repo=repo, pt_acl=pt_acl)
        ranking_svc.compute_ranking(ComputeBenchmarkRankingCommand())
        assert len(repo.query_rankings({})) == 2  # A 实测 + A 导入

        svc.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=source['id'], category='asr',
            entries=[_entry(model_name='A', value=5.1)]))
        # 仅重算外部轨（来源筛选）：实测行原样保留、导入行刷新
        ranking_svc.compute_ranking(
            ComputeBenchmarkRankingCommand(source='external_import'))
        rows = repo.query_rankings({})
        by_source = {r['source']: r for r in rows}
        assert by_source['platform_test']['metric_value'] == pytest.approx(7.0)
        assert by_source['external_import']['metric_value'] == pytest.approx(5.1)

    def test_group_vanish_keeps_stale_rows(self, sqlite_db):
        # 行为快照（观察项，非验收失败项）：某组的全部条目消失后（基线新版本
        # 不再含该指标且无实测），全量重算不触碰该组的旧行——ReadModel 按 key
        # 刷新，组消失场景依赖后续清理策略。此处固化当前行为防静默漂移。
        repo = BenchmarkRepositoryImpl()
        _seed_mapping(repo)
        _seed_mapping(repo, dimension='CER', metric_code='CER', unit='%')
        source = _seed_source(repo)
        svc = BenchmarkBaselineService(repo)
        svc.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=source['id'], category='asr',
            entries=[_entry(model_name='A', metric_code='WER', value=5.0),
                     _entry(model_name='A', metric_code='CER', value=9.0)]))

        ranking_svc = BenchmarkRankingService(repo=repo, pt_acl=_FakePtAcl([]))
        ranking_svc.compute_ranking(
            ComputeBenchmarkRankingCommand())
        assert len(repo.query_rankings({})) == 2

        # v2 只含 WER（CER 从基线中消失），重算后 CER 旧行保留
        svc.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=source['id'], category='asr',
            entries=[_entry(model_name='A', metric_code='WER', value=5.1)]))
        ranking_svc.compute_ranking(
            ComputeBenchmarkRankingCommand())
        rows = repo.query_rankings({})
        codes = {r['metric_code']: r for r in rows}
        assert codes['WER']['metric_value'] == pytest.approx(5.1)   # 新值已刷新
        assert codes['CER']['metric_value'] == pytest.approx(9.0)   # 旧行残留（固化行为）
