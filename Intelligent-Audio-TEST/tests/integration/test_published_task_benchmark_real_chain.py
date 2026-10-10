# -*- coding: utf-8 -*-
"""已发布任务 Benchmark 标记 —— 网关 HTTP 真实链路验收（INT-26 测试工程师独立验收）

补齐提测说明中自认未覆盖的「网关 HTTP 实测」缺口，全链路走真实代码：
网关路由/schema → ACL 代理 → gRPC（进程内真实 server，生产同款拦截器）
→ task_service 应用服务 → 仓储 → DB（SQLite 临时库，模型表全量建）。

覆盖验收标准：
1. 发布可携带 benchmark 标记并持久化；snapshot_config 不被写入标记（快照不可变语义）
2. 网关 GET /published-tasks?benchmark= 三态过滤（true/false/缺省/非法值 400/大小写归一）
3. 审计事件 PUBLISHED_TASK_BENCHMARK_MARKED 落库 logs（module/level/category/content）
4. 新版本继承/显式覆盖、归档保留标记（状态机兼容）
"""
import os
import uuid

# BaseConfig 在 import 时校验环境变量（测试环境无 .env），先补齐必需项。
# AUTH_MODE 显式置 off：TestClient 免登录打网关路由。
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ['AUTH_MODE'] = 'off'

from concurrent import futures
from datetime import datetime

import grpc
import pytest

from tests.integration.test_data_transfer_roundtrip import (  # noqa: F401
    db,
    fake_redis,
    storage_env,
)


@pytest.fixture()
def pt_grpc_server(db):
    """进程内启动真实 PublishedTaskConfigServiceServicer（临时端口，生产同款拦截器）。

    依赖 db 夹具先行装配 engine，拦截器的 scoped_session 才绑定到本测临时库。
    """
    from shared.infrastructure.grpc_interceptors import (
        server_db_scope_interceptor,
        server_log_interceptor,
    )
    from shared.proto import task_service_pb2_grpc as task_grpc
    from task_service.interfaces.grpc.published_task_config import (
        PublishedTaskConfigServiceServicer,
    )

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=8),
        interceptors=[server_db_scope_interceptor, server_log_interceptor])
    task_grpc.add_PublishedTaskConfigServiceServicer_to_server(
        PublishedTaskConfigServiceServicer(), server)
    port = server.add_insecure_port('[::]:0')
    server.start()
    yield port
    server.stop(grace=None).wait(timeout=5)


@pytest.fixture()
def pt_chain(pt_grpc_server, monkeypatch):
    """共享 channel/stub 指向进程内 published_task server（清 lru_cache），测试后还原"""
    import shared.clients._grpc_channels as channels_mod
    import shared.clients._grpc_stubs as stubs_mod

    monkeypatch.setattr(channels_mod, 'TASK_GRPC_ADDR', f'localhost:{pt_grpc_server}')
    channels_mod._get_task_channel.cache_clear()
    stubs_mod.get_published_task_config_service_stub.cache_clear()
    yield pt_grpc_server
    stubs_mod.get_published_task_config_service_stub.cache_clear()
    channels_mod._get_task_channel.cache_clear()


@pytest.fixture()
def pt_gateway(monkeypatch, db, storage_env, fake_redis, pt_chain):
    """网关 HTTP TestClient：init_db/服务注册替换为 no-op，路由/中间件/ACL/代理全真实"""
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


def _seed_publishable_task():
    """写入一个可发布源任务（completed + 1 用例），返回 task_id。"""
    from shared.models.database import get_db_session
    from shared.utils.status_constants import (
        ExecutionStatus, EvaluationStatus, TaskCaseStatus, TaskStatus,
    )
    from task_service.infrastructure.persistence.models import Task, TaskCase
    from task_service.infrastructure.persistence.models.testcase_models import TestCase

    s = get_db_session()
    case = TestCase(id=f'PT-BENCH-{uuid.uuid4().hex[:12]}', name='基准用例',
                    config={})
    s.add(case)
    s.flush()
    now = datetime.now()
    task = Task(name='PT-BENCH-src', status=TaskStatus.COMPLETED,
                total_cases=1, completed_cases=1, failed_cases=0,
                created_at=now, updated_at=now)
    s.add(task)
    s.flush()
    s.add(TaskCase(task_id=task.id, test_case_id=case.id, status=TaskCaseStatus.COMPLETED,
                   execution_status=ExecutionStatus.COMPLETED,
                   evaluation_status=EvaluationStatus.COMPLETED, created_at=now))
    s.commit()
    task_id = task.id
    s.close()
    return task_id


def _published_rows(db, **filters):
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models import PublishedTask

    s = get_db_session()
    rows = s.query(PublishedTask).filter_by(**filters).all()
    s.close()
    return rows


