# -*- coding: utf-8 -*-
"""Benchmark 双轨排行 —— 网关 HTTP 真实链路验收（INT-27）

全链路走真实代码：
网关路由/schema → ACL 代理 → gRPC（进程内真实 server，生产同款拦截器）
→ report_service 应用服务/领域算法 → 仓储 → DB（SQLite 临时库，模型表全量建）；
排行实测轨经 report_service ACL → task_service PublishedTaskConfigService（进程内）
→ published_tasks（benchmark=true + 冻结报告快照）。

覆盖验收标准：
1. 双轨数据经统一指标映射后合并排行，口径一致（Moshi 实测 7.2 vs 导入 6.0 并存，
   delta=1.2；Whisper 无实测以导入值参与排序）
2. 6 算法边界由单测覆盖（test_benchmark_ranking_algorithms.py），此处验证真实链路贯通
3. 外部基线重复导入幂等、快照不可变（v1 行不修改，新版本翻转 is_current）
"""
import json
import os
import uuid

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ['AUTH_MODE'] = 'off'

from concurrent import futures

import grpc
import pytest

from tests.integration.test_data_transfer_roundtrip import (  # noqa: F401
    db,
    fake_redis,
    storage_env,
)


@pytest.fixture()
def benchmark_grpc_servers(db):
    """进程内启动真实 task PublishedTaskConfigService + report BenchmarkConfigService。"""
    from shared.infrastructure.grpc_interceptors import (
        server_db_scope_interceptor,
        server_log_interceptor,
    )
    from shared.proto import task_service_pb2_grpc as task_grpc
    from shared.proto import report_service_pb2_grpc as report_grpc
    from task_service.interfaces.grpc.published_task_config import (
        PublishedTaskConfigServiceServicer,
    )
    from report_service.interfaces.grpc.servicers import BenchmarkServicer

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=8),
        interceptors=[server_db_scope_interceptor, server_log_interceptor])
    task_grpc.add_PublishedTaskConfigServiceServicer_to_server(
        PublishedTaskConfigServiceServicer(), server)
    report_grpc.add_BenchmarkConfigServiceServicer_to_server(
        BenchmarkServicer(), server)
    task_port = server.add_insecure_port('[::]:0')
    report_port = server.add_insecure_port('[::]:0')
    server.start()
    yield task_port, report_port
    server.stop(grace=None).wait(timeout=5)


@pytest.fixture()
def benchmark_chain(benchmark_grpc_servers, monkeypatch):
    """channel/stub 指向进程内双 server（清 lru_cache），测试后还原。"""
    task_port, report_port = benchmark_grpc_servers
    import shared.clients._grpc_channels as channels_mod
    import shared.clients._grpc_stubs as stubs_mod

    monkeypatch.setattr(channels_mod, 'TASK_GRPC_ADDR', f'localhost:{task_port}')
    monkeypatch.setattr(channels_mod, 'REPORT_GRPC_ADDR', f'localhost:{report_port}')
    channels_mod._get_task_channel.cache_clear()
    channels_mod._get_report_channel.cache_clear()
    stubs_mod.get_published_task_config_service_stub.cache_clear()
    stubs_mod.get_report_config_service_stub.cache_clear()
    stubs_mod.get_benchmark_config_service_stub.cache_clear()
    yield
    for clear in (stubs_mod.get_published_task_config_service_stub.cache_clear,
                  stubs_mod.get_report_config_service_stub.cache_clear,
                  stubs_mod.get_benchmark_config_service_stub.cache_clear,
                  channels_mod._get_task_channel.cache_clear,
                  channels_mod._get_report_channel.cache_clear):
        clear()


