# -*- coding: utf-8 -*-
"""任务数据导入导出 —— 真实链路回归（INT-25 复验补充）

关闭进程内夹具的盲区（缺陷 3/4 教训：替身绕过 gRPC 序列化与包导入层）：
- 启动 task/evaluation/report 三个真实 gRPC server（临时端口 + 生产同款拦截器），
  共享 channel 地址指到本进程；
- 网关 HTTP（FastAPI TestClient，AUTH_MODE=dev 默认 off）→ ACL → gRPC → 各服务
  应用服务全链路走真实代码：export 下载 ZIP → preview → import → progress；
- 直连 ACL 层的导入/回滚签名回归（timeout 必须是 gRPC 调用关键字参数，
  不允许再混入 Request 构造参数）。
"""
import io
import json
import os
import zipfile
from concurrent import futures
from datetime import datetime

# BaseConfig 在 import 时校验环境变量（测试环境无 .env），先补齐必需项。
# AUTH_MODE 显式置 off：TestClient 免登录打网关路由（覆盖 .env 可能带入的 dev/on）。
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ['AUTH_MODE'] = 'off'

import grpc
import pytest

from tests.integration.test_data_transfer_roundtrip import (  # noqa: F401
    db,
    fake_redis,
    storage_env,
)
from tests.integration.test_data_transfer_roundtrip import _seed


@pytest.fixture()
def grpc_servers():
    """本进程内启动三个真实 gRPC server（临时端口），含生产同款 DB scope/日志拦截器。

    函数级作用域：每测新建 worker 线程，避免跨测试时线程局部 scoped_session
    绑在上一测已销毁的 engine 上（sqlite 文件被删 → no such table）。
    """
    from shared.infrastructure.grpc_interceptors import (
        server_db_scope_interceptor,
        server_log_interceptor,
    )
    from shared.proto import evaluation_service_pb2_grpc as eval_grpc
    from shared.proto import report_service_pb2_grpc as report_grpc
    from shared.proto import task_service_pb2_grpc as task_grpc
    from evaluation_service.interfaces.grpc.evaluation_data_servicer import (
        EvaluationDataServiceServicer,
    )
    from report_service.interfaces.grpc.servicers import ReportServicer
    from task_service.interfaces.grpc.data_transfer import DataTransferServiceServicer

    def _start(servicer, add_fn):
        server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=8),
            interceptors=[server_db_scope_interceptor, server_log_interceptor])
        add_fn(servicer, server)
        port = server.add_insecure_port('[::]:0')
        server.start()
        return server, port

    task_server, task_port = _start(
        DataTransferServiceServicer(), task_grpc.add_DataTransferServiceServicer_to_server)
    eval_server, eval_port = _start(
        EvaluationDataServiceServicer(), eval_grpc.add_EvaluationDataServiceServicer_to_server)
    report_server, report_port = _start(
        ReportServicer(), report_grpc.add_ReportConfigServiceServicer_to_server)

    yield {'task': task_port, 'eval': eval_port, 'report': report_port}

    for server in (task_server, eval_server, report_server):
        server.stop(grace=None).wait(timeout=5)


@pytest.fixture()
def grpc_chain(grpc_servers, db, storage_env, fake_redis, monkeypatch):
    """共享 channel/stub 指向本进程内 server（清 lru_cache），测试后还原"""
    import shared.clients._grpc_channels as channels_mod
    import shared.clients._grpc_stubs as stubs_mod

    monkeypatch.setattr(channels_mod, 'TASK_GRPC_ADDR', f'localhost:{grpc_servers["task"]}')
    monkeypatch.setattr(channels_mod, 'EVALUATION_GRPC_ADDR', f'localhost:{grpc_servers["eval"]}')
    monkeypatch.setattr(channels_mod, 'REPORT_GRPC_ADDR', f'localhost:{grpc_servers["report"]}')
    for name in ('_get_task_channel', '_get_evaluation_channel', '_get_report_channel'):
        getattr(channels_mod, name).cache_clear()
    for name in ('get_data_transfer_service_stub', 'get_evaluation_data_service_stub',
                 'get_report_config_service_stub'):
        getattr(stubs_mod, name).cache_clear()
    yield grpc_servers
    for name in ('get_data_transfer_service_stub', 'get_evaluation_data_service_stub',
                 'get_report_config_service_stub'):
        getattr(stubs_mod, name).cache_clear()
    for name in ('_get_task_channel', '_get_evaluation_channel', '_get_report_channel'):
        getattr(channels_mod, name).cache_clear()


@pytest.fixture()
def gateway_client(monkeypatch, db, storage_env, fake_redis, grpc_chain):
    """网关 HTTP TestClient：init_db/服务注册替换为 no-op（DB 由 db 夹具装配，
    Redis 由 fake_redis 替身），路由/中间件/ACL/代理全部真实代码"""
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


def _zip_bytes_from_response(response) -> bytes:
    assert response.status_code == 200, response.text[:300]
    assert response.headers['content-type'].startswith('application/zip')
    return response.content


