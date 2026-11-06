# -*- coding: utf-8 -*-
"""Benchmark 排行计算服务单测（INT-27 验收标准 1：双轨合并排行，口径一致）

覆盖：
- 双轨合并：平台实测 + 外部基线同组排行（同 category/metric/场景口径）
- 双轨并存规则：排名以实测值参与排序，无实测值时以导入值参与排序；delta 计算
- 跳过标记：已发布任务无报告（no_report）、指标缺失映射（no_mapping）
- 同主体多版本取最新参与排行
- 严格 CQRS：查询侧只读不触发写；排行计算是 ReadModel 唯一写入口
- 数据来源筛选与非法值拦截
"""
import os

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from report_service.domain.entities.benchmark import (
    MetricMapping,
    RankingDirection,
)
from report_service.application.commands.benchmark_commands import (
    ComputeBenchmarkRankingCommand,
)
import report_service.application.services.benchmark_ranking_service as rank_module
from report_service.application.services.benchmark_ranking_service import (
    BenchmarkRankingService,
)
from report_service.application.handlers.benchmark_handlers import (
    BenchmarkCommandHandler,
    BenchmarkQueryHandler,
)

LOWER = RankingDirection.LOWER_IS_BETTER


class FakeRankingRepo:
    """排行仓储替身（内存 ReadModel）。"""

    def __init__(self, mappings=None, baselines=None):
        self.mappings = mappings or []
        self.baselines = baselines or []
        self.rankings = []
        self.replace_calls = []

    def list_metric_mappings(self, active_only=False):
        return self.mappings

    def list_all_current_baselines(self, category='', metric_code='', source_id=None):
        return [b for b in self.baselines
                if b.get('is_current', True)
                and (not category or b.get('category') == category)]

    def replace_ranking_rows(self, group_keys, rows):
        self.replace_calls.append({'keys': group_keys, 'rows': rows})
        # 模拟删旧插新
        key_markers = {(k['category'], k['metric_code'], k['scenario_key'], k['source'])
                       for k in group_keys}
        self.rankings = [r for r in self.rankings
                         if (r['category'], r['metric_code'], r['scenario_key'], r['source'])
                         not in key_markers] + list(rows)
        return len(rows)

    def query_rankings(self, filters):
        rows = self.rankings
        if filters.get('suite'):
            rows = [r for r in rows if r['benchmark_suite'] == filters['suite']]
        if filters.get('category'):
            rows = [r for r in rows if r['category'] == filters['category']]
        if filters.get('metric_code'):
            rows = [r for r in rows if r['metric_code'] == filters['metric_code']]
        if filters.get('source'):
            rows = [r for r in rows if r['source'] == filters['source']]
        if filters.get('subject_name'):
            rows = [r for r in rows if r['subject_name'] == filters['subject_name']]
        return list(rows)


class FakePtAcl:
    """已发布任务 ACL 替身。"""

    def __init__(self, tasks=None, details=None):
        self.tasks = tasks or []
        self.details = details or {}

    def list_benchmark_published_tasks(self):
        return list(self.tasks)

    def get_published_task_detail(self, published_task_id):
        return self.details.get(published_task_id)


@pytest.fixture(autouse=True)
def _no_audit(monkeypatch):
    monkeypatch.setattr(rank_module, 'write_benchmark_audit', lambda *a, **k: None)


def _wer_mapping():
    return MetricMapping(
        id=1, dimension_name='WER', metric_code='WER', metric_name='Word Error Rate',
        unit='%', direction=LOWER, scenario_tags=['普通话通用'],
    )


def _pt(pt_id, version, snapshot=None, report=None, name=None):
    return {'id': pt_id, 'version': version, 'name': name or f'PT-{pt_id}',
            'benchmark': True, 'status': 'published', 'snapshot_config': snapshot or {}}


def _detail(pt, dim_values, snapshot=None, report_id=11, devices=None, apis=None):
    return {
        'id': pt['id'],
        'version': pt['version'],
        'snapshot_config': snapshot or pt.get('snapshot_config') or {},
        'report_snapshot': {
            'reportId': report_id,
            'summary': {
                'dimensionValues': dim_values,
                'devices': devices or [],
                'apis': apis or [],
            },
        },
    }