def _audit_logs(db, published_task_id):
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models.system_models import Log

    s = get_db_session()
    rows = (s.query(Log)
            .filter(Log.module == 'published_task',
                    Log.content.like(f'%{published_task_id}%'))
            .all())
    s.close()
    return rows


class TestPublishBenchmarkRealChain:
    """验收标准 1+3：发布携带 benchmark 持久化 + 审计落库（网关 HTTP 全链路）"""

    def test_publish_benchmark_true_persists_and_audits(self, pt_gateway, db):
        task_id = _seed_publishable_task()
        resp = pt_gateway.post('/api/v1/published-tasks', json={
            'sourceTaskId': task_id, 'name': '基准发布-真', 'benchmark': True,
        })
        assert resp.status_code == 201, resp.text[:300]
        pt_id = resp.json()['data']['id']

        rows = _published_rows(db, id=pt_id)
        assert len(rows) == 1
        row = rows[0]
        assert row.benchmark is True
        assert row.version == 1 and row.is_current is True and row.status == 'published'
        # 快照不可变语义：benchmark 是行级标记，不写入冻结快照结构
        assert 'benchmark' not in (row.snapshot_config or {})

        logs = _audit_logs(db, pt_id)
        assert logs, 'benchmark=true 发布应写审计事件'
        audit = [l for l in logs if 'PUBLISHED_TASK_BENCHMARK_MARKED' in (l.content or '')]
        assert audit, f'审计内容缺事件名: {[l.content for l in logs]}'
        assert logs[0].level == 'INFO' and logs[0].category == 'System'
        assert str(pt_id) in audit[0].content

    def test_publish_without_benchmark_defaults_false_no_audit(self, pt_gateway, db):
        task_id = _seed_publishable_task()
        resp = pt_gateway.post('/api/v1/published-tasks', json={
            'sourceTaskId': task_id, 'name': '基准发布-缺省',
        })
        assert resp.status_code == 201, resp.text[:300]
        pt_id = resp.json()['data']['id']

        row = _published_rows(db, id=pt_id)[0]
        assert row.benchmark is False
        # 不带标记发布不产生 BENCHMARK_MARKED 审计
        # （INT-65 起仍无条件落 PUBLISHED_TASK_CREATED，见断言与单测 test_int65_published_task_audit）
        logs = _audit_logs(db, pt_id)
        benchmark_logs = [l for l in logs if 'PUBLISHED_TASK_BENCHMARK_MARKED' in (l.content or '')]
        created_logs = [l for l in logs if 'PUBLISHED_TASK_CREATED' in (l.content or '')]
        assert benchmark_logs == [], '不带标记发布不应产生 BENCHMARK_MARKED 审计'
        assert created_logs, '发布应无条件落 PUBLISHED_TASK_CREATED 审计（INT-65）'


class TestGatewayBenchmarkFilterRealChain:
    """验收标准 2：网关接口按 benchmark 标记过滤（三态 + 非法值 400）"""

    @pytest.fixture()
    def _two_published(self, pt_gateway, db):
        id_true = _seed_publishable_task()
        id_false = _seed_publishable_task()
        r1 = pt_gateway.post('/api/v1/published-tasks', json={
            'sourceTaskId': id_true, 'name': '基准-进榜', 'benchmark': True})
        r2 = pt_gateway.post('/api/v1/published-tasks', json={
            'sourceTaskId': id_false, 'name': '基准-不进榜'})
        assert r1.status_code == 201 and r2.status_code == 201, (r1.text, r2.text)
        return r1.json()['data']['id'], r2.json()['data']['id']

    def test_filter_true_false_and_default(self, pt_gateway, _two_published):
        id_true, id_false = _two_published

        items = pt_gateway.get('/api/v1/published-tasks', params={'benchmark': 'true'})
        assert items.status_code == 200, items.text[:300]
        ids = [i['id'] for i in items.json()['data']['items']]
        assert id_true in ids and id_false not in ids
        assert all(i['benchmark'] is True for i in items.json()['data']['items'])

        items = pt_gateway.get('/api/v1/published-tasks', params={'benchmark': 'false'})
        assert items.status_code == 200
        ids = [i['id'] for i in items.json()['data']['items']]
        assert id_false in ids and id_true not in ids
        assert all(i['benchmark'] is False for i in items.json()['data']['items'])

        items = pt_gateway.get('/api/v1/published-tasks')
        assert items.status_code == 200
        ids = {i['id'] for i in items.json()['data']['items']}
        assert {id_true, id_false} <= ids

    def test_filter_case_insensitive(self, pt_gateway, _two_published):
        id_true, id_false = _two_published
        resp = pt_gateway.get('/api/v1/published-tasks', params={'benchmark': 'TRUE'})
        assert resp.status_code == 200
        ids = [i['id'] for i in resp.json()['data']['items']]
        assert id_true in ids and id_false not in ids

    def test_filter_invalid_value_rejected_400(self, pt_gateway, _two_published):
        resp = pt_gateway.get('/api/v1/published-tasks', params={'benchmark': 'abc'})
        assert resp.status_code == 400, resp.text[:300]

    def test_filter_empty_value_means_no_filter(self, pt_gateway, _two_published):
        id_true, id_false = _two_published
        resp = pt_gateway.get('/api/v1/published-tasks', params={'benchmark': ''})
        assert resp.status_code == 200
        ids = {i['id'] for i in resp.json()['data']['items']}
        assert {id_true, id_false} <= ids