@pytest.fixture()
def benchmark_gateway(monkeypatch, db, storage_env, fake_redis, benchmark_chain):
    """网关 HTTP TestClient：init_db/服务注册 no-op，路由/中间件/ACL/代理全真实。"""
    import api_gateway.app as gateway_app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(gateway_app, 'init_db', lambda *a, **k: None)

    class _FakeRegistry:
        def __init__(self, *a, **k):
            pass

        def register(self, *a, **k):
            pass

    monkeypatch.setattr(gateway_app, 'RedisServiceRegistry', _FakeRegistry)

    with TestClient(gateway_app.app) as client:
        yield client


def _seed_publishable_task_with_report(wer_value=7.2):
    """写入可发布源任务 + 已完成报告（维度值 WER），返回 task_id。"""
    from shared.models.database import get_db_session
    from shared.utils.status_constants import TaskStatus
    from task_service.infrastructure.persistence.models import Task, TaskCase
    from task_service.infrastructure.persistence.models.testcase_models import TestCase
    from report_service.infrastructure.persistence.models import (
        Report, ReportSummary, ReportSummaryMeta,
    )

    s = get_db_session()
    case = TestCase(id=f'BENCH-{uuid.uuid4().hex[:12]}', name='基准用例',
                    config={})
    s.add(case)
    task = Task(name='双轨排行基准任务', description=None,
                status=TaskStatus.COMPLETED, total_cases=1, completed_cases=1)
    s.add(task)
    s.flush()
    s.add(TaskCase(task_id=task.id, test_case_id=case.id, status='completed'))
    report = Report(name='基准报告', type='task', task_id=task.id, status='completed')
    s.add(report)
    s.flush()
    s.add(ReportSummary(report_id=report.id, total_cases=1, completed_cases=1))
    s.add(ReportSummaryMeta(
        report_id=report.id,
        dimension_values=json.dumps([{'name': 'WER', 'average_value': wer_value}]),
        devices=json.dumps([{'id': 1, 'name': '测试手机', 'app_name': 'Moshi', 'type': 'phone'}]),
        apis=json.dumps([]),
    ))
    s.commit()
    return task.id


def _seed_wer_mapping():
    """写入 WER 指标映射（真实 DB）。"""
    from shared.models.database import get_db_session
    from report_service.infrastructure.persistence.models import BenchmarkMetricMapping

    s = get_db_session()
    mapping = BenchmarkMetricMapping(
        dimension_name='WER', metric_code='WER', metric_name='Word Error Rate',
        unit='%', direction='lower_is_better', scenario_tags=['普通话通用'], active=True)
    s.add(mapping)
    s.commit()
    return mapping.id