# ==================== 双轨合并 ====================

class TestDualTrackMerge:
    def test_platform_and_external_merge_same_group(self):
        # 同模型 Moshi：平台实测（WER=7.2）+ 外部基线（WER=6.0）并存；
        # 外部独有模型 Whisper（WER=8.5）以导入值参与排序
        repo = FakeRankingRepo(
            mappings=[_wer_mapping()],
            baselines=[
                {'id': 101, 'source_id': 1, 'category': 'voice_llm', 'model_name': 'Moshi',
                 'vendor': 'Kyutai', 'metric_code': 'WER', 'metric_name': 'WER', 'value': 6.0,
                 'unit': '%', 'direction': 'lower_is_better', 'scenario_tags': [],
                 'sample_size': 500, 'metric_date': '2026-08-01', 'version': 1, 'is_current': True},
                {'id': 102, 'source_id': 1, 'category': 'voice_llm', 'model_name': 'Whisper',
                 'vendor': 'OpenAI', 'metric_code': 'WER', 'metric_name': 'WER', 'value': 8.5,
                 'unit': '%', 'direction': 'lower_is_better', 'scenario_tags': [],
                 'sample_size': 500, 'metric_date': '2026-08-01', 'version': 1, 'is_current': True},
            ])
        pt = _pt(1, 2, snapshot={'benchmarkSuite': 'internal-v1', 'benchmarkCategory': 'voice_llm'})
        acl = FakePtAcl(
            tasks=[pt],
            details={1: _detail(pt, [{'name': 'WER', 'average_value': 7.2}],
                                devices=[{'name': '测试机', 'app_name': 'Moshi'}])},
        )
        service = BenchmarkRankingService(repo=repo, pt_acl=acl)
        result = service.compute_ranking(ComputeBenchmarkRankingCommand())

        assert result['success'] is True
        rows = repo.rankings
        # 三行：Moshi 实测 + Moshi 导入 + Whisper 导入
        assert len(rows) == 3
        by = {(r['subject_name'], r['source']): r for r in rows}

        # Moshi 双轨并存：排名以实测值参与排序；delta = 7.2 - 6.0 = 1.2
        moshi_pt = by[('Moshi', 'platform_test')]
        moshi_ext = by[('Moshi', 'external_import')]
        assert moshi_pt['metric_value'] == 7.2 and moshi_ext['metric_value'] == 6.0
        assert moshi_pt['delta_external'] == pytest.approx(1.2)
        assert moshi_ext['delta_external'] == pytest.approx(1.2)
        # Moshi 实测 7.2 vs Whisper 导入 8.5：Moshi 第 1，Whisper 第 2
        assert moshi_pt['rank'] == 1 and moshi_pt['total'] == 2
        whisper = by[('Whisper', 'external_import')]
        assert whisper['rank'] == 2 and whisper['total'] == 2
        # 无实测值时以导入值参与排序：Whisper 的参与值 = 8.5
        assert whisper['metric_value'] == 8.5

    def test_both_rows_share_competition_metrics(self):
        # 双轨两行共享同一竞赛指标（rank/percentile/score100 一致）
        repo = FakeRankingRepo(
            mappings=[_wer_mapping()],
            baselines=[
                {'id': 101, 'source_id': 1, 'category': 'asr', 'model_name': 'Nova',
                 'metric_code': 'WER', 'value': 5.0, 'unit': '%',
                 'direction': 'lower_is_better', 'scenario_tags': [],
                 'version': 1, 'is_current': True},
            ])
        pt = _pt(1, 1, snapshot={'benchmarkCategory': 'asr'}, name='Nova')
        acl = FakePtAcl(tasks=[pt],
                        details={1: _detail(pt, [{'name': 'WER', 'average_value': 5.0}],
                                            devices=[{'name': '设备1', 'app_name': 'Nova'}])})
        service = BenchmarkRankingService(repo=repo, pt_acl=acl)
        service.compute_ranking(ComputeBenchmarkRankingCommand())

        rows = repo.rankings
        assert len(rows) == 2
        assert rows[0]['rank'] == rows[1]['rank'] == 1
        assert rows[0]['percentile'] == rows[1]['percentile'] == 100.0
        # 单主体不归一化：score100 置空
        assert rows[0]['score100'] is None and rows[1]['score100'] is None
        assert rows[0]['delta_external'] == pytest.approx(0.0)


