# -*- coding: utf-8 -*-
"""INT-148 实机验证回归 —— 真实 Postgres + 进程内 gRPC（风格对齐 INT-35 真实链路）。

验收项：failed/stopped 任务重启场景无重复结果行；任务 start 前对 API 用例
目标 API 做在线预检（复用 api_test_service test_connection）。

链路（生产同款组件，仅进程边界收拢）：
- 真实 Postgres 临时库（CREATE DATABASE → 全模型建表 → 用后即删）；
- 真实 TaskDataServiceServicer.SubmitResult（执行/评估提交侧，无条件 INSERT）
  与真实 APITestServiceServicer.TestAPIConnection（健康检查，requests 真实
  HTTP 打本地被测 API 替身）；
- 重启清理走真实 task_repository.reset_task_for_start。

覆盖：
- 缺陷#2：首轮执行产生 TestResult → reset_task_for_start（failed 任务重启
  前置重置）→ 旧行清空 → 重跑提交后每个 (task_id, test_case_id) 恰一行，
  无重复/脏结果行；
- 缺陷#1：API 在线 → 预检放行；API 离线（连接拒绝）→ 明确报错阻断启动。
"""
import json
import os
import uuid

# BaseConfig 在 import 时校验环境变量（测试环境无 .env），先补齐必需项
os.environ.setdefault('DATABASE_URL', 'postgresql://placeholder:placeholder@localhost:5432/placeholder')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psycopg2
import pytest

from tests.integration.test_data_transfer_roundtrip import storage_env  # noqa: F401

PG_HOST = os.environ.get('INT35_PG_HOST', '127.0.0.1')
PG_PORT = int(os.environ.get('INT35_PG_PORT', '5432'))
PG_USER = os.environ.get('INT35_PG_USER', 'intelligent_audio_test')
PG_PASSWORD = os.environ.get('INT35_PG_PASSWORD', 'intelligent_audio_test666')

TASK_ID = 9148


def _pg_reachable():
    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD,
            dbname='postgres', connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


def _import_all_models():
    import task_service.infrastructure.persistence.models  # noqa: F401
    import evaluation_service.infrastructure.persistence.models  # noqa: F401
    import report_service.infrastructure.persistence.models  # noqa: F401
    import api_test_service.infrastructure.persistence.models  # noqa: F401
    import audio_service.infrastructure.persistence.models  # noqa: F401
    import algorithm_service.infrastructure.persistence.models  # noqa: F401


@pytest.fixture(scope='module')
def pg_db(storage_env):
    """真实 Postgres 临时库：整库创建（CREATE DATABASE）→ 全模型建表 → 用后即删。"""
    if not _pg_reachable():
        pytest.skip(f'本机 Postgres {PG_HOST}:{PG_PORT} 不可用，INT-148 实机验证跳过')

    dbname = f'int148_{uuid.uuid4().hex[:10]}'
    admin = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD,
        dbname='postgres', connect_timeout=5)
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute(f'CREATE DATABASE {dbname} ENCODING utf8')
    cur.close()

    from sqlalchemy import create_engine

    import shared.models.database as database

    _import_all_models()

    prev_engine = database._engine
    engine = create_engine(
        f'postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{dbname}',
        pool_pre_ping=True)
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(engine)
    yield database
    database.remove_db_session()
    engine.dispose()
    # INT-163：恢复 worker 进程级 engine / session 工厂绑定——本 fixture 替换
    # 的是全局单例，不恢复则同 worker 后续文件的 get_db_session() 会指向
    # 已删除的临时库（跨文件序污染源）。
    database._engine = prev_engine
    database._SessionFactory.configure(bind=prev_engine)
    try:
        cur = admin.cursor()
        # 逐个终止库内残留后端后普通 DROP。不再用 WITH (FORCE)：其内置终止
        # 撞上外来角色后端时直接 InsufficientPrivilege 使 teardown 炸掉
        # （INT-163 实证）且临时库名残留；同角色后端 pg_terminate_backend
        # 可终止，外来角色终止失败（返回 false）则 DROP 失败、登记残留库名
        # 后继续，不因环境权限差异炸掉整个模块的收尾。
        cur.execute(
            'SELECT pid, pg_terminate_backend(pid) FROM pg_stat_activity '
            'WHERE datname = %s AND pid <> pg_backend_pid()', (dbname,))
        cur.execute(f'DROP DATABASE IF EXISTS {dbname}')
        cur.close()
    except psycopg2.Error as e:
        print(f'[int148] 临时库 {dbname} 清理失败，残留待手工清理: {e!r}')
    finally:
        admin.close()


class _JsonHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, payload, status=200):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        length = int(self.headers.get('Content-Length') or 0)
        if length:
            self.rfile.read(length)
        if self.path.split('?')[0].rstrip('/') == '/health':
            self._send({'code': 0, 'msg': 'success', 'status': 'healthy'}, 200)
        else:
            self._send({'code': 404, 'msg': 'not found'}, 404)


