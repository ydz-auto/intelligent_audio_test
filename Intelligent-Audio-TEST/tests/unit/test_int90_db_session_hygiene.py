# -*- coding: utf-8 -*-
"""INT-90 共享 DB 会话卫生回归守卫（三个互相放大的缺陷一组）。

缺陷 A 会话污染跨请求存活：flush 失败把 scoped_session 毒化为
PendingRollbackError 状态（is_active=False），原先按线程复用时该线程后续
所有请求持续失败。守卫：
- get_db_session() 对非活跃 session 先 rollback 自愈（毒化不跨取用存活）
- 请求级 scope（bind/release_request_session_scope）让每个请求拿到独立
  session、请求结束归还连接池（污染与 idle-in-transaction 不跨请求存活）
- DbSessionScopeMiddleware 端到端接线（毒化请求之后的请求拿到干净 session）

缺陷 B audit 日志 task_id 类型不匹配：logs.task_id 为 Integer 列，e2e 链路
以字符串任务 ID（'t1'）写库在 PostgreSQL 必报 invalid input syntax for type
bigint，flush 失败毒化会话并拖垮同批日志。守卫 batch_create 写库边界规范化：
数字/数字字符串→int，非数字→None（行照常落库）。

缺陷 C gRPC ACL 吞异常：playback ACL 基础设施失败（gRPC 调用异常、列表类
success=False）必须抛 PlaybackDeviceQueryError 向上传递真实错误，不得返回
[]/None 被翻译成「未找到可用设备」；正常应答但无匹配仍返回 []/None。
"""
import os
import tempfile

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int90_') + '/guard.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Column, Integer, String
from sqlalchemy.exc import IntegrityError, PendingRollbackError

from shared.models.database import (
    Base,
    bind_request_session_scope,
    get_db_session,
    get_engine,
    init_db,
    release_request_session_scope,
    _scoped_session,
)
from shared.infrastructure.db_session_middleware import DbSessionScopeMiddleware


class _Int90Poison(Base):
    """毒化专用 PO：nullable 列写入 NULL，flush 必失败（复现 InFailedSqlTransaction
    → PendingRollbackError 毒化链，与 logs.task_id 类型错在 PostgreSQL 的行为同构）。"""
    __tablename__ = 'int90_poison'
    id = Column(Integer, primary_key=True, autoincrement=True)
    payload = Column(String(20), nullable=False)


@pytest.fixture(scope='module', autouse=True)
def _db():
    init_db()
    engine = get_engine()
    Base.metadata.create_all(engine, tables=[_Int90Poison.__table__])
    yield


# ==================== 缺陷 A：毒化自愈 ====================

def _poison_current_session():
    """把当前 scope 的 session 毒化成 PendingRollbackError 状态，返回该 session。"""
    s = get_db_session().registry()
    s.add(_Int90Poison(payload=None))
    with pytest.raises(IntegrityError):
        s.flush()
    assert not s.is_active
    return s


def test_poisoned_session_unusable_before_heal():
    """机制前置验证：毒化后直接使用必抛 PendingRollbackError（原缺陷复现）。"""
    s = _poison_current_session()
    with pytest.raises(PendingRollbackError):
        s.query(_Int90Poison).count()
    s.rollback()  # 收尾，不污染后续用例


def test_get_db_session_heals_poisoned_session():
    """get_db_session() 对非活跃 session 先 rollback：毒化不跨取用存活（缺陷 A 兜底）。"""
    _poison_current_session()
    s = get_db_session().registry()  # 取用即自愈
    assert s.query(_Int90Poison).count() == 0


def test_model_query_descriptor_routes_through_heal():
    """Model.query 描述符与显式 get_db_session() 行为一致（同样自愈）。"""
    _poison_current_session()
    assert _Int90Poison.query.count() == 0


# ==================== 缺陷 A：请求级 scope 隔离与清理 ====================

