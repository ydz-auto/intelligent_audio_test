# -*- coding: utf-8 -*-
"""INT-2236（P1 IDOR）—— 报告二次对比源报告可见性：gRPC 真实链路 + 网关映射验收。

缺陷：`_validate_reports_and_get_tasks` 用 `get_report_by_id_raw`（无 visibility /
无 deleted 过滤）读源报告，随后把源报告用例复制进新报告；持有 report:compare 的
用户传他人私有 / 已软删报告 ID 即可越权读出内容。

本文件不依赖开发者单测，走**生产同款链路**独立取证：
  gRPC stub（共享 channel + 生产客户端拦截器，x-user-id / x-user-is-admin 由
  contextvar 自动附加）→ 进程内真实 ReportServicer（生产三个服务端拦截器，
  含 server_user_context_interceptor）→ 应用服务 → 真仓储 → SQLite 临时库。

覆盖：
1. 非 owner 传他人私有报告 ID → success=False + 业务码 404（pb.code 与 data.code
   双通道都验），未提交异步任务、库中不新增报告；
2. 已软删报告（owner 自己传）→ 同样 404，不做「跳过已删行凑够两个就放行」；
3. 不存在的报告 ID → 404；
4. 整批拒绝语义：私有非 owner 与可见报告混传 → 仍拒绝（不放行可见那部分）；
5. admin（x-user-is-admin 经 metadata 透传）可读他人私有报告 → 提交成功（豁免
   不是靠放开过滤）；
6. owner 自己的私有报告 + 共享报告 → 校验通过并提交（正常链路不回归）；
7. 网关 `ReportCommandService.secondary_compare` 把 data.code=404 提升为 HTTP 404。
"""
import json
import os
import tempfile
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from concurrent import futures

import grpc
import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    return 'INTEGER'


USER_A = 1001
USER_B = 1002
DENIED_HINT = '报告不存在或无权访问'


# ---------------------------------------------------------------------------
# 环境夹具
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    """SQLite 临时文件库：engine 直装全局 scoped_session（同现有集成测试模式）。"""
    import shared.models.database as database
    import task_service.infrastructure.persistence.models  # noqa: F401
    import evaluation_service.infrastructure.persistence.models  # noqa: F401
    import report_service.infrastructure.persistence.models  # noqa: F401

    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    engine = create_engine(f'sqlite:///{path}',
                           connect_args={'check_same_thread': False})
    database.remove_db_session()
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(engine)
    yield database
    database.remove_db_session()
    engine.dispose()
    try:
        os.remove(path)
    except PermissionError:
        pass


@pytest.fixture(autouse=True)
def _clean_user_context():
    from shared.infrastructure.user_context import (
        set_current_user_id,
        set_current_user_is_admin,
    )
    import report_service.application.services.report_compare_generator as cmp_mod

    set_current_user_id(None)
    set_current_user_is_admin(False)
    cmp_mod._generating_secondary.clear()
    yield
    set_current_user_id(None)
    set_current_user_is_admin(False)
    cmp_mod._generating_secondary.clear()


@pytest.fixture()
def report_server(db):
    """进程内真实 report ReportConfigService gRPC server（生产同款拦截器）。"""
    from shared.infrastructure.grpc_interceptors import (
        server_db_scope_interceptor,
        server_log_interceptor,
        server_user_context_interceptor,
    )
    from shared.proto import report_service_pb2_grpc as report_grpc
    from report_service.interfaces.grpc.servicers import ReportServicer

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=4),
        interceptors=[server_db_scope_interceptor, server_log_interceptor,
                      server_user_context_interceptor])
    report_grpc.add_ReportConfigServiceServicer_to_server(ReportServicer(), server)
    port = server.add_insecure_port('[::]:0')
    server.start()
    yield port
    server.stop(grace=None).wait(timeout=5)


@pytest.fixture()
def report_client(report_server):
    """共享 channel / stub 指向进程内 server；保留生产客户端拦截器。"""
    import shared.clients._grpc_channels as channels_mod
    import shared.clients._grpc_stubs as stubs_mod

    old_addr = channels_mod.REPORT_GRPC_ADDR
    channels_mod.REPORT_GRPC_ADDR = f'localhost:{report_server}'
    channels_mod._get_report_channel.cache_clear()
    stubs_mod.get_report_config_service_stub.cache_clear()
    yield stubs_mod.get_report_config_service_stub()
    stubs_mod.get_report_config_service_stub.cache_clear()
    channels_mod.REPORT_GRPC_ADDR = old_addr
    channels_mod._get_report_channel.cache_clear()