@pytest.fixture(scope='module')
def api_double():
    """被测 API 替身（真实 HTTP，仅 /health 在线）——API 在线预检的健康检查目标。"""
    server = ThreadingHTTPServer(('127.0.0.1', 0), _JsonHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_address[1]}'
    server.shutdown()
    server.server_close()


@pytest.fixture(scope='module')
def grpc_mesh(pg_db, api_double):
    """task_service + api_test_service 进程内真实 gRPC server + stub 重定向。"""
    from concurrent import futures

    import grpc

    from shared.infrastructure.grpc_interceptors import (
        server_db_scope_interceptor,
        server_log_interceptor,
    )

    def _new_server():
        return grpc.server(
            futures.ThreadPoolExecutor(max_workers=8),
            interceptors=[server_db_scope_interceptor, server_log_interceptor])

    from shared.proto import task_service_pb2_grpc as task_grpc
    from task_service.interfaces.grpc.task_data_service import TaskDataServiceServicer

    task_server = _new_server()
    task_grpc.add_TaskDataServiceServicer_to_server(TaskDataServiceServicer(), task_server)
    task_port = task_server.add_insecure_port('[::]:0')

    from api_test_service.core.api_test_service import api_test_service as _api_svc
    _api_svc.init_app()
    from shared.proto import api_test_service_pb2_grpc as api_grpc
    from api_test_service.interfaces.grpc.servicers import APITestServiceServicer

    api_server = _new_server()
    api_grpc.add_APITestServiceServicer_to_server(APITestServiceServicer(), api_server)
    api_port = api_server.add_insecure_port('[::]:0')

    task_server.start()
    api_server.start()

    import shared.clients._grpc_channels as channels_mod
    import shared.clients._grpc_stubs as stubs_mod

    mp = pytest.MonkeyPatch()
    mp.setattr(channels_mod, 'TASK_GRPC_ADDR', f'localhost:{task_port}')
    mp.setattr(channels_mod, 'API_TEST_GRPC_ADDR', f'localhost:{api_port}')

    _channel_caches = [
        channels_mod._get_task_channel.cache_clear,
        channels_mod._get_api_test_channel.cache_clear,
    ]
    _stub_caches = [
        stubs_mod.get_task_data_service_stub.cache_clear,
        stubs_mod.get_api_test_service_stub.cache_clear,
    ]
    for clear in _channel_caches + _stub_caches:
        clear()

    yield {'online_endpoint': api_double}

    for clear in _channel_caches + _stub_caches:
        clear()
    mp.undo()
    task_server.stop(grace=None).wait(timeout=5)
    api_server.stop(grace=None).wait(timeout=5)


# ──────────────────────────── 数据准备 ────────────────────────────

def _seed_failed_task_with_results(case_ids):
    """failed 任务：TaskCase 全部 failed + 每用例一条终态 TestResult（首轮执行残留）。"""
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models import Task, TaskCase, TestResult

    session = get_db_session()
    try:
        session.add(Task(id=TASK_ID, name='INT-148 重启验证任务', status='failed',
                         total_cases=len(case_ids), completed_cases=0,
                         failed_cases=len(case_ids)))
        for cid in case_ids:
            session.add(TaskCase(task_id=TASK_ID, test_case_id=cid,
                                 status='failed', execution_status='failed',
                                 evaluation_status='failed',
                                 error_message='首轮执行失败'))
            session.add(TestResult(task_id=TASK_ID, test_case_id=cid,
                                   execution_status='failed',
                                   error_message='首轮执行失败'))
        session.commit()
    finally:
        session.close()


def _submit_result_via_grpc(task_id, test_case_id):
    """真实提交侧：TaskDataServiceServicer.SubmitResult（无条件 INSERT）。"""
    from shared.clients.grpc_clients import submit_result

    result_id = submit_result(task_id, {
        'test_case_id': test_case_id,
        'execution_status': 'completed',
        'algorithm_type': 'translation',
        'algorithm_result': {'rounds': [{'answer': 'ok'}]},
    })
    assert result_id, 'SubmitResult 应返回 result_id'
    return result_id


def _count_results(task_id, test_case_id=None):
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models import TestResult

    session = get_db_session()
    try:
        q = session.query(TestResult).filter(TestResult.task_id == task_id)
        if test_case_id:
            q = q.filter(TestResult.test_case_id == test_case_id)
        return q.count()
    finally:
        session.close()


# ──────────────────────────── 缺陷#2：重启无重复结果行 ────────────────────────────