# ==================== 跳过与边界 ====================

class TestSkipsAndEdges:
    def test_no_report_skipped(self):
        repo = FakeRankingRepo(mappings=[_wer_mapping()])
        pt = _pt(1, 1, snapshot={'benchmarkCategory': 'asr'})
        detail = _detail(pt, [])
        detail['report_snapshot'] = None  # 无冻结报告
        acl = FakePtAcl(tasks=[pt], details={1: detail})
        result = BenchmarkRankingService(repo=repo, pt_acl=acl).compute_ranking(
            ComputeBenchmarkRankingCommand())
        assert result['success'] is True
        assert repo.rankings == []
        assert result['data']['skipped'][0]['reason'] == 'no_report'

    def test_platform_dimension_missing_mapping_skipped(self):
        # 平台维度 WER 有映射，MOS 无映射 → MOS 跳过并标记 no_mapping
        repo = FakeRankingRepo(mappings=[_wer_mapping()])
        pt = _pt(1, 1, snapshot={'benchmarkCategory': 'asr'})
        acl = FakePtAcl(tasks=[pt], details={1: _detail(pt, [
            {'name': 'WER', 'average_value': 4.0},
            {'name': 'MOS', 'average_value': 4.5},
        ])})
        result = BenchmarkRankingService(repo=repo, pt_acl=acl).compute_ranking(
            ComputeBenchmarkRankingCommand())
        rows = repo.rankings
        assert len(rows) == 1 and rows[0]['metric_code'] == 'WER'
        assert any(s['reason'] == 'no_mapping' and s['metric'] == 'MOS'
                   for s in result['data']['skipped'])

    def test_external_metric_missing_mapping_skipped(self):
        # 边界：外部基线缺失映射 → 跳过（no_mapping），合法映射指标正常入榜
        repo = FakeRankingRepo(
            mappings=[_wer_mapping()],
            baselines=[
                {'id': 1, 'category': 'asr', 'model_name': 'Nova', 'metric_code': 'WER',
                 'value': 5.0, 'unit': '%', 'direction': 'lower_is_better',
                 'scenario_tags': [], 'version': 1, 'is_current': True},
                {'id': 2, 'category': 'asr', 'model_name': 'Mystery', 'metric_code': 'UNKNOWN_X',
                 'value': 1.0, 'unit': '', 'direction': 'lower_is_better',
                 'scenario_tags': [], 'version': 1, 'is_current': True},
            ])
        result = BenchmarkRankingService(repo=repo, pt_acl=FakePtAcl()).compute_ranking(
            ComputeBenchmarkRankingCommand())
        assert [r['subject_name'] for r in repo.rankings] == ['Nova']
        assert any(s['reason'] == 'no_mapping' for s in result['data']['skipped'])

    def test_empty_board(self):
        # 边界：空榜（无实测无基线）→ 成功返回 0 组 0 行
        result = BenchmarkRankingService(repo=FakeRankingRepo(), pt_acl=FakePtAcl()).compute_ranking(
            ComputeBenchmarkRankingCommand())
        assert result['success'] is True
        assert result['data']['rows_written'] == 0
        assert result['data']['group_count'] == 0

    def test_latest_version_wins_for_same_subject(self):
        # 同测试集同主体多版本：取最新版本参与排行
        repo = FakeRankingRepo(mappings=[_wer_mapping()])
        pt_v1 = _pt(1, 1, snapshot={'benchmarkCategory': 'asr'}, name='Moshi')
        pt_v2 = _pt(2, 2, snapshot={'benchmarkCategory': 'asr'}, name='Moshi')
        acl = FakePtAcl(
            tasks=[pt_v1, pt_v2],
            details={
                1: _detail(pt_v1, [{'name': 'WER', 'average_value': 9.9}]),
                2: _detail(pt_v2, [{'name': 'WER', 'average_value': 3.3}]),
            })
        BenchmarkRankingService(repo=repo, pt_acl=acl).compute_ranking(
            ComputeBenchmarkRankingCommand())
        platform_rows = [r for r in repo.rankings if r['source'] == 'platform_test']
        assert len(platform_rows) == 1
        assert platform_rows[0]['published_task_version'] == 2
        assert platform_rows[0]['metric_value'] == 3.3

    def test_invalid_source_rejected(self):
        result = BenchmarkRankingService(repo=FakeRankingRepo(), pt_acl=FakePtAcl()).compute_ranking(
            ComputeBenchmarkRankingCommand(source='weibo'))
        assert result['success'] is False and result['code'] == 100

    def test_source_filter_limits_collection(self):
        # source=external_import：只消费基线轨，不触发 ACL 拉取
        repo = FakeRankingRepo(
            mappings=[_wer_mapping()],
            baselines=[
                {'id': 1, 'category': 'asr', 'model_name': 'Nova', 'metric_code': 'WER',
                 'value': 5.0, 'unit': '%', 'direction': 'lower_is_better',
                 'scenario_tags': [], 'version': 1, 'is_current': True},
            ])
        acl = FakePtAcl(tasks=[_pt(1, 1)])
        result = BenchmarkRankingService(repo=repo, pt_acl=acl).compute_ranking(
            ComputeBenchmarkRankingCommand(source='external_import'))
        assert result['success'] is True
        assert {r['source'] for r in repo.rankings} == {'external_import'}


