# -*- coding: utf-8 -*-
"""Benchmark 外部基线导入单测（INT-27 验收标准 3）

覆盖：
- 逐行校验（字段缺失 / 方向非法 / 映射存在时单位方向不一致拦截），合法行不阻断
- 重复导入幂等（同内容 → 返回已有版本，不新建版本、不翻转 is_current）
- 快照不可变（新版本 = 追加行 + 旧当前版本翻转 is_current，旧行内容不修改）
- 命令级校验（数据源不存在 / 类别非法 / 空条目 / 全部非法）
- 指标映射更新（成功 + 方向非法拦截）
"""
import os

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from report_service.domain.entities.benchmark import (
    BaselineDraftEntry,
    MetricMapping,
    RankingDirection,
)
from report_service.application.commands.benchmark_commands import (
    CreateBenchmarkSourceCommand,
    ImportBenchmarkBaselinesCommand,
    UpdateBenchmarkMetricMappingCommand,
)
import report_service.application.services.benchmark_baseline_service as svc_module
from report_service.application.services.benchmark_baseline_service import (
    BenchmarkBaselineService,
)

LOWER = RankingDirection.LOWER_IS_BETTER


class FakeRepo:
    """基线仓储替身：内存版不可变快照语义。"""

    def __init__(self, mappings=None):
        self.mappings = mappings or []
        self.sources = {1: {'id': 1, 'name': 'Pipecat STT Benchmark'}}
        self.rows = []  # 基线行（模拟 benchmark_baselines）
        self.next_id = 1

    # ---- 指标映射 ----
    def list_metric_mappings(self, active_only=False):
        return self.mappings

    def update_metric_mapping(self, mapping_id, updates):
        return None

    # ---- 数据源 ----
    def get_source(self, source_id):
        return self.sources.get(source_id)

    def create_source(self, data):
        new_id = max(self.sources.keys(), default=0) + 1
        record = dict(data)
        record['id'] = new_id
        self.sources[new_id] = record
        return record

    # ---- 基线版本 ----
    def list_baseline_versions(self, source_id, category):
        versions = {}
        for row in self.rows:
            if row['source_id'] == source_id and row['category'] == category:
                versions.setdefault(row['version'], False)
                versions[row['version']] = versions[row['version']] or row['is_current']
        return [
            {'version': v, 'is_current': cur,
             'entry_count': sum(1 for r in self.rows
                                if r['source_id'] == source_id and r['category'] == category
                                and r['version'] == v)}
            for v, cur in sorted(versions.items(), reverse=True)
        ]

    def get_baseline_rows(self, source_id, category, version):
        return [
            dict(r) for r in self.rows
            if r['source_id'] == source_id and r['category'] == category
            and r['version'] == version
        ]

    def insert_baseline_version(self, rows, demote_source_id, demote_category):
        # 模拟同事务：旧当前版本翻转 False → 新行 is_current=True
        for r in self.rows:
            if (r['source_id'] == demote_source_id and r['category'] == demote_category
                    and r['is_current']):
                r['is_current'] = False
        ids = []
        for row in rows:
            record = dict(row)
            record['id'] = self.next_id
            self.next_id += 1
            self.rows.append(record)
            ids.append(record['id'])
        return ids

    def list_current_baselines(self, **kwargs):
        return {'items': [], 'total': 0, 'page': 1, 'per_page': 20, 'pages': 0}

    def list_all_current_baselines(self, **kwargs):
        return [dict(r) for r in self.rows if r['is_current']]


@pytest.fixture(autouse=True)
def _no_audit(monkeypatch):
    """静默审计写入（单测不依赖 logs 落库）。"""
    monkeypatch.setattr(svc_module, 'write_benchmark_audit', lambda *a, **k: None)


def _entry(**overrides):
    base = dict(model_name='Deepgram Nova', metric_code='WER', value=5.6,
                vendor='Deepgram', unit='%', direction='lower_is_better',
                scenario_tags=['普通话通用'], sample_size=1000, metric_date='2026-09-01')
    base.update(overrides)
    return BaselineDraftEntry(**base)


def _wer_mapping(direction='lower_is_better', unit='%'):
    return MetricMapping(
        id=1, dimension_name='WER', metric_code='WER', metric_name='Word Error Rate',
        unit=unit, direction=RankingDirection(direction), scenario_tags=['普通话通用'],
    )


# ==================== 命令级校验 ====================

class TestImportCommandValidation:
    def test_source_not_exist(self):
        service = BenchmarkBaselineService(FakeRepo())
        result = service.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=999, category='asr', entries=[_entry()]))
        assert result['success'] is False and result['code'] == 201

    def test_invalid_category(self):
        service = BenchmarkBaselineService(FakeRepo())
        result = service.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=1, category='stt', entries=[_entry()]))
        assert result['success'] is False and result['code'] == 102

    def test_empty_entries(self):
        service = BenchmarkBaselineService(FakeRepo())
        result = service.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=1, category='asr', entries=[]))
        assert result['success'] is False and result['code'] == 103


# ==================== 逐行校验 ====================

