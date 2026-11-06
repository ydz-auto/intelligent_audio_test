# -*- coding: utf-8 -*-
"""Benchmark 指标映射创建 API 单测（INT-130：主链 LLM 裁判维度映射缺口）

覆盖：
- 服务层 create_metric_mapping：成功创建 / 维度重复冲突 409 / 必填与方向校验 /
  scenario_tags 归一化
- gRPC servicer：snake_case 与 camelCase 参数解析、异常兜底
- 网关：schema 校验 → ACL 转发、409 业务码 → HTTP 409 冲突
- 排行计算 no_mapping 告警：完成消息携带跳过摘要（不再纯静默）
- 种子覆盖：主链 voice_llm LLM 裁判维度（逐轮话轮评估 / 拒识场景裁判）已入种子
"""
import json
import os
from types import SimpleNamespace

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
    CreateBenchmarkMetricMappingCommand,
)
import report_service.application.services.benchmark_baseline_service as baseline_module
import report_service.application.services.benchmark_ranking_service as rank_module
from report_service.application.services.benchmark_baseline_service import (
    BenchmarkBaselineService,
)
from report_service.application.services.benchmark_ranking_service import (
    BenchmarkRankingService,
)
from report_service.application.handlers.benchmark_handlers import (
    BenchmarkCommandHandler,
)

HIGHER = RankingDirection.HIGHER_IS_BETTER
LOWER = RankingDirection.LOWER_IS_BETTER


class FakeMappingRepo:
    """指标映射仓储替身（内存表）。"""

    def __init__(self, mappings=None):
        self.mappings = list(mappings or [])
        self.created = []

    def list_metric_mappings(self, active_only=False):
        rows = self.mappings + self.created
        if active_only:
            rows = [m for m in rows if m.active]
        return list(rows)

    def create_metric_mapping(self, data):
        entity = MetricMapping(
            id=len(self.mappings) + len(self.created) + 1,
            dimension_name=data['dimension_name'],
            metric_code=data['metric_code'],
            metric_name=data.get('metric_name') or data['dimension_name'],
            unit=data.get('unit') or '',
            direction=RankingDirection(data['direction']),
            scenario_tags=list(data.get('scenario_tags') or []),
            active=bool(data.get('active', True)),
        )
        self.created.append(entity)
        return entity


@pytest.fixture(autouse=True)
def _no_audit(monkeypatch):
    monkeypatch.setattr(baseline_module, 'write_benchmark_audit', lambda *a, **k: None)
    monkeypatch.setattr(rank_module, 'write_benchmark_audit', lambda *a, **k: None)


# ==================== 服务层创建 ====================