class TestBenchmarkRealChain:
    def test_full_dual_track_chain(self, benchmark_gateway):
        client = benchmark_gateway

        # ---- 准备：可发布任务（带报告快照素材）+ WER 指标映射 ----
        task_id = _seed_publishable_task_with_report(wer_value=7.2)
        _seed_wer_mapping()

        # ---- 1. 发布已发布任务（benchmark=true + suite/category 进快照）----
        resp = client.post('/api/v1/published-tasks', json={
            'sourceTaskId': task_id, 'name': '双轨排行基准任务',
            'benchmark': True, 'benchmarkSuite': 'librispeech-v1',
            'benchmarkCategory': 'asr',
        })
        assert resp.status_code == 201, resp.text
        pt_id = resp.json()['data']['id']

        # 快照携带 Benchmark 分组字段（设计文档 §6.2）
        detail = client.get(f'/api/v1/published-tasks/{pt_id}').json()['data']
        assert detail['benchmark'] is True
        assert detail['snapshot_config']['benchmarkSuite'] == 'librispeech-v1'
        assert detail['snapshot_config']['benchmarkCategory'] == 'asr'
        assert detail['report_snapshot']['summary']['dimensionValues'] == [
            {'name': 'WER', 'average_value': 7.2}]

        # ---- 2. 创建数据源 + 导入外部基线（Moshi 6.0 + Whisper 8.5）----
        source = client.post('/api/v1/benchmarks/sources', json={
            'name': 'Open ASR Leaderboard', 'provider': 'Hugging Face',
            'sourceType': 'official', 'url': 'https://huggingface.co/spaces/hf-audio/open_asr_leaderboard',
        })
        assert source.status_code == 201, source.text
        source_id = source.json()['data']['id']

        entries = [
            {'modelName': 'Moshi', 'vendor': 'Kyutai', 'metricCode': 'WER',
             'value': 6.0, 'unit': '%', 'direction': 'lower_is_better',
             'scenarioTags': ['普通话通用'], 'sampleSize': 500, 'metricDate': '2026-08-01'},
            {'modelName': 'Whisper', 'vendor': 'OpenAI', 'metricCode': 'WER',
             'value': 8.5, 'unit': '%', 'direction': 'lower_is_better',
             'scenarioTags': ['普通话通用'], 'sampleSize': 500, 'metricDate': '2026-08-01'},
        ]
        imported = client.post('/api/v1/benchmarks/baselines', json={
            'sourceId': source_id, 'category': 'asr', 'entries': entries,
        })
        assert imported.status_code == 201, imported.text
        body = imported.json()
        assert body['data']['version'] == 1 and body['data']['entry_count'] == 2

        # ---- 3. 重复导入幂等：同内容 → 返回 v1，不新建版本 ----
        again = client.post('/api/v1/benchmarks/baselines', json={
            'sourceId': source_id, 'category': 'asr', 'entries': entries,
        })
        assert again.status_code == 201
        assert again.json()['data']['is_new_version'] is False
        assert again.json()['data']['version'] == 1

        # ---- 4. 排行计算（全链路：HTTP → gRPC → 双轨采集 → 6 算法 → ReadModel）----
        computed = client.post('/api/v1/benchmarks/ranking/compute', json={})
        assert computed.status_code == 200, computed.text
        compute_data = computed.json()['data']
        assert compute_data['rows_written'] == 3  # Moshi 实测 + Moshi 导入 + Whisper 导入

        # ---- 5. 排行查询（验收标准 1：双轨合并，口径一致）----
        ranking = client.get('/api/v1/benchmarks/ranking',
                             params={'category': 'asr', 'metricCode': 'WER'}).json()['data']['items']
        assert len(ranking) == 3
        by = {(r['subject_name'], r['source']): r for r in ranking}

        moshi_pt = by[('Moshi', 'platform_test')]
        moshi_ext = by[('Moshi', 'external_import')]
        whisper = by[('Whisper', 'external_import')]

        # 实测轨行：引用已发布任务版本与报告
        assert moshi_pt['published_task_id'] == pt_id
        assert moshi_pt['published_task_version'] == 1
        assert moshi_pt['metric_value'] == 7.2
        assert moshi_pt['benchmark_suite'] == 'librispeech-v1'
        assert moshi_pt['device_type'] == 'physical' and moshi_pt['subject_type'] == 'app'
        # 排名以实测值参与排序：Moshi 7.2 < Whisper 8.5（lower_is_better）
        assert moshi_pt['rank'] == 1 and whisper['rank'] == 2
        assert moshi_pt['total'] == whisper['total'] == 2
        # 双轨并存：delta = 实测 7.2 - 导入 6.0 = 1.2（两行同值承载）
        assert moshi_pt['delta_external'] == pytest.approx(1.2)
        assert moshi_ext['delta_external'] == pytest.approx(1.2)
        # 无实测值时以导入值参与排序（Whisper 只有导入值）
        assert whisper['metric_value'] == 8.5 and whisper['baseline_id'] is not None
        # 来源筛选
        only_platform = client.get('/api/v1/benchmarks/ranking',
                                   params={'source': 'platform_test'}).json()['data']['items']
        assert [r['subject_name'] for r in only_platform] == ['Moshi']

        # ---- 6. 新版本导入：v2 追加，v1 不可变（内容不变，is_current 翻转）----
        v2_entries = [{'modelName': 'Moshi', 'vendor': 'Kyutai', 'metricCode': 'WER',
                       'value': 5.8, 'unit': '%', 'direction': 'lower_is_better',
                       'scenarioTags': ['普通话通用']}]
        v2 = client.post('/api/v1/benchmarks/baselines/version', json={
            'sourceId': source_id, 'category': 'asr', 'entries': v2_entries,
        })
        assert v2.status_code == 201
        assert v2.json()['data']['version'] == 2 and v2.json()['data']['is_new_version'] is True

        from shared.models.database import get_db_session
        from report_service.infrastructure.persistence.models import BenchmarkBaseline
        s = get_db_session()
        v1_rows = s.query(BenchmarkBaseline).filter_by(
            source_id=source_id, category='asr', version=1).all()
        assert all(r.is_current is False for r in v1_rows)
        assert all(r.value == 6.0 or r.model_name == 'Whisper' for r in v1_rows)  # 内容未修改
        v2_rows = s.query(BenchmarkBaseline).filter_by(
            source_id=source_id, category='asr', version=2).all()
        assert all(r.is_current is True for r in v2_rows)
        s.close()

        # 当前生效版本查询只返回 v2
        current = client.get('/api/v1/benchmarks/baselines',
                             params={'category': 'asr'}).json()['data']
        assert current['total'] == 1
        assert current['items'][0]['version'] == 2

        # ---- 7. 指标映射查询与排行重算幂等 ----
        mappings = client.get('/api/v1/benchmarks/metric-mappings').json()['data']
        assert any(m['metric_code'] == 'WER' for m in mappings['items'])

        recompute = client.post('/api/v1/benchmarks/ranking/compute', json={})
        assert recompute.status_code == 200
        recompute_rows = client.get('/api/v1/benchmarks/ranking',
                                    params={'category': 'asr', 'metricCode': 'WER'}).json()['data']['items']
        # 幂等重算不产生重复记录；v2 快照后 Whisper 不在当前版本 → 不再参与排行
        assert {(r['subject_name'], r['source']) for r in recompute_rows} == {
            ('Moshi', 'platform_test'), ('Moshi', 'external_import')}
        by_after = {(r['subject_name'], r['source']): r for r in recompute_rows}
        assert by_after[('Moshi', 'external_import')]['metric_value'] == 5.8
        assert by_after[('Moshi', 'platform_test')]['delta_external'] == pytest.approx(1.4)

        # ---- 8. 被测主体列表（v2 快照后 Whisper 已退出当前排行）----
        subjects = client.get('/api/v1/benchmarks/ranking/subjects').json()['data']
        assert set(subjects['items']) == {'Moshi'}


