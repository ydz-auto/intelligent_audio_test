# -*- coding: utf-8 -*-
"""Benchmark 报告发布 —— gRPC 真实链路验收（INT-481）

全链路走真实代码：
gRPC stub → 进程内真实 report BenchmarkConfigService server（生产同款拦截器）
→ servicer → 应用服务 → 真仓储 → SQLite 临时库；报告主记录复用真 report_repository。

覆盖验收标准：
- POST/GET 端点实测走通：CreateBenchmarkReport → ListBenchmarkReports →
  GetBenchmarkReport 三 RPC 经真实 gRPC server 贯通
- report_type='benchmark' 报告主记录生成（test_reports 7 表结构）
- 排行快照与 benchmark_rankings ReadModel 一致（发布时点定格）
"""
import json
import os
import tempfile
from datetime import datetime

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ['AUTH_MODE'] = 'off'

from concurrent import futures

import grpc
import pytest

from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    return 'INTEGER'


from tests.integration.test_data_transfer_roundtrip import (  # noqa: F401
    db,
    fake_redis,
    storage_env,
)


@pytest.fixture()
def report_grpc_server(db):
    """进程内启动真实 report BenchmarkConfigService gRPC server。"""
    from shared.infrastructure.grpc_interceptors import (
        server_db_scope_interceptor,
        server_log_interceptor,
        server_user_context_interceptor,
    )
    from shared.proto import report_service_pb2_grpc as report_grpc
    from report_service.interfaces.grpc.servicers import BenchmarkServicer

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=4),
        interceptors=[server_db_scope_interceptor, server_log_interceptor,
                     server_user_context_interceptor])
    report_grpc.add_BenchmarkConfigServiceServicer_to_server(
        BenchmarkServicer(), server)
    report_port = server.add_insecure_port('[::]:0')
    server.start()
    yield report_port
    server.stop(grace=None).wait(timeout=5)


@pytest.fixture()
def report_chain(report_grpc_server, monkeypatch):
    """channel/stub 指向进程内 report server（清 lru_cache），测试后还原。"""
    port = report_grpc_server
    import shared.clients._grpc_channels as channels_mod
    import shared.clients._grpc_stubs as stubs_mod

    monkeypatch.setattr(channels_mod, 'REPORT_GRPC_ADDR', f'localhost:{port}')
    channels_mod._get_report_channel.cache_clear()
    stubs_mod.get_benchmark_config_service_stub.cache_clear()
    yield
    stubs_mod.get_benchmark_config_service_stub.cache_clear()
    channels_mod._get_report_channel.cache_clear()


def _rank_row(subject, metric='WER', category='asr', suite='librispeech-v1',
              source='platform_test', pt_id=1, value=5.0):
    return {
        'source': source, 'published_task_id': pt_id, 'published_task_version': 1,
        'report_id': (100 + pt_id) if pt_id is not None else None,
        'baseline_id': None, 'subject_name': subject,
        'subject_type': 'app', 'device_type': 'physical', 'benchmark_suite': suite,
        'category': category, 'metric_code': metric, 'metric_name': metric,
        'metric_value': value, 'unit': '%', 'direction': 'lower_is_better',
        'rank': 1, 'total': 2, 'percentile': 50.0, 'score100': 90.0,
        'gap_best': 0.0, 'gap_median': 0.5, 'delta_external': None,
        'scenario_key': '通用', 'computed_at': datetime(2026, 10, 16, 0, 0, 0),
    }


def _seed_report(report_id, deleted=False):
    """写入 test_reports 行，使排行行 report_id 指向存在的报告（INT-1218 可见性过滤）。"""
    from report_service.infrastructure.persistence.models import Report
    from shared.models.database import get_db_session
    s = get_db_session()
    po = Report(id=report_id, name=f'bench-report-{report_id}', type='task',
                status='completed', deleted=deleted)
    s.add(po)
    s.commit()
    s.close()