@pytest.fixture()
def submitted(monkeypatch):
    """拦截异步提交：记录被提交的 report_ids，不真跑生成线程。"""
    import report_service.application.services.report_compare_generator as cmp_mod

    calls = []

    def _fake_submit(report_ids, report_key, description):
        calls.append(list(report_ids))
        return True

    monkeypatch.setattr(cmp_mod, '_submit_secondary_generation', _fake_submit)
    return calls


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _seed_reports(db, rows):
    """直接写 Report PO，精确控制 owner / visibility / deleted。"""
    from report_service.infrastructure.persistence.models import Report

    session = db.get_db_session()
    ids = []
    for row in rows:
        po = Report(name=row['name'], type=row.get('type', 'task'),
                    status=row.get('status', 'completed'),
                    task_id=row.get('task_id'),
                    created_by_user_id=row.get('created_by'),
                    visibility=row.get('visibility', 'shared'),
                    deleted=row.get('deleted', False))
        session.add(po)
        session.flush()
        ids.append(po.id)
    session.commit()
    db.remove_db_session()
    return ids


def _report_ids_in_db(db):
    from report_service.infrastructure.persistence.models import Report

    session = db.get_db_session()
    try:
        return [r[0] for r in session.query(Report.id).all()]
    finally:
        db.remove_db_session()


def _call(report_client, report_ids):
    from shared.proto import report_service_pb2 as report_pb

    stub = report_client
    req = report_pb.GenerateSecondaryCompareReportRequest(
        data=json.dumps({'report_ids': report_ids, 'description': ''}))
    return stub.GenerateSecondaryCompareReport(req)


def _folded(resp):
    return json.loads(resp.data) if resp.data else {}


# ---------------------------------------------------------------------------
# 1~4：越权 / 软删 / 不存在 / 整批拒绝
# ---------------------------------------------------------------------------

class TestDeniedSourceReports:
    def test_other_users_private_report_denied_404(
            self, db, report_client, submitted):
        from shared.infrastructure.user_context import set_current_user_id

        rid_a, rid_b = _seed_reports(db, [
            {'name': 'A私有', 'created_by': USER_A, 'visibility': 'private'},
            {'name': 'B共享', 'created_by': USER_B, 'visibility': 'shared'},
        ])
        before = set(_report_ids_in_db(db))

        set_current_user_id(USER_B)
        resp = _call(report_client, [rid_a, rid_b])

        assert resp.success is False
        assert resp.code == 404, f'pb.code 应为 404，实际 {resp.code}'
        data = _folded(resp)
        assert data.get('code') == 404, f'data.code 应为 404，实际 {data}'
        assert DENIED_HINT in resp.message
        assert str(rid_a) in resp.message
        # 不提交、不建报告
        assert submitted == []
        assert set(_report_ids_in_db(db)) == before

    def test_soft_deleted_report_denied_even_for_owner(
            self, db, report_client, submitted):
        from shared.infrastructure.user_context import set_current_user_id

        rid_alive, rid_deleted = _seed_reports(db, [
            {'name': 'A在用', 'created_by': USER_A, 'visibility': 'private'},
            {'name': 'A回收站', 'created_by': USER_A, 'visibility': 'private',
             'deleted': True},
        ])
        before = set(_report_ids_in_db(db))

        set_current_user_id(USER_A)
        resp = _call(report_client, [rid_alive, rid_deleted])

        assert resp.success is False
        assert resp.code == 404
        assert str(rid_deleted) in resp.message
        assert submitted == []
        assert set(_report_ids_in_db(db)) == before

    def test_nonexistent_report_id_denied(self, db, report_client, submitted):
        from shared.infrastructure.user_context import set_current_user_id

        rid_a, = _seed_reports(db, [
            {'name': 'A共享', 'created_by': USER_A, 'visibility': 'shared'},
        ])

        set_current_user_id(USER_A)
        resp = _call(report_client, [rid_a, 987654321])

        assert resp.success is False
        assert resp.code == 404
        assert '987654321' in resp.message
        assert submitted == []

    def test_mixed_batch_does_not_pass_through_visible_part(
            self, db, report_client, submitted):
        """两个可见 + 一个他人私有：整批拒绝（不做跳过式放行）。"""
        from shared.infrastructure.user_context import set_current_user_id

        rid_a1, rid_a2, rid_b_private = _seed_reports(db, [
            {'name': 'A共享1', 'created_by': USER_A, 'visibility': 'shared'},
            {'name': 'A私有', 'created_by': USER_A, 'visibility': 'private'},
            {'name': 'B私有', 'created_by': USER_B, 'visibility': 'private'},
        ])

        set_current_user_id(USER_A)
        resp = _call(report_client, [rid_a1, rid_a2, rid_b_private])

        assert resp.success is False
        assert resp.code == 404
        assert str(rid_b_private) in resp.message
        assert submitted == []