def _seed_voice_llm_task_with_report(dim_name='逐轮话轮评估', value=0.85):
    """写入 voice_llm 主链形态的源任务 + 报告（API 被测 + LLM 裁判维度值）。"""
    from shared.models.database import get_db_session
    from shared.utils.status_constants import TaskStatus
    from task_service.infrastructure.persistence.models import Task, TaskCase
    from task_service.infrastructure.persistence.models.testcase_models import TestCase
    from report_service.infrastructure.persistence.models import (
        Report, ReportSummary, ReportSummaryMeta,
    )

    s = get_db_session()
    case = TestCase(id=f'VLLM-{uuid.uuid4().hex[:12]}', name='voice_llm 基准用例',
                    config={})
    s.add(case)
    task = Task(name='voice_llm 双轨排行基准任务', description=None,
                status=TaskStatus.COMPLETED, total_cases=1, completed_cases=1)
    s.add(task)
    s.flush()
    s.add(TaskCase(task_id=task.id, test_case_id=case.id, status='completed'))
    report = Report(name='voice_llm 基准报告', type='task', task_id=task.id,
                    status='completed')
    s.add(report)
    s.flush()
    s.add(ReportSummary(report_id=report.id, total_cases=1, completed_cases=1))
    s.add(ReportSummaryMeta(
        report_id=report.id,
        dimension_values=json.dumps([{'name': dim_name, 'average_value': value}]),
        devices=json.dumps([]),
        apis=json.dumps([{'id': 19, 'name': 'INT95验收API(mock DUT)', 'type': 'http'}]),
    ))
    s.commit()
    return task.id