class TestRowValidation:
    def test_valid_rows_imported(self):
        repo = FakeRepo()
        service = BenchmarkBaselineService(repo)
        result = service.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=1, category='asr', entries=[_entry(), _entry(model_name='Whisper')]))
        assert result['success'] is True
        assert result['data']['version'] == 1
        assert result['data']['entry_count'] == 2
        assert result['data']['errors'] == []

    def test_missing_model_name_row_error(self):
        service = BenchmarkBaselineService(FakeRepo())
        result = service.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=1, category='asr', entries=[_entry(model_name='  ')]))
        assert result['success'] is False and result['code'] == 104
        assert result['data']['errors'][0]['field'] == 'model_name'

    def test_missing_metric_code_row_error(self):
        service = BenchmarkBaselineService(FakeRepo())
        result = service.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=1, category='asr', entries=[_entry(metric_code='')]))
        assert result['data']['errors'][0]['field'] == 'metric_code'

    def test_non_numeric_value_row_error(self):
        service = BenchmarkBaselineService(FakeRepo())
        result = service.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=1, category='asr', entries=[_entry(value='abc')]))
        assert result['data']['errors'][0]['field'] == 'value'

    def test_invalid_direction_row_error(self):
        service = BenchmarkBaselineService(FakeRepo())
        result = service.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=1, category='asr', entries=[_entry(direction='up')]))
        assert result['data']['errors'][0]['field'] == 'direction'

    def test_direction_mismatch_with_mapping_blocked(self):
        # 映射存在：方向不一致拦截，不允许入库
        repo = FakeRepo(mappings=[_wer_mapping(direction='lower_is_better')])
        service = BenchmarkBaselineService(repo)
        result = service.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=1, category='asr',
            entries=[_entry(direction='higher_is_better')]))
        assert result['success'] is False
        assert result['data']['errors'][0]['field'] == 'direction'
        assert result['data']['imported'] == 0

    def test_unit_mismatch_with_mapping_blocked(self):
        repo = FakeRepo(mappings=[_wer_mapping(unit='%')])
        service = BenchmarkBaselineService(repo)
        result = service.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=1, category='asr', entries=[_entry(unit='ms')]))
        assert result['data']['errors'][0]['field'] == 'unit'

    def test_valid_rows_not_blocked_by_invalid_row(self):
        # 部分非法：合法行正常入库（设计文档 §10）
        repo = FakeRepo()
        service = BenchmarkBaselineService(repo)
        result = service.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=1, category='asr',
            entries=[_entry(), _entry(model_name=''), _entry(model_name='Whisper', value=8.1)]))
        assert result['success'] is True
        assert result['data']['entry_count'] == 2
        assert len(result['data']['errors']) == 1
        assert result['data']['errors'][0]['row'] == 2

    def test_direction_unit_filled_from_mapping(self):
        # 行未提供单位/指标名时从映射补齐
        repo = FakeRepo(mappings=[_wer_mapping()])
        service = BenchmarkBaselineService(repo)
        result = service.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=1, category='asr',
            entries=[_entry(unit='', metric_name='')]))
        rows = repo.get_baseline_rows(1, 'asr', 1)
        assert rows[0]['unit'] == '%'
        assert rows[0]['metric_name'] == 'Word Error Rate'


# ==================== 幂等与不可变快照 ====================

class TestIdempotencyAndImmutability:
    def test_duplicate_import_idempotent(self):
        # 验收标准 3：重复导入幂等 → 不新建版本
        repo = FakeRepo()
        service = BenchmarkBaselineService(repo)
        first = service.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=1, category='asr', entries=[_entry()]))
        assert first['data']['is_new_version'] is True
        first_rows = list(repo.rows)

        second = service.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=1, category='asr', entries=[_entry()]))
        assert second['success'] is True
        assert second['data']['is_new_version'] is False
        assert second['data']['version'] == 1
        assert repo.rows == first_rows  # 未追加任何行

    def test_new_version_appended_and_current_flipped(self):
        # 快照不可变：新版本追加行，旧版本行内容不变、仅 is_current 翻转
        repo = FakeRepo()
        service = BenchmarkBaselineService(repo)
        service.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=1, category='asr', entries=[_entry(value=5.6)]))
        v1_rows = [dict(r) for r in repo.rows]

        second = service.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=1, category='asr', entries=[_entry(value=5.9)]))
        assert second['data']['is_new_version'] is True
        assert second['data']['version'] == 2

        # v1 行内容未被修改（除 is_current 翻转）
        for old, new in zip(v1_rows, [r for r in repo.rows if r['version'] == 1]):
            assert old['value'] == new['value']
            assert new['is_current'] is False
        # v2 行为当前版本
        assert all(r['is_current'] for r in repo.rows if r['version'] == 2)

    def test_versions_isolated_by_category(self):
        repo = FakeRepo()
        service = BenchmarkBaselineService(repo)
        service.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=1, category='asr', entries=[_entry()]))
        result = service.import_baselines(ImportBenchmarkBaselinesCommand(
            source_id=1, category='tts', entries=[_entry()]))
        # 不同类别互不影响，各自从 v1 开始
        assert result['data']['version'] == 1


# ==================== 数据源与指标映射 ====================

class TestSourceAndMapping:
    def test_create_source_success(self):
        service = BenchmarkBaselineService(FakeRepo())
        result = service.create_source(CreateBenchmarkSourceCommand(
            name='Open ASR Leaderboard', provider='Hugging Face', source_type='official'))
        assert result['success'] is True and result['code'] == 201

    def test_create_source_invalid_type(self):
        service = BenchmarkBaselineService(FakeRepo())
        result = service.create_source(CreateBenchmarkSourceCommand(
            name='X', source_type='blog'))
        assert result['success'] is False and result['code'] == 101

    def test_create_source_empty_name(self):
        service = BenchmarkBaselineService(FakeRepo())
        result = service.create_source(CreateBenchmarkSourceCommand(name=''))
        assert result['success'] is False and result['code'] == 100

    def test_update_mapping_invalid_direction(self):
        service = BenchmarkBaselineService(FakeRepo())
        result = service.update_metric_mapping(UpdateBenchmarkMetricMappingCommand(
            mapping_id=1, direction='diagonal'))
        assert result['success'] is False and result['code'] == 100