def _registry_size():
    return len(_scoped_session.registry.registry)


def test_request_scope_isolated_and_released():
    """请求级 scope：新请求拿全新 session，release 后该 scope 的 session 归还。"""
    before = _registry_size()

    token = bind_request_session_scope()
    s1 = get_db_session().registry()
    assert _registry_size() == before + 1

    # 本请求内毒化，release 后下个请求不受影响（缺陷 A 主场景）
    s1.add(_Int90Poison(payload=None))
    with pytest.raises(IntegrityError):
        s1.flush()
    release_request_session_scope(token)
    assert _registry_size() == before  # session 已清理，连接归还连接池

    token2 = bind_request_session_scope()
    s2 = get_db_session().registry()
    assert s2 is not s1
    assert s2.is_active
    assert s2.query(_Int90Poison).count() == 0
    release_request_session_scope(token2)


def test_middleware_end_to_end_poison_does_not_leak():
    """DbSessionScopeMiddleware 端到端：毒化请求之后的新请求拿到干净 session。"""
    app = FastAPI()
    app.add_middleware(DbSessionScopeMiddleware)

    @app.get('/int90-poison')
    def poison_route():
        s = get_db_session()
        s.add(_Int90Poison(payload=None))
        try:
            s.flush()
        except IntegrityError:
            pass
        return {'ok': True}

    @app.get('/int90-use')
    def use_route():
        return {'count': get_db_session().query(_Int90Poison).count()}

    client = TestClient(app)
    assert client.get('/int90-poison').json() == {'ok': True}
    # 即便线程池复用同一线程，新请求也拿到干净 session
    assert client.get('/int90-use').json() == {'count': 0}


# ==================== 缺陷 B：logs.task_id 写库边界规范化 ====================

def test_batch_create_normalizes_task_id():
    """数字/数字字符串规范为 int，非数字合成任务 ID（'t1'）置 None，行照常落库。"""
    from task_service.infrastructure.persistence.models.system_models import Log
    from task_service.infrastructure.persistence.log_repository import log_repository

    Log.__table__.create(get_engine(), checkfirst=True)

    payloads = [
        {'level': 'INFO', 'category': 'Task', 'module': 'reevaluator',
         'source': 'backend', 'content': '已提交 E2E 轮次评估', 'task_id': 't1'},
        {'level': 'INFO', 'category': 'Task', 'module': 'reevaluator',
         'source': 'backend', 'content': '数字字符串任务 ID', 'task_id': '123'},
        {'level': 'INFO', 'category': 'Task', 'module': 'reevaluator',
         'source': 'backend', 'content': '整型任务 ID', 'task_id': 42},
        {'level': 'INFO', 'category': 'Task', 'module': 'reevaluator',
         'source': 'backend', 'content': '无任务 ID', 'task_id': None},
    ]
    ids = log_repository.batch_create(payloads)
    assert len(ids) == len(payloads) and all(i is not None for i in ids)

    s = get_db_session()
    try:
        rows = {r.id: r.task_id for r in s.query(Log).filter(Log.id.in_(ids)).all()}
        assert [rows[i] for i in ids] == [None, 123, 42, None]
    finally:
        s.close()


# ==================== 缺陷 C：playback ACL 失败语义 ====================

class _FakeStub:
    """按 behavior(repo) 返回假响应/抛异常的 PlaybackConfigService stub。"""

    def __init__(self, behavior):
        self._behavior = behavior

    def ListPlaybackDevices(self, request):
        return self._behavior('list')

    def GetPlaybackDevice(self, request):
        return self._behavior('get')


def _install_stub(monkeypatch, behavior):
    from shared.clients import grpc_clients
    monkeypatch.setattr(grpc_clients, 'get_playback_config_service_stub',
                        lambda: _FakeStub(behavior))


class _Resp:
    def __init__(self, success, data='', message='', code=0):
        self.success = success
        self.data = data
        self.message = message
        self.code = code