# ---------------------------------------------------------------------------
# 5~6：admin 豁免 / 正常链路不回归
# ---------------------------------------------------------------------------

class TestAllowedSourceReports:
    def test_admin_reads_other_private_report(
            self, db, report_client, submitted):
        from shared.infrastructure.user_context import (
            set_current_user_id, set_current_user_is_admin,
        )

        rid_a, rid_b = _seed_reports(db, [
            {'name': 'A私有', 'created_by': USER_A, 'visibility': 'private'},
            {'name': 'B私有', 'created_by': USER_B, 'visibility': 'private'},
        ])

        set_current_user_id(USER_B)
        set_current_user_is_admin(True)   # 经 x-user-is-admin metadata 透传
        resp = _call(report_client, [rid_a, rid_b])

        assert resp.success is True, resp.message
        assert _folded(resp).get('status') == 'generating'
        assert submitted == [[rid_a, rid_b]]

    def test_owner_private_and_shared_reports_still_submit(
            self, db, report_client, submitted):
        from shared.infrastructure.user_context import set_current_user_id

        rid_own_private, rid_shared = _seed_reports(db, [
            {'name': 'A私有', 'created_by': USER_A, 'visibility': 'private'},
            {'name': 'C共享', 'created_by': 1003, 'visibility': 'shared'},
        ])

        set_current_user_id(USER_A)
        resp = _call(report_client, [rid_own_private, rid_shared])

        assert resp.success is True, resp.message
        assert _folded(resp).get('status') == 'generating'
        assert submitted == [[rid_own_private, rid_shared]]

    def test_unauthenticated_only_shared_reports_allowed(
            self, db, report_client, submitted):
        """未认证（AUTH_MODE=off 口径，user_id 归一为 None）：私有不可读、共享可读。"""
        rid_shared, rid_private = _seed_reports(db, [
            {'name': '共享', 'created_by': USER_A, 'visibility': 'shared'},
            {'name': '私有', 'created_by': USER_A, 'visibility': 'private'},
        ])

        # 不设置当前用户 = 未认证
        resp = _call(report_client, [rid_shared, rid_private])
        assert resp.success is False
        assert resp.code == 404
        assert str(rid_private) in resp.message

        rid_shared2, = _seed_reports(db, [
            {'name': '共享2', 'created_by': USER_A, 'visibility': 'shared'},
        ])
        resp2 = _call(report_client, [rid_shared, rid_shared2])
        assert resp2.success is True, resp2.message
        assert submitted == [[rid_shared, rid_shared2]]


# ---------------------------------------------------------------------------
# 6.1：异步线程复核（身份随任务带进 worker，提交后被删/收回即失败）
# ---------------------------------------------------------------------------