class TestMappingCreateRealChain:
    """映射创建 API 真实链路（实机 no_mapping 空转缺陷的回归锚点）：

    LLM 裁判维度名由用户运行期定义，种子无法预置时须能经 API 运行期补映射，
    重算后实测数据进榜（主链验收第 7 步：发布 → 排行 ReadModel 出现实测数据）。
    """

    def test_runtime_mapping_create_unblocks_platform_ranking(self, benchmark_gateway):
        client = benchmark_gateway
        dim_name = '逐轮话轮评估'

        task_id = _seed_voice_llm_task_with_report(dim_name=dim_name, value=0.85)
        resp = client.post('/api/v1/published-tasks', json={
            'sourceTaskId': task_id, 'name': 'voice_llm 基准任务',
            'benchmark': True, 'benchmarkCategory': 'voice_llm',
        })
        assert resp.status_code == 201, resp.text

        # 缺陷形态：维度无映射 → no_mapping 跳过，ReadModel 0 行
        before = client.post('/api/v1/benchmarks/ranking/compute', json={})
        assert before.status_code == 200, before.text
        assert before.json()['data']['rows_written'] == 0
        assert {'subject': 'INT95验收API(mock DUT)', 'metric': dim_name,
                'reason': 'no_mapping'} in before.json()['data']['skipped']
        assert 'no_mapping' in before.json()['message']

        # 运行期经创建 API 补映射（camelCase 请求体）
        created = client.post('/api/v1/benchmarks/metric-mappings', json={
            'dimensionName': dim_name, 'metricCode': 'TURN_EVAL',
            'metricName': '逐轮话轮评估', 'direction': 'higher_is_better',
            'scenarioTags': ['通用'],
        })
        assert created.status_code == 201, created.text
        assert created.json()['data']['dimension_name'] == dim_name

        # 同维度重复创建 → 409 冲突（同一维度仅一条映射）
        dup = client.post('/api/v1/benchmarks/metric-mappings', json={
            'dimensionName': dim_name, 'metricCode': 'TURN_EVAL',
            'direction': 'higher_is_better',
        })
        assert dup.status_code == 409, dup.text

        # 参数校验：缺 metric_code / 方向非法 → 400
        assert client.post('/api/v1/benchmarks/metric-mappings', json={
            'dimensionName': '拒识场景裁判', 'direction': 'higher_is_better',
        }).status_code == 400
        assert client.post('/api/v1/benchmarks/metric-mappings', json={
            'dimensionName': '拒识场景裁判', 'metricCode': 'REFUSAL_JUDGE',
            'direction': '任意',
        }).status_code == 400

        # 补映射后重算：实测数据进榜（主链验收标准达成）
        after = client.post('/api/v1/benchmarks/ranking/compute', json={
            'source': 'platform_test'})
        assert after.status_code == 200, after.text
        assert after.json()['data']['rows_written'] == 1

        rows = client.get('/api/v1/benchmarks/ranking', params={
            'category': 'voice_llm', 'metricCode': 'TURN_EVAL',
        }).json()['data']['items']
        assert len(rows) == 1
        row = rows[0]
        assert row['source'] == 'platform_test'
        assert row['subject_name'] == 'INT95验收API(mock DUT)'
        assert row['metric_value'] == pytest.approx(0.85)
        assert row['direction'] == 'higher_is_better'
        assert row['device_type'] == 'http_api'
        assert row['scenario_key'] == '通用'
        assert row['rank'] == 1 and row['total'] == 1

        # 映射列表可查到新映射
        mappings = client.get('/api/v1/benchmarks/metric-mappings').json()['data']
        assert any(m['metric_code'] == 'TURN_EVAL' and m['dimension_name'] == dim_name
                   for m in mappings['items'])