class TestRestartNoDuplicateResults:
    """failed 任务重启 → 重置清理旧 TestResult → 重跑提交恰好一行。"""

    def test_restart_clears_then_resubmit_single_row(self, pg_db, grpc_mesh):
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import Task, TaskCase
        from task_service.infrastructure.persistence.task_repository import task_repository

        case_ids = ['case-a', 'case-b']
        _seed_failed_task_with_results(case_ids)

        # 首轮残留：每用例一条旧行
        assert _count_results(TASK_ID) == 2
        assert _count_results(TASK_ID, 'case-a') == 1

        # 重启路径（start 对 failed 任务的前置重置，真实 Postgres）
        assert task_repository.reset_task_for_start(TASK_ID) is True

        # 旧行清空（修复前：残留 2 行 → 重跑 INSERT 后 4 行重复/脏结果）
        assert _count_results(TASK_ID) == 0

        # 重跑：TaskCase 已重置 pending，提交侧 INSERT 全新结果行
        session = get_db_session()
        try:
            for tc in session.query(TaskCase).filter_by(task_id=TASK_ID).all():
                assert tc.execution_status == 'pending'
                assert tc.evaluation_status == 'pending'
        finally:
            session.close()

        for cid in case_ids:
            _submit_result_via_grpc(TASK_ID, cid)

        # 验收点：无重复结果行——每个 (task_id, test_case_id) 恰一条
        assert _count_results(TASK_ID) == 2
        for cid in case_ids:
            assert _count_results(TASK_ID, cid) == 1

        session = get_db_session()
        try:
            task = session.get(Task, TASK_ID)
            assert task.status == 'pending'
            assert task.completed_cases == 0
            assert task.failed_cases == 0
        finally:
            session.close()


# ──────────────────────────── 缺陷#1：API 在线预检 ────────────────────────────

class TestStartApiPrecheck:
    """start 预检：目标 API 在线放行 / 离线明确报错阻断（真实 gRPC + HTTP）。"""

    def _seed_api_case(self, task_id, case_id, api_row_id):
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import TaskCase

        session = get_db_session()
        try:
            session.add(TaskCase(task_id=task_id, test_case_id=case_id,
                                 status='pending', execution_status='pending',
                                 evaluation_status='pending',
                                 device_type='http_api', device_id=str(api_row_id)))
            session.commit()
        finally:
            session.close()

    def _create_api_config(self, endpoint):
        """经真实 ACL 写入 apis 表（api_test_service 仓储），返回 api id。"""
        from api_test_service.infrastructure.persistence.api_test_repository import (
            api_test_repository,
        )

        po = api_test_repository.create_api({
            'name': f'INT148 预检 {uuid.uuid4().hex[:6]}',
            'api_endpoints': [{'endpoint': endpoint, 'max_timeout': 5}],
            'algorithm_type': 'voice_llm',
            'status': 'online',
        })
        return po.id

    def test_online_api_passes_precheck(self, pg_db, grpc_mesh):
        from task_service.infrastructure.acl.api_acl_repository import api_acl_repository
        from task_service.infrastructure.persistence._task_lifecycle_mixin import (
            TaskLifecycleMixin,
        )

        api_id = self._create_api_config(grpc_mesh['online_endpoint'])

        # 真实 gRPC 链路健康检查（test_connection → /health 替身）：
        # 防降级假通过——ACL 返回 None（gRPC 失败）时预检会静默跳过
        info = api_acl_repository.test_api_connection(api_id)
        assert info is not None, 'TestAPIConnection 不应失败（_log source 冲突回归）'
        assert info['status'] == 'online'

        self._seed_api_case(TASK_ID + 1, 'case-online', api_id)

        can_start, err = TaskLifecycleMixin._check_apis_online(TASK_ID + 1)

        assert (can_start, err) == (True, '')

    def test_offline_api_blocks_with_clear_error(self, pg_db, grpc_mesh):
        from task_service.infrastructure.persistence._task_lifecycle_mixin import (
            TaskLifecycleMixin,
        )

        # 指向必然拒绝连接的死端口 → test_connection 收敛 status=offline
        api_id = self._create_api_config('http://127.0.0.1:9/port-down')
        self._seed_api_case(TASK_ID + 3, 'case-offline', api_id)

        can_start, err = TaskLifecycleMixin._check_apis_online(TASK_ID + 3)

        assert can_start is False
        assert f'id={api_id}' in err
        assert '离线' in err

    def test_mixed_cases_only_api_cases_checked(self, pg_db, grpc_mesh):
        """physical 用例不参与 API 预检（设备检查职责），API 用例照常检查。"""
        from shared.models.database import get_db_session
        from task_service.infrastructure.persistence.models import TaskCase
        from task_service.infrastructure.persistence._task_lifecycle_mixin import (
            TaskLifecycleMixin,
        )

        session = get_db_session()
        try:
            session.add(TaskCase(task_id=TASK_ID + 2, test_case_id='case-phys',
                                 status='pending', execution_status='pending',
                                 evaluation_status='pending',
                                 device_type='physical', device_id='3'))
            session.commit()
        finally:
            session.close()

        api_id = self._create_api_config('http://127.0.0.1:9/port-down')
        self._seed_api_case(TASK_ID + 2, 'case-api-dead', api_id)

        can_start, err = TaskLifecycleMixin._check_apis_online(TASK_ID + 2)

        assert can_start is False
        assert '离线' in err