class TestBenchmarkReportRealChain:
    def test_report_publish_roundtrip_via_grpc(self, db, report_chain):
        from shared.clients.grpc_clients import get_benchmark_config_service_stub
        from shared.proto import report_service_pb2 as report_pb
        from report_service.infrastructure.persistence.benchmark_repository import (
            BenchmarkRepositoryImpl,
        )
        from report_service.infrastructure.persistence.models import Report
        from shared.models.database import get_db_session

        # ---- 准备：排行 ReadModel（2 行实测） ----
        repo = BenchmarkRepositoryImpl()
        _seed_report(101)  # _rank_row(pt_id=1) → report_id=101（INT-1218 可见性过滤）
        _seed_report(102)  # _rank_row(pt_id=2) → report_id=102
        repo.replace_ranking_rows(
            [{'category': 'asr', 'metric_code': 'WER', 'scenario_key': '通用',
              'source': 'platform_test'}],
            [_rank_row('Moshi', category='asr', suite='librispeech-v1', pt_id=1),
             _rank_row('Nova', category='asr', suite='librispeech-v1', pt_id=2)])

        stub = get_benchmark_config_service_stub()

        # ---- 发布（真实 gRPC server） ----
        resp = stub.CreateBenchmarkReport(report_pb.BenchmarkCommandRequest(
            data=json.dumps({'suite': 'librispeech-v1', 'category': 'asr',
                             'name': 'ASR 2026Q3', 'publishedBy': 'tester'},
                            ensure_ascii=False)))
        assert resp.success is True, resp.message
        record = json.loads(resp.data)
        record_id = record['id']
        report_id = record['report_id']
        assert record['published_task_count'] == 2
        assert record['subject_count'] == 2
        assert record['metric_count'] == 1
        assert record['version'] == 1

        # 报告主记录：report_type='benchmark'（复用报告 7 表结构）
        s = get_db_session()
        po = s.query(Report).filter(Report.id == report_id).first()
        assert po.type == 'benchmark'
        assert po.status == 'published'
        assert po.name == 'ASR 2026Q3'
        s.close()

        # ---- 列表 ----
        list_resp = stub.ListBenchmarkReports(report_pb.BenchmarkQueryRequest(
            data=json.dumps({'category': 'asr'})))
        assert list_resp.success is True
        listed = json.loads(list_resp.data)
        assert listed['total'] == 1
        assert listed['items'][0]['id'] == record_id
        assert 'ranking_data' not in listed['items'][0]  # 列表不带大体积快照

        # ---- 详情（含排行快照，与 ReadModel 一致） ----
        get_resp = stub.GetBenchmarkReport(report_pb.BenchmarkQueryRequest(
            data=json.dumps({'reportId': record_id})))
        assert get_resp.success is True
        detail = json.loads(get_resp.data)
        assert detail['report_id'] == report_id
        assert detail['ranking_data']['counts']['row_count'] == 2
        subjects = {r['subject_name'] for r in detail['ranking_data']['rows']}
        assert subjects == {'Moshi', 'Nova'}

        # ---- 404 ----
        missing = stub.GetBenchmarkReport(report_pb.BenchmarkQueryRequest(
            data=json.dumps({'reportId': 999})))
        assert missing.success is False
        assert missing.code == 404

    def test_report_publish_filters_snapshot_by_source(self, db, report_chain):
        """发布按 source 筛选：仅快照该来源排行行，计数正确。"""
        from shared.clients.grpc_clients import get_benchmark_config_service_stub
        from shared.proto import report_service_pb2 as report_pb
        from report_service.infrastructure.persistence.benchmark_repository import (
            BenchmarkRepositoryImpl,
        )

        repo = BenchmarkRepositoryImpl()
        _seed_report(101)  # _rank_row(pt_id=1) → report_id=101（INT-1218 可见性过滤）
        repo.replace_ranking_rows(
            [{'category': 'asr', 'metric_code': 'WER', 'scenario_key': '通用',
              'source': 'platform_test'}],
            [_rank_row('Moshi', category='asr', suite='librispeech-v1', pt_id=1)])
        repo.replace_ranking_rows(
            [{'category': 'asr', 'metric_code': 'WER', 'scenario_key': '通用',
              'source': 'external_import'}],
            [_rank_row('Moshi', category='asr', suite='librispeech-v1', pt_id=None,
                       source='external_import', value=6.0)])

        stub = get_benchmark_config_service_stub()
        resp = stub.CreateBenchmarkReport(report_pb.BenchmarkCommandRequest(
            data=json.dumps({'source': 'external_import'})))
        assert resp.success is True
        record = json.loads(resp.data)
        # 仅外部轨：无正式任务（published_task_count=0），1 主体
        assert record['published_task_count'] == 0
        assert record['subject_count'] == 1
        assert record['ranking_data']['rows'][0]['source'] == 'external_import'