# ==================== 严格 CQRS ====================

class TestCqrs:
    def test_query_side_has_no_write_side_effect(self):
        # 读侧查询不触发 ReadModel 写入
        repo = FakeRankingRepo(mappings=[_wer_mapping()])
        handler = BenchmarkQueryHandler(repo=repo)
        result = handler.handle_get_ranking(__import__(
            'report_service.application.queries.benchmark_queries',
            fromlist=['GetBenchmarkRankingQuery']).GetBenchmarkRankingQuery(category='asr'))
        assert result['success'] is True
        assert repo.replace_calls == []  # 查询未产生写副作用

    def test_compute_is_only_writer(self):
        # 写侧：只有 compute_ranking 调用 replace_ranking_rows
        repo = FakeRankingRepo(mappings=[_wer_mapping()])
        pt = _pt(1, 1, snapshot={'benchmarkCategory': 'asr'})
        acl = FakePtAcl(tasks=[pt], details={1: _detail(pt, [{'name': 'WER', 'average_value': 4.0}])})
        service = BenchmarkRankingService(repo=repo, pt_acl=acl)
        service.compute_ranking(ComputeBenchmarkRankingCommand())
        assert len(repo.replace_calls) == 1
        # 刷新键含 source 维度（ReadModel 按组整体替换）
        keys = repo.replace_calls[0]['keys']
        assert keys == [{'category': 'asr', 'metric_code': 'WER',
                         'scenario_key': '普通话通用', 'source': 'platform_test'}]

    def test_compute_idempotent(self):
        # 幂等：同输入重复计算 → ReadModel 行集一致，不产生重复记录
        # computed_at 是每次计算的固有新鲜时间戳（Windows 时钟 ~15.6ms 粒度，
        # 负载下两次计算跨刻度即不相等），幂等断言按业务字段比较、排除该列
        def _rows_without_ts(rows):
            return [{k: v for k, v in r.items() if k != 'computed_at'} for r in rows]

        repo = FakeRankingRepo(mappings=[_wer_mapping()])
        pt = _pt(1, 1, snapshot={'benchmarkCategory': 'asr'})
        acl = FakePtAcl(tasks=[pt], details={1: _detail(pt, [{'name': 'WER', 'average_value': 4.0}])})
        service = BenchmarkRankingService(repo=repo, pt_acl=acl)
        service.compute_ranking(ComputeBenchmarkRankingCommand())
        first = list(repo.rankings)
        service.compute_ranking(ComputeBenchmarkRankingCommand())
        assert _rows_without_ts(repo.rankings) == _rows_without_ts(first)
        assert len(repo.rankings) == 1