class TestCreateMetricMappingService:
    def _service(self, repo):
        return BenchmarkBaselineService(repo=repo)

    def test_create_success_returns_201_with_entity(self):
        repo = FakeMappingRepo()
        result = self._service(repo).create_metric_mapping(
            CreateBenchmarkMetricMappingCommand(
                dimension_name='逐轮话轮评估', metric_code='TURN_EVAL',
                direction='higher_is_better', unit='分',
                scenario_tags=['通用'],
            ))
        assert result['success'] is True
        assert result['code'] == 201
        assert result['data']['dimension_name'] == '逐轮话轮评估'
        assert result['data']['metric_code'] == 'TURN_EVAL'
        assert result['data']['direction'] == 'higher_is_better'
        assert len(repo.created) == 1

    def test_create_strips_and_normalizes_fields(self):
        repo = FakeMappingRepo()
        result = self._service(repo).create_metric_mapping(
            CreateBenchmarkMetricMappingCommand(
                dimension_name='  拒识场景裁判  ', metric_code=' REFUSAL_JUDGE ',
                metric_name='  ', direction=' HIGHER_IS_BETTER ',
                scenario_tags=[' 通用 ', '', '噪声'],
            ))
        assert result['success'] is True
        assert repo.created[0].dimension_name == '拒识场景裁判'
        assert repo.created[0].metric_code == 'REFUSAL_JUDGE'
        # metric_name 空串回退维度名（与仓储落库口径一致）
        assert repo.created[0].metric_name == '拒识场景裁判'
        assert repo.created[0].direction is HIGHER
        assert repo.created[0].scenario_tags == ['通用', '噪声']

    def test_create_duplicate_dimension_conflict_409(self):
        repo = FakeMappingRepo(mappings=[MetricMapping(
            id=1, dimension_name='逐轮话轮评估', metric_code='TURN_EVAL',
            metric_name='逐轮话轮评估', unit='', direction=HIGHER,
        )])
        result = self._service(repo).create_metric_mapping(
            CreateBenchmarkMetricMappingCommand(
                dimension_name='逐轮话轮评估', metric_code='TURN_EVAL',
                direction='higher_is_better',
            ))
        assert result['success'] is False
        assert result['code'] == 409
        assert repo.created == []

    def test_create_requires_dimension_name(self):
        result = BenchmarkBaselineService(repo=FakeMappingRepo()).create_metric_mapping(
            CreateBenchmarkMetricMappingCommand(
                dimension_name='  ', metric_code='X', direction='higher_is_better'))
        assert result['success'] is False
        assert result['code'] == 100

    def test_create_requires_metric_code(self):
        result = BenchmarkBaselineService(repo=FakeMappingRepo()).create_metric_mapping(
            CreateBenchmarkMetricMappingCommand(
                dimension_name='WER', metric_code='', direction='lower_is_better'))
        assert result['success'] is False
        assert result['code'] == 100

    def test_create_rejects_invalid_direction(self):
        result = BenchmarkBaselineService(repo=FakeMappingRepo()).create_metric_mapping(
            CreateBenchmarkMetricMappingCommand(
                dimension_name='WER', metric_code='WER', direction='随便'))
        assert result['success'] is False
        assert result['code'] == 100

    def test_handler_wiring_delegates_to_baseline_service(self):
        repo = FakeMappingRepo()
        handler = BenchmarkCommandHandler(
            ranking_service=SimpleNamespace(compute_ranking=lambda c: {}),
            baseline_service=self._service(repo))
        result = handler.handle_create_metric_mapping(
            CreateBenchmarkMetricMappingCommand(
                dimension_name='WER', metric_code='WER', direction='lower_is_better'))
        assert result['success'] is True
        assert len(repo.created) == 1


# ==================== gRPC servicer ====================

class TestCreateMetricMappingServicer:
    def _servicer(self, capture):
        from report_service.interfaces.grpc.servicers import BenchmarkServicer

        servicer = BenchmarkServicer()
        servicer.command_handler = SimpleNamespace(
            handle_create_metric_mapping=lambda cmd: (
                capture.append(cmd) or
                {'success': True, 'message': '指标映射已创建',
                 'data': {'id': 1, 'dimension_name': cmd.dimension_name}, 'code': 201})
        )
        return servicer

    def test_servicer_accepts_snake_case(self):
        from shared.proto import report_service_pb2 as report_pb

        capture = []
        servicer = self._servicer(capture)
        resp = servicer.CreateBenchmarkMetricMapping(report_pb.BenchmarkCommandRequest(
            data=json.dumps({'dimension_name': 'WER', 'metric_code': 'WER',
                             'direction': 'lower_is_better'}, ensure_ascii=False)))
        assert resp.success is True
        assert resp.code == 201
        assert capture[0].dimension_name == 'WER'

    def test_servicer_accepts_camel_case(self):
        from shared.proto import report_service_pb2 as report_pb

        capture = []
        servicer = self._servicer(capture)
        resp = servicer.CreateBenchmarkMetricMapping(report_pb.BenchmarkCommandRequest(
            data=json.dumps({'dimensionName': '拒识场景裁判', 'metricCode': 'REFUSAL_JUDGE',
                             'direction': 'higher_is_better',
                             'scenarioTags': ['通用']}, ensure_ascii=False)))
        assert resp.success is True
        assert capture[0].metric_code == 'REFUSAL_JUDGE'
        assert capture[0].scenario_tags == ['通用']

    def test_servicer_exception_returns_failure(self):
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import BenchmarkServicer

        servicer = BenchmarkServicer.__new__(BenchmarkServicer)
        servicer.command_handler = SimpleNamespace(
            handle_create_metric_mapping=lambda cmd: (_ for _ in ()).throw(RuntimeError('boom')))
        resp = servicer.CreateBenchmarkMetricMapping(report_pb.BenchmarkCommandRequest(
            data=json.dumps({'dimension_name': 'WER', 'metric_code': 'WER',
                             'direction': 'lower_is_better'})))
        assert resp.success is False
        assert resp.code == 500


