# -*- coding: utf-8 -*-
"""INT-842 专项：API 管理 CRUD 补操作人 user_id（api_test_service）。

覆盖：
- 仓储写侧 create_api / update_api / delete_api（软删）从上下文填充操作人列
  created_by_user_id / updated_by_user_id。apis 表无 deleted_by_user_id 列
  （INT-842 现状注记），软删操作人以 updated_by_user_id 记录（对齐
  api_gateway laboratory 仓储口径）。
- AUTH_MODE=off 等价：无上下文 → 列保持 NULL，不硬编码 0/None 充当真实用户。
- 客户端自报值不充当操作人：上下文用户优先（覆盖 data 中同名键）。
- 补装 server_user_context_interceptor 后：真实 gRPC server + x-user-id
  metadata → contextvar → 仓储落列（验收「网关 x-user-id metadata 能落到仓库」）。

DB：SQLite 临时文件库（check_same_thread=False，gRPC 线程可写），仅建 apis 表，
对齐 test_int68_api_rms_spl_persistence_db.py 的 db 夹具口径。
"""
import json
import os
import socket
import tempfile

os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

import pytest

import shared.models.database as database


def _free_port() -> int:
    """取一个当前空闲的本地端口（bind 0 释放后复用，竞态窗口极小）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


@pytest.fixture()
def db():
    """SQLite 临时文件库：engine 直装全局 scoped_session，仅建 apis 表。"""
    from sqlalchemy import create_engine

    from api_test_service.infrastructure.persistence.models.api_models import API

    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    engine = create_engine(
        f'sqlite:///{path}', connect_args={'check_same_thread': False})
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(engine, tables=[API.__table__])
    yield database
    database.remove_db_session()
    engine.dispose()
    try:
        os.remove(path)
    except PermissionError:
        # gRPC 线程连接归还竞态下文件句柄偶发未释放：临时文件由 OS 兜底清理，不阻塞
        pass


def _get_api_po(db, api_id):
    from api_test_service.infrastructure.persistence.models import API
    session = db.get_db_session()
    try:
        return session.get(API, api_id)
    finally:
        db.remove_db_session()


@pytest.fixture()
def neutralize_side_effects(monkeypatch):
    """隔离 create/delete 的无关副作用（Redis 事件发布 + 首页统计刷新）。

    统计刷新会对 task/audio/device/... 各服务发起出站 gRPC（本测试无后端，
    INT-204 规定 task 域失败透传 → 拖慢 handler 直至客户端 deadline）；测试
    只关心 metadata → contextvar → 仓储落列，故按 test_int816 口径置为 no-op。
    """
    from api_test_service.application import api_crud_service as api_crud_module

    class _FakeEventBus:
        def publish(self, channel, event_type, payload):
            pass

    monkeypatch.setattr(api_crud_module, 'EventBus', _FakeEventBus)
    monkeypatch.setattr(api_crud_module, 'refresh_stats_cache', lambda: None)


# ---------------- 仓储写侧操作人填充 ----------------

class TestRepositoryOperatorFill:

    def test_create_fills_created_by_user_id_from_context(self, db):
        from shared.infrastructure.user_context import set_current_user_id
        from api_test_service.infrastructure.persistence import api_test_repository as repo_mod

        set_current_user_id(111)
        try:
            api = repo_mod.api_test_repository.create_api({
                'name': 'INT842-Create', 'meta': {}, 'api_url': 'http://example.com',
            })
            po = _get_api_po(db, api.id)
            assert po.created_by_user_id == 111
            assert po.updated_by_user_id is None  # create 仅填创建者（codebase 口径）
        finally:
            set_current_user_id(None)

    def test_create_without_context_leaves_null(self, db):
        from shared.infrastructure.user_context import set_current_user_id
        from api_test_service.infrastructure.persistence import api_test_repository as repo_mod

        set_current_user_id(None)
        api = repo_mod.api_test_repository.create_api({
            'name': 'INT842-OffMode', 'meta': {},
        })
        po = _get_api_po(db, api.id)
        assert po.created_by_user_id is None

    def test_create_context_wins_over_client_self_report(self, db):
        from shared.infrastructure.user_context import set_current_user_id
        from api_test_service.infrastructure.persistence import api_test_repository as repo_mod

        set_current_user_id(111)
        try:
            api = repo_mod.api_test_repository.create_api({
                'name': 'INT842-SelfReport', 'meta': {},
                'created_by_user_id': 999,  # 客户端自报值不得充当操作人
            })
            po = _get_api_po(db, api.id)
            assert po.created_by_user_id == 111
        finally:
            set_current_user_id(None)

    def test_update_fills_updated_by_user_id_from_context(self, db):
        from shared.infrastructure.user_context import set_current_user_id
        from api_test_service.infrastructure.persistence import api_test_repository as repo_mod

        set_current_user_id(111)
        try:
            api = repo_mod.api_test_repository.create_api({
                'name': 'INT842-Before', 'meta': {},
            })
            set_current_user_id(222)
            updated = repo_mod.api_test_repository.update_api(
                api.id, {'name': 'INT842-After'})
            assert updated is not None
            po = _get_api_po(db, api.id)
            assert po.name == 'INT842-After'
            assert po.updated_by_user_id == 222
        finally:
            set_current_user_id(None)

    def test_update_context_wins_over_client_self_report(self, db):
        from shared.infrastructure.user_context import set_current_user_id
        from api_test_service.infrastructure.persistence import api_test_repository as repo_mod

        set_current_user_id(111)
        try:
            api = repo_mod.api_test_repository.create_api({
                'name': 'INT842-UpdateSelf', 'meta': {},
            })
            set_current_user_id(222)
            repo_mod.api_test_repository.update_api(
                api.id, {'name': 'x', 'updated_by_user_id': 999})
            po = _get_api_po(db, api.id)
            assert po.updated_by_user_id == 222
        finally:
            set_current_user_id(None)

    def test_update_without_context_leaves_null(self, db):
        from shared.infrastructure.user_context import set_current_user_id
        from api_test_service.infrastructure.persistence import api_test_repository as repo_mod

        set_current_user_id(None)
        api = repo_mod.api_test_repository.create_api({
            'name': 'INT842-UpdOff', 'meta': {},
        })
        repo_mod.api_test_repository.update_api(api.id, {'name': 'x'})
        po = _get_api_po(db, api.id)
        assert po.updated_by_user_id is None

    def test_delete_soft_records_operator_in_updated_by(self, db):
        """apis 表无 deleted_by_user_id 列：软删操作人以 updated_by_user_id 记录。"""
        from shared.infrastructure.user_context import set_current_user_id
        from api_test_service.infrastructure.persistence import api_test_repository as repo_mod

        set_current_user_id(111)
        try:
            api = repo_mod.api_test_repository.create_api({
                'name': 'INT842-Delete', 'meta': {},
            })
            set_current_user_id(333)
            assert repo_mod.api_test_repository.delete_api(api.id) is True
            po = _get_api_po(db, api.id)
            assert po.deleted is True
            assert po.updated_by_user_id == 333
        finally:
            set_current_user_id(None)


# ---------------- 补装 server_user_context_interceptor ----------------

class TestServerWiresUserContextInterceptor:

    def test_start_grpc_server_wires_user_context_interceptor(self, monkeypatch):
        """验收：start_grpc_server 的拦截器链包含 server_user_context_interceptor。"""
        import grpc as grpc_lib

        from api_test_service.interfaces.grpc import server as server_mod
        from shared.infrastructure.grpc_interceptors import server_user_context_interceptor

        real_server = grpc_lib.server
        captured = []

        def _capturing_server(*args, **kwargs):
            captured.append(kwargs.get('interceptors'))
            return real_server(*args, **kwargs)

        monkeypatch.setattr(server_mod.grpc, 'server', _capturing_server)
        srv = server_mod.start_grpc_server(port=0)
        try:
            assert captured, 'start_grpc_server 未创建 gRPC server'
            assert server_user_context_interceptor in captured[0], \
                'server_user_context_interceptor 未挂载（INT-842 补装）'
        finally:
            srv.stop(0)


# ---------------- 真实 gRPC server：metadata → contextvar → 仓储 ----------------

class TestGrpcUserContextReachesRepository:
    """真实 gRPC server（挂生产拦截器链）+ 真实 APITestServiceServicer。

    验证 x-user-id metadata 经拦截器落入 contextvar，再由仓储写侧落列。
    """

    def _call_create(self, stub, name, metadata=None):
        from shared.proto import api_test_service_pb2 as api_pb
        from shared.utils.grpc_json import dumps as _dumps

        kwargs = {'timeout': 10}
        if metadata:
            kwargs['metadata'] = metadata
        resp = stub.CreateAPIConfig(api_pb.CreateAPIConfigRequest(data=_dumps({
            'name': name, 'api_url': 'http://example.com', 'meta': {},
        })), **kwargs)
        return resp

    def test_create_metadata_writes_creator(self, db, neutralize_side_effects):
        import grpc

        from api_test_service.interfaces.grpc.server import start_grpc_server
        from shared.proto import api_test_service_pb2 as api_pb
        from shared.proto import api_test_service_pb2_grpc as api_grpc

        port = _free_port()
        server = start_grpc_server(port=port)
        try:
            with grpc.insecure_channel(f'127.0.0.1:{port}') as channel:
                stub = api_grpc.APITestServiceStub(channel)
                resp = self._call_create(
                    stub, 'INT842-gRPC-Create', metadata=(('x-user-id', '8'),))
                assert resp.success is True, resp.message
                api_id = json.loads(resp.data)['id']
            po = _get_api_po(db, api_id)
            assert po.created_by_user_id == 8
        finally:
            server.stop(0)

    def test_update_metadata_writes_updater(self, db, neutralize_side_effects):
        import grpc

        from api_test_service.interfaces.grpc.server import start_grpc_server
        from shared.proto import api_test_service_pb2 as api_pb
        from shared.proto import api_test_service_pb2_grpc as api_grpc
        from shared.utils.grpc_json import dumps as _dumps
        from api_test_service.infrastructure.persistence.models import API

        # 直插种子行（无上下文，created_by 保持 NULL）
        session = db.get_db_session()
        try:
            po = API(name='INT842-seed', meta={})
            session.add(po)
            session.commit()
            api_id = po.id
        finally:
            db.remove_db_session()

        port = _free_port()
        server = start_grpc_server(port=port)
        try:
            with grpc.insecure_channel(f'127.0.0.1:{port}') as channel:
                stub = api_grpc.APITestServiceStub(channel)
                resp = stub.UpdateAPIConfig(
                    api_pb.UpdateAPIConfigRequest(
                        api_id=api_id, data=_dumps({'name': 'INT842-gRPC-Updated'})),
                    timeout=10, metadata=(('x-user-id', '9'),))
                assert resp.success is True, resp.message
            po = _get_api_po(db, api_id)
            assert po.name == 'INT842-gRPC-Updated'
            assert po.updated_by_user_id == 9
        finally:
            server.stop(0)

    def test_without_metadata_leaves_null_no_crosstalk(self, db, neutralize_side_effects):
        """无 metadata 调用不得继承前一次 RPC 的操作人（拦截器 RPC 结束清理）。"""
        import grpc

        from api_test_service.interfaces.grpc.server import start_grpc_server
        from shared.proto import api_test_service_pb2_grpc as api_grpc

        port = _free_port()
        server = start_grpc_server(port=port)
        try:
            with grpc.insecure_channel(f'127.0.0.1:{port}') as channel:
                stub = api_grpc.APITestServiceStub(channel)
                # 先带 metadata 的调用：落 8
                resp1 = self._call_create(
                    stub, 'INT842-with-meta', metadata=(('x-user-id', '8'),))
                assert resp1.success is True, resp1.message
                # 同线程池再发无 metadata 调用：不得串号，created_by 恒 NULL
                resp2 = self._call_create(stub, 'INT842-no-meta')
                assert resp2.success is True, resp2.message
                api_id_2 = json.loads(resp2.data)['id']
            po = _get_api_po(db, api_id_2)
            assert po.created_by_user_id is None
        finally:
            server.stop(0)

    def test_delete_metadata_records_deleter(self, db, neutralize_side_effects):
        """软删操作人以 updated_by_user_id 记录（无 deleted_by_user_id 列）。"""
        import grpc

        from api_test_service.interfaces.grpc.server import start_grpc_server
        from shared.proto import api_test_service_pb2 as api_pb
        from shared.proto import api_test_service_pb2_grpc as api_grpc
        from shared.utils.grpc_json import dumps as _dumps
        from api_test_service.infrastructure.persistence.models import API

        session = db.get_db_session()
        try:
            po = API(name='INT842-del', meta={})
            session.add(po)
            session.commit()
            api_id = po.id
        finally:
            db.remove_db_session()

        port = _free_port()
        server = start_grpc_server(port=port)
        try:
            with grpc.insecure_channel(f'127.0.0.1:{port}') as channel:
                stub = api_grpc.APITestServiceStub(channel)
                resp = stub.DeleteAPIConfig(
                    api_pb.DeleteAPIConfigRequest(api_id=api_id),
                    timeout=10, metadata=(('x-user-id', '7'),))
                assert resp.success is True, resp.message
            po = _get_api_po(db, api_id)
            assert po.deleted is True
            assert po.updated_by_user_id == 7
        finally:
            server.stop(0)