class TestGatewayHttpRealChain:
    """网关 HTTP → ACL → gRPC → 各服务：export/preview/import/progress 四路由全链路"""

    def test_export_preview_import_progress(self, gateway_client, db, storage_env,
                                            fake_redis, grpc_chain):
        _seed(db, storage_env)

        # ---- POST /export：网关 → task_service DataTransferService → 导出引擎
        resp = gateway_client.post('/api/v1/data-transfer/export', json={'task_ids': [1, 2]})
        zip_bytes = _zip_bytes_from_response(resp)
        disposition = resp.headers.get('content-disposition', '')
        assert 'task_export_' in disposition
        buf = io.BytesIO(zip_bytes)
        assert zipfile.is_zipfile(buf)
        with zipfile.ZipFile(buf) as zf:
            manifest = json.loads(zf.read('manifest.json'))
            assert manifest['version'] == '1.0'
            assert manifest['stats']['taskCount'] == 2
            assert len([n for n in zf.namelist() if n.startswith('db/')]) == 15

        # ---- POST /import/preview：同库导入 → 任务 ID 冲突清单
        resp = gateway_client.post(
            '/api/v1/data-transfer/import/preview',
            files={'file': ('task_export.zip', zip_bytes, 'application/zip')})
        assert resp.status_code == 200, resp.text[:300]
        body = resp.json()
        assert body['success'] is True, body.get('message')
        task_conflicts = {c['id'] for c in body['data']['conflicts']
                          if c['table'] == 'test_tasks'}
        assert task_conflicts == {1, 2}

        # ---- POST /import：全链路执行（task 段 → 维度段 gRPC → 报告段 gRPC → 文件）
        resp = gateway_client.post(
            '/api/v1/data-transfer/import',
            files={'file': ('task_export.zip', zip_bytes, 'application/zip')})
        assert resp.status_code == 200, resp.text[:300]
        body = resp.json()
        assert body['success'] is True, body.get('message')
        stats = body['data']
        assert stats['importedTasks'] == 2
        assert stats['importedResults'] == 2
        assert stats['importedDimensions'] == 1
        assert stats['importedReports'] == 1
        assert sorted(int(k) for k in stats['remappedIds']['tasks']) == [1, 2]

        # ---- GET /import/progress：快照兜底（进度经真实发布链路写入）
        resp = gateway_client.get('/api/v1/data-transfer/import/progress')
        assert resp.status_code == 200, resp.text[:300]
        body = resp.json()
        assert body['success'] is True
        assert body['data']['step'] == 'done'

        # ---- DB 终态：导入任务 completed、维度/报告挂新 ID
        from shared.models.database import get_db_session
        from evaluation_service.infrastructure.persistence.models import TestResultDimension
        from report_service.infrastructure.persistence.models import Report
        from task_service.infrastructure.persistence.models import Task, TestResult
        session = get_db_session()
        try:
            tasks = {t.id: t for t in session.query(Task).all()}
            new_ids = {int(k) for k in stats['remappedIds']['tasks'].values()}
            assert new_ids <= set(tasks)
            assert all(tasks[tid].status == 'completed' for tid in new_ids)
            assert session.query(TestResult).count() == 4
            assert session.query(TestResultDimension).count() == 2
            reports = session.query(Report).all()
            assert len(reports) == 2
            assert all(r.task_id in set(tasks) for r in reports)
        finally:
            session.close()


class TestRealAclSignatures:
    """ACL 层直连 gRPC 回归：导入/回滚调用签名（timeout 为调用关键字参数）与链路连通"""

    def test_evaluation_acl_import_rollback(self, grpc_chain, db, storage_env, fake_redis):
        _seed(db, storage_env)
        from task_service.infrastructure.acl.evaluation_transfer_acl import (
            evaluation_transfer_acl_repository,
        )
        row = {'id': 999901, 'test_result_id': 100, 'dimension_id': 1,
               'algorithm_type': 'translation', 'round_number': 0,
               'dimension_value': 1.0, 'score': 90.0, 'evaluation_status': 'completed',
               'created_at': datetime.now().isoformat(timespec='seconds')}
        result = evaluation_transfer_acl_repository.import_dimensions(
            [row], {}, 'chain-batch-eval')
        assert result['imported'] == 1

        exported = evaluation_transfer_acl_repository.export_dimensions_for_tasks([100])
        assert len(exported['dimensions']) == 2  # 种子 200 + 链路写入 999901

        rolled = evaluation_transfer_acl_repository.rollback_dimension_import('chain-batch-eval')
        assert rolled['deleted'] == 1

    def test_report_acl_import_rollback(self, grpc_chain, db, storage_env, fake_redis):
        _seed(db, storage_env)
        from task_service.infrastructure.acl.report_transfer_acl import (
            report_transfer_acl_repository,
        )
        now = datetime.now().isoformat(timespec='seconds')
        tables = {'test_reports': [{'id': 999902, 'name': '链路冒烟报告', 'type': 'standard',
                                    'task_id': 1, 'status': 'completed', 'deleted': False,
                                    'created_at': now, 'updated_at': now}]}
        result = report_transfer_acl_repository.import_reports(tables, {}, 'chain-batch-report')
        assert result['imported'] == 1

        exported = report_transfer_acl_repository.export_reports_for_tasks([1])
        assert len(exported['test_reports']) == 2  # 种子 300 + 链路写入 999902

        rolled = report_transfer_acl_repository.rollback_report_import('chain-batch-report')
        assert rolled['deleted']['test_reports'] == 1