class TestVersionAndArchiveBenchmarkRealChain:
    """验收标准 1+4：新版本继承/覆盖、归档保留标记（状态机兼容）"""

    def test_version_inherits_then_overrides_with_audit(self, pt_gateway, db):
        task_id = _seed_publishable_task()
        r1 = pt_gateway.post('/api/v1/published-tasks', json={
            'sourceTaskId': task_id, 'name': '基准-版本链', 'benchmark': True})
        assert r1.status_code == 201, r1.text[:300]
        pt_id = r1.json()['data']['id']

        # v2：请求不带 benchmark → 继承 v1 的 true
        r2 = pt_gateway.post(f'/api/v1/published-tasks/{pt_id}/versions', json={})
        assert r2.status_code == 201, r2.text[:300]
        v2_id = r2.json()['data']['id']
        v2 = _published_rows(db, id=v2_id)[0]
        assert v2.version == 2 and v2.benchmark is True and v2.is_current is True
        assert _published_rows(db, id=pt_id)[0].is_current is False

        # v3：显式 benchmark=false → 覆盖为 false（且不写审计）
        r3 = pt_gateway.post(f'/api/v1/published-tasks/{pt_id}/versions',
                             json={'benchmark': False})
        assert r3.status_code == 201, r3.text[:300]
        v3_id = r3.json()['data']['id']
        v3 = _published_rows(db, id=v3_id)[0]
        assert v3.version == 3 and v3.benchmark is False and v3.is_current is True
        # v1/v2 各写过一次审计；v3 不带标记不得新增
        marked_logs = [l for l in _audit_logs(db, pt_id)
                       if 'PUBLISHED_TASK_BENCHMARK_MARKED' in (l.content or '')]
        assert len(marked_logs) == 2

        # v4：显式 benchmark=true（在 false 版本上重新标记）→ 覆盖为 true + 审计
        r4 = pt_gateway.post(f'/api/v1/published-tasks/{pt_id}/versions',
                             json={'benchmark': True})
        assert r4.status_code == 201, r4.text[:300]
        v4_id = r4.json()['data']['id']
        assert _published_rows(db, id=v4_id)[0].benchmark is True
        assert len([l for l in _audit_logs(db, pt_id)
                    if 'PUBLISHED_TASK_BENCHMARK_MARKED' in (l.content or '')]) == 3

    def test_archive_keeps_marker_and_detail_exposes_it(self, pt_gateway, db):
        task_id = _seed_publishable_task()
        r1 = pt_gateway.post('/api/v1/published-tasks', json={
            'sourceTaskId': task_id, 'name': '基准-归档', 'benchmark': True})
        assert r1.status_code == 201, r1.text[:300]
        pt_id = r1.json()['data']['id']

        ra = pt_gateway.post(f'/api/v1/published-tasks/{pt_id}/archive')
        assert ra.status_code == 200, ra.text[:300]

        row = _published_rows(db, id=pt_id)[0]
        assert row.status == 'archived' and row.benchmark is True, '归档不得清除标记'

        detail = pt_gateway.get(f'/api/v1/published-tasks/{pt_id}')
        assert detail.status_code == 200, detail.text[:300]
        data = detail.json()['data']
        assert data['status'] == 'archived' and data['benchmark'] is True


class TestListContractRealChain:
    """列表/详情契约：benchmark 字段随响应返回（D1 消费入口）"""

    def test_list_and_detail_contain_benchmark_field(self, pt_gateway):
        task_id = _seed_publishable_task()
        r1 = pt_gateway.post('/api/v1/published-tasks', json={
            'sourceTaskId': task_id, 'name': '基准-契约'})
        assert r1.status_code == 201, r1.text[:300]
        pt_id = r1.json()['data']['id']

        items = pt_gateway.get('/api/v1/published-tasks').json()['data']['items']
        target = [i for i in items if i['id'] == pt_id]
        assert target and isinstance(target[0]['benchmark'], bool)

        detail = pt_gateway.get(f'/api/v1/published-tasks/{pt_id}').json()['data']
        assert isinstance(detail['benchmark'], bool)