class TestAsyncRevalidationWithIdentity:
    @staticmethod
    def _stub_tasks(monkeypatch):
        """任务查询打桩：只验证源报告可见性这一段，不拉跨域用例数据。"""
        import report_service.application.services.report_compare_helpers as helpers

        monkeypatch.setattr(
            helpers, '_grpc_get_tasks_by_ids',
            lambda task_ids: [{'id': tid, 'status': 'completed'} for tid in task_ids])

    def test_worker_thread_sees_owner_identity(self, db, monkeypatch):
        """身份若没带进 worker，owner 自己的私有报告会被当成未认证身份拒掉。"""
        import report_service.application.services.report_compare_helpers as helpers
        from shared.infrastructure.user_context import (
            capture_identity, run_with_identity, set_current_user_id,
        )

        self._stub_tasks(monkeypatch)
        rid1, rid2 = _seed_reports(db, [
            {'name': 'A私有1', 'created_by': USER_A, 'visibility': 'private',
             'task_id': 501},
            {'name': 'A私有2', 'created_by': USER_A, 'visibility': 'private',
             'task_id': 502},
        ])

        set_current_user_id(USER_A)
        identity = capture_identity()
        set_current_user_id(None)   # 模拟 worker 线程（contextvars 不跨线程传播）

        # 反向对照：不带身份直接调用 → 未认证身份把 owner 的私有报告拒掉
        _, _, _, unauthorized = helpers.ReportCompareHelpers._validate_reports_and_get_tasks(
            [rid1, rid2])
        assert unauthorized and DENIED_HINT in unauthorized

        reports, tasks, task_ids, error = run_with_identity(
            identity, helpers.ReportCompareHelpers._validate_reports_and_get_tasks,
            [rid1, rid2])

        assert error is None, f'worker 内应按 owner 身份通过可见性校验，实际: {error}'
        assert sorted(r.id for r in reports) == [rid1, rid2]
        assert sorted(task_ids) == [501, 502]
        assert len(tasks) == 2

    def test_report_soft_deleted_after_submit_is_rejected(self, db, monkeypatch):
        """提交后源报告被软删：异步线程同一助手复核必须整批失败。"""
        import report_service.application.services.report_compare_helpers as helpers
        from shared.infrastructure.user_context import (
            capture_identity, run_with_identity, set_current_user_id,
        )
        from report_service.infrastructure.persistence.models import Report

        self._stub_tasks(monkeypatch)
        rid1, rid2 = _seed_reports(db, [
            {'name': 'A私有1', 'created_by': USER_A, 'visibility': 'private',
             'task_id': 511},
            {'name': 'A私有2', 'created_by': USER_A, 'visibility': 'private',
             'task_id': 512},
        ])

        session = db.get_db_session()
        session.query(Report).filter(Report.id == rid2).update({'deleted': True})
        session.commit()
        db.remove_db_session()

        set_current_user_id(USER_A)
        identity = capture_identity()
        set_current_user_id(None)

        reports, tasks, task_ids, error = run_with_identity(
            identity, helpers.ReportCompareHelpers._validate_reports_and_get_tasks,
            [rid1, rid2])

        assert reports is None and tasks is None and task_ids is None
        assert error and DENIED_HINT in error and str(rid2) in error


# ---------------------------------------------------------------------------
# 7：网关 HTTP 映射
# ---------------------------------------------------------------------------

class _FakeRequest:
    """request_adapter 兼容的假请求（中间件预解析 body 落在 state._json_body）。"""

    def __init__(self, body):
        self.state = SimpleNamespace(_json_body=body, username='')

    def get_json(self, silent=False):
        return self.state._json_body


class TestGatewayHttpMapping:
    def test_business_code_404_becomes_http_404(self, monkeypatch):
        from types import SimpleNamespace
        from shared.proto import report_service_pb2 as report_pb
        from shared.utils.grpc_json import dumps as _dumps
        import api_gateway.application.services.report.report_command_sevice as gw
        from api_gateway.infrastructure import request_adapter

        class _Stub:
            def GenerateSecondaryCompareReport(self, req):
                return report_pb.ReportConfigResponse(
                    success=False,
                    message='报告不存在或无权访问: 12',
                    data=_dumps({'code': 404}),
                    code=404)

        monkeypatch.setattr(gw, 'report_config_service',
                            SimpleNamespace(stub=_Stub()))
        request_adapter.set_current_request(
            _FakeRequest({'reportIds': [12, 13]}))
        try:
            result = gw.ReportCommandService.secondary_compare()
        finally:
            request_adapter.set_current_request(None)

        payload, http_code = result
        assert http_code == 404, f'应映射 HTTP 404，实际 {http_code}'
        assert int(payload.get('code')) == 404
        assert '报告不存在或无权访问' in payload.get('message', '')

    def test_non_404_failure_keeps_default_error(self, monkeypatch):
        from types import SimpleNamespace
        from shared.proto import report_service_pb2 as report_pb
        import api_gateway.application.services.report.report_command_sevice as gw
        from api_gateway.infrastructure import request_adapter

        class _Stub:
            def GenerateSecondaryCompareReport(self, req):
                return report_pb.ReportConfigResponse(
                    success=False, message='内部错误', data='', code=0)

        monkeypatch.setattr(gw, 'report_config_service',
                            SimpleNamespace(stub=_Stub()))
        request_adapter.set_current_request(
            _FakeRequest({'reportIds': [12, 13]}))
        try:
            payload, http_code = gw.ReportCommandService.secondary_compare()
        finally:
            request_adapter.set_current_request(None)

        assert http_code != 404
        assert '内部错误' in payload.get('message', '')