# ==================== 网关 ====================

class _State:
    def __init__(self, json_body):
        self._json_body = json_body
        self.username = 'operator'


class _FakeRequest:
    def __init__(self, json_body):
        self.state = _State(json_body)


class TestGatewayCreateMetricMapping:
    @pytest.fixture()
    def capture_acl(self, monkeypatch):
        import api_gateway.application.services.benchmark.benchmark_service as gw_benchmark

        captured = {}

        def _create(payload):
            captured['create'] = dict(payload)
            return {'success': True, 'data': {'id': 9}, 'message': '指标映射已创建', 'code': 201}

        monkeypatch.setattr(gw_benchmark, '_benchmark_acl',
                            SimpleNamespace(create_metric_mapping=_create))
        return captured

    def test_create_forwards_acl_and_returns_201(self, capture_acl):
        from api_gateway.infrastructure import request_adapter
        import api_gateway.application.services.benchmark.benchmark_service as gw_benchmark

        request_adapter.set_current_request(_FakeRequest({
            'dimensionName': '逐轮话轮评估', 'metricCode': 'TURN_EVAL',
            'direction': 'higher_is_better', 'scenarioTags': ['通用'],
        }))
        try:
            payload, http_code = gw_benchmark.BenchmarkService.create_metric_mapping()
        finally:
            request_adapter.set_current_request(None)
        assert http_code == 201
        assert capture_acl['create']['dimension_name'] == '逐轮话轮评估'
        assert capture_acl['create']['metric_code'] == 'TURN_EVAL'

    def test_create_duplicate_maps_to_http_409(self, monkeypatch):
        from api_gateway.infrastructure import request_adapter
        import api_gateway.application.services.benchmark.benchmark_service as gw_benchmark

        monkeypatch.setattr(gw_benchmark, '_benchmark_acl', SimpleNamespace(
            create_metric_mapping=lambda payload: {
                'success': False, 'message': '系统维度 WER 已存在映射配置',
                'data': None, 'code': 409}))
        request_adapter.set_current_request(_FakeRequest(
            {'dimension_name': 'WER', 'metric_code': 'WER', 'direction': 'lower_is_better'}))
        try:
            payload, http_code = gw_benchmark.BenchmarkService.create_metric_mapping()
        finally:
            request_adapter.set_current_request(None)
        assert http_code == 409
        assert payload['code'] == 204  # ErrorCode.CONFLICT

    def test_create_invalid_body_returns_400(self):
        from api_gateway.infrastructure import request_adapter
        import api_gateway.application.services.benchmark.benchmark_service as gw_benchmark

        request_adapter.set_current_request(_FakeRequest({'dimension_name': 'WER'}))
        try:
            payload, http_code = gw_benchmark.BenchmarkService.create_metric_mapping()
        finally:
            request_adapter.set_current_request(None)
        assert http_code == 400


# ==================== 排行计算 no_mapping 告警 ====================