@pytest.fixture()
def acl():
    from audio_service.infrastructure.acl.playback_acl_repository import (
        PlaybackConfigACLRepositoryImpl,
    )
    return PlaybackConfigACLRepositoryImpl()


def test_acl_raises_on_grpc_transport_failure(acl, monkeypatch):
    from audio_service.domain.repositories.acl.playback_acl_repository import (
        PlaybackDeviceQueryError,
    )

    def boom(_):
        raise RuntimeError('connection reset')

    _install_stub(monkeypatch, boom)
    with pytest.raises(PlaybackDeviceQueryError):
        acl.list_playback_devices()
    with pytest.raises(PlaybackDeviceQueryError):
        acl.get_playback_device(1)


def test_acl_raises_on_list_explicit_failure(acl, monkeypatch):
    """列表类接口 success=False 必为故障（空列表走 success=True），必须上抛。"""
    from audio_service.domain.repositories.acl.playback_acl_repository import (
        PlaybackDeviceQueryError,
    )

    _install_stub(monkeypatch, lambda kind: _Resp(False, message='device_service 内部错误'))
    with pytest.raises(PlaybackDeviceQueryError):
        acl.list_playback_devices()
    with pytest.raises(PlaybackDeviceQueryError):
        acl.find_playback_device_by_name('dry-1')


def test_acl_empty_result_stays_business_empty(acl, monkeypatch):
    """正常应答但无匹配仍返回 []/None，不误报故障。"""
    import json as _json

    _install_stub(monkeypatch, lambda kind: _Resp(
        True, data=_json.dumps({'devices': [
            {'id': 7, 'name': 'dry-1', 'device_unique_id': 'uid-7',
             'device_type': 'dry', 'is_deleted': False},
            {'id': 8, 'name': 'old-dev', 'device_unique_id': 'uid-8',
             'device_type': 'dry', 'is_deleted': True},
        ]})))
    assert acl.list_playback_devices()[0]['id'] == 7
    assert acl.find_playback_device_by_name('dry-1')['id'] == 7
    assert acl.find_playback_device_by_name('不存在') is None
    assert acl.find_playback_device_by_unique_id('uid-7')['id'] == 7
    # 已删除设备不算匹配
    assert acl.find_playback_device_by_unique_id('uid-8') is None


def test_acl_get_device_keeps_not_found_none(acl, monkeypatch):
    """GetPlaybackDevice success=False 且未透传 code（旧版本服务，code=0）维持既有 None 契约（INT-92 兼容）。"""
    _install_stub(monkeypatch, lambda kind: _Resp(False, message='未找到播放设备'))
    assert acl.get_playback_device(999) is None


def test_builder_helpers_propagate_infra_failure(monkeypatch):
    """builder 包装层不再吞异常：基础设施失败穿透到调用方（预览/执行链路可见真错）。"""
    from audio_service.infrastructure.audio import playback_config_builder as pcb
    from audio_service.domain.repositories.acl.playback_acl_repository import (
        PlaybackDeviceQueryError,
    )

    def boom(_):
        raise RuntimeError('device_service 不可用')

    _install_stub(monkeypatch, boom)
    with pytest.raises(PlaybackDeviceQueryError):
        pcb._get_playback_device_via_grpc(1)
    with pytest.raises(PlaybackDeviceQueryError):
        pcb._find_playback_device_by_unique_id('uid-x')
    with pytest.raises(PlaybackDeviceQueryError):
        pcb._find_playback_device_by_name('x')


def test_builder_helpers_return_none_for_not_found(monkeypatch):
    """builder 包装层对「正常应答但未找到」仍返回 None（既有降级语义不变）。"""
    from audio_service.infrastructure.audio import playback_config_builder as pcb

    _install_stub(monkeypatch, lambda kind: _Resp(False, message='未找到播放设备'))
    assert pcb._get_playback_device_via_grpc(999) is None