# ==================== 审计打回修复回归（INT-27 二次提测） ====================

class _RaisingPtAcl:
    """模拟 ACL 瞬时故障：重试后仍失败（上抛异常）。"""

    def __init__(self, tasks=None, fail_list=False, fail_detail=False):
        self.tasks = tasks or []
        self.fail_list = fail_list
        self.fail_detail = fail_detail

    def list_benchmark_published_tasks(self):
        if self.fail_list:
            raise RuntimeError('task_service unavailable')
        return list(self.tasks)

    def get_published_task_detail(self, published_task_id):
        if self.fail_detail:
            raise RuntimeError('task_service unavailable')
        return None


def test_acl_impl_retries_once_then_raises():
    # 审计 P3-2：ACL 瞬时失败自动重试一次，仍失败上抛（禁止降级空结果）
    from report_service.infrastructure.acl.published_task_acl_repository import (
        _call_with_retry,
    )
    calls = {'n': 0}

    def _op():
        calls['n'] += 1
        raise RuntimeError('transient')

    with pytest.raises(RuntimeError):
        _call_with_retry(_op, 'list_benchmark_published_tasks')
    assert calls['n'] == 2


class TestAclFailureSemantics:
    def test_list_failure_fails_compute_keeps_old_ranking(self):
        # 审计 P3-2：LIST 失败不得降级为"仅外部轨"刷新，整体失败保留旧榜
        repo = FakeRankingRepo(
            mappings=[_wer_mapping()],
            baselines=[
                {'id': 1, 'category': 'asr', 'model_name': 'Nova', 'metric_code': 'WER',
                 'value': 5.0, 'unit': '%', 'direction': 'lower_is_better',
                 'scenario_tags': [], 'version': 1, 'is_current': True},
            ])
        repo.replace_ranking_rows(
            [{'category': 'asr', 'metric_code': 'WER', 'scenario_key': '普通话通用',
              'source': 'platform_test'}],
            [{'source': 'platform_test', 'subject_name': 'Moshi', 'category': 'asr',
              'metric_code': 'WER', 'scenario_key': '普通话通用', 'metric_value': 7.0}])
        before = list(repo.rankings)
        acl = _RaisingPtAcl(fail_list=True)
        result = BenchmarkRankingService(repo=repo, pt_acl=acl).compute_ranking(
            ComputeBenchmarkRankingCommand())
        assert result['success'] is False
        assert result['code'] == 301
        assert repo.rankings == before  # ReadModel 未被触碰
        assert result['message'] != '排行计算失败: task_service unavailable'  # 不透传内部异常

    def test_detail_failure_fails_compute_not_disguised_as_no_report(self):
        # 审计 P3-2：detail 失败不得伪装成 no_report 静默丢主体行
        repo = FakeRankingRepo(mappings=[_wer_mapping()])
        acl = _RaisingPtAcl(tasks=[_pt(1, 1)], fail_detail=True)
        result = BenchmarkRankingService(repo=repo, pt_acl=acl).compute_ranking(
            ComputeBenchmarkRankingCommand())
        assert result['success'] is False
        assert repo.replace_calls == []

    def test_empty_detail_is_legitimate_no_report(self):
        # 服务端明确返回无数据（None）仍是 no_report 合法形态，不算故障
        repo = FakeRankingRepo(mappings=[_wer_mapping()])
        acl = FakePtAcl(tasks=[_pt(1, 1)], details={})  # detail 缺失 → None
        result = BenchmarkRankingService(repo=repo, pt_acl=acl).compute_ranking(
            ComputeBenchmarkRankingCommand())
        assert result['success'] is True
        assert result['data']['skipped'][0]['reason'] == 'no_report'


class TestCommandContract:
    def test_compute_command_rejects_task_scoped_recompute(self):
        # 审计 P2-1（方案 A）：按任务范围重算会静默删除同组其他任务排行行，
        # 命令不再提供 published_task_id 参数（设计文档 §7.1 仅全量重算）
        import pytest as _pytest
        with _pytest.raises(TypeError):
            ComputeBenchmarkRankingCommand(published_task_id=1)