class TestComputeSkipSummary:
    def _ranking_service(self, mappings, pt_details):
        class FakeRepo:
            def list_metric_mappings(self, active_only=False):
                return mappings

            def list_all_current_baselines(self, category='', metric_code='', source_id=None):
                return []

            def replace_ranking_rows(self, group_keys, rows):
                return len(rows)

        class FakePtAcl:
            def list_benchmark_published_tasks(self):
                return [{'id': 524, 'version': 1, 'name': 'INT95验收API',
                         'snapshot_config': {}}]

            def get_published_task_detail(self, published_task_id):
                return pt_details

        return BenchmarkRankingService(repo=FakeRepo(), pt_acl=FakePtAcl())

    def test_message_carries_skip_summary_on_no_mapping(self):
        # 快照含两个维度、映射表均未覆盖（复现实测 no_mapping 空转形态）
        details = {'report_snapshot': {'reportId': 391, 'summary': {
            'dimensionValues': [
                {'id': 72, 'name': '逐轮话轮评估', 'average_value': 0.85},
                {'id': 134, 'name': '拒识场景裁判', 'average_value': 850.0},
            ],
            'apis': [{'name': 'INT95验收API(mock DUT)', 'type': 'http'}],
        }}}
        result = self._ranking_service([], details).compute_ranking(
            ComputeBenchmarkRankingCommand())
        assert result['success'] is True
        assert result['data']['rows_written'] == 0
        assert result['data']['skipped'] == [
            {'subject': 'INT95验收API(mock DUT)', 'metric': '逐轮话轮评估', 'reason': 'no_mapping'},
            {'subject': 'INT95验收API(mock DUT)', 'metric': '拒识场景裁判', 'reason': 'no_mapping'},
        ]
        assert '跳过 2 项：no_mapping 2 项' in result['message']

    def test_message_plain_when_nothing_skipped(self):
        details = {'report_snapshot': {'reportId': 1, 'summary': {
            'dimensionValues': [{'name': 'WER', 'average_value': 5.0}],
            'apis': [{'name': 'DUT', 'type': 'http'}],
        }}}
        mapping = MetricMapping(id=1, dimension_name='WER', metric_code='WER',
                                metric_name='WER', unit='%', direction=LOWER)
        result = self._ranking_service([mapping], details).compute_ranking(
            ComputeBenchmarkRankingCommand())
        assert result['success'] is True
        assert result['data']['rows_written'] == 1
        assert '跳过' not in result['message']

    def test_no_mapping_emits_warning_log(self, caplog):
        details = {'report_snapshot': {'reportId': 391, 'summary': {
            'dimensionValues': [{'id': 72, 'name': '逐轮话轮评估', 'average_value': 0.85}],
            'apis': [{'name': 'DUT', 'type': 'http'}],
        }}}
        with caplog.at_level('WARNING', logger=rank_module.logger.name):
            self._ranking_service([], details).compute_ranking(
                ComputeBenchmarkRankingCommand())
        assert any('无映射配置未进榜' in r.getMessage() for r in caplog.records)


# ==================== 种子覆盖 ====================

class TestSeedCoverage:
    def _load_migration_module(self):
        import importlib.util

        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        path = os.path.join(
            repo_root, 'scripts', 'migrations', '202610', 'add_benchmark_tables.py')
        spec = importlib.util.spec_from_file_location('add_benchmark_tables', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_main_chain_voice_llm_dimensions_seeded(self):
        module = self._load_migration_module()
        by_dim = {row[0]: row for row in module.DEFAULT_MAPPINGS}
        # 主链实测轨两个 LLM 裁判维度必须预置映射，否则实机任务永不进榜
        turn = by_dim['逐轮话轮评估']
        assert turn[1] == 'TURN_EVAL'
        assert turn[4] == 'higher_is_better'
        refusal = by_dim['拒识场景裁判']
        assert refusal[1] == 'REFUSAL_JUDGE'
        assert refusal[4] == 'higher_is_better'

    def test_seed_dimension_names_unique(self):
        module = self._load_migration_module()
        dims = [row[0] for row in module.DEFAULT_MAPPINGS]
        assert len(dims) == len(set(dims))

