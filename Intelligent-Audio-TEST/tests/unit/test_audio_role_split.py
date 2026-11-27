# -*- coding: utf-8 -*-
"""audio 拆分角色回归（docs/audio服务拆分方案.md §3/§4/§5/§6）。

锁定四件事：
- 角色解析：AUDIO_ROLE 缺省 server、agent 合法、非法值报错；
- 客户端 stub 路由：数据面走 AUDIO_SERVICE_*，硬件面走 AUDIO_AGENT_*；
- 执行机地址解析：Redis `audio_agent` 注册表按 lab 命中，未命中回退静态地址；
- 服务端注册：server 注册数据面 AudioConfigService（试听两 RPC 显式 UNIMPLEMENTED），
  agent 只注册试听裁剪版 + 播放。

另覆盖 split 引入的两条 RPC：RecordPlaybackHistory（含幂等键去重）与
ResolveAudioByName，以及 agent 侧元数据 ACL 走 gRPC 而非本地仓储。
"""
import os
import types

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.proto import audio_service_pb2 as pb
from shared.utils.grpc_json import dumps, loads


# ---------------------------------------------------------------- 角色解析

def test_default_audio_role_is_server(monkeypatch):
    from audio_service.interfaces.grpc.server import _resolve_audio_role
    monkeypatch.delenv('AUDIO_ROLE', raising=False)
    assert _resolve_audio_role() == 'server'


def test_explicit_agent_role(monkeypatch):
    from audio_service.interfaces.grpc.server import _resolve_audio_role
    monkeypatch.setenv('AUDIO_ROLE', ' AGENT ')
    assert _resolve_audio_role() == 'agent'


def test_invalid_audio_role_raises(monkeypatch):
    from audio_service.interfaces.grpc.server import _resolve_audio_role
    monkeypatch.setenv('AUDIO_ROLE', 'gateway')
    with pytest.raises(ValueError):
        _resolve_audio_role()


def test_config_is_audio_agent_role(monkeypatch):
    from shared.infrastructure.config import is_audio_agent_role
    monkeypatch.setenv('AUDIO_ROLE', 'agent')
    assert is_audio_agent_role() is True
    monkeypatch.setenv('AUDIO_ROLE', 'server')
    assert is_audio_agent_role() is False
    monkeypatch.delenv('AUDIO_ROLE', raising=False)
    assert is_audio_agent_role() is False


# ---------------------------------------------------- 执行机地址解析（按 lab）

def test_resolve_audio_agent_addr_prefers_registry(monkeypatch):
    import shared.utils.service_registry as registry_mod
    from shared.clients._grpc_stubs import resolve_audio_agent_addr

    class _Registry:
        def get_one(self, name, lab_name=None):
            if name == 'audio_agent' and lab_name == 'lab-b':
                return {'host': '10.0.0.8', 'grpc_port': 50052}
            return None

    monkeypatch.setattr(registry_mod, 'RedisServiceRegistry', _Registry)
    assert resolve_audio_agent_addr('lab-b') == '10.0.0.8:50052'


def test_resolve_audio_agent_addr_falls_back_to_static(monkeypatch):
    import shared.utils.service_registry as registry_mod
    from shared.clients import _grpc_stubs as stubs

    class _Registry:
        def get_one(self, name, lab_name=None):
            return None

    monkeypatch.setattr(registry_mod, 'RedisServiceRegistry', _Registry)
    assert stubs.resolve_audio_agent_addr('lab-x') == stubs.AUDIO_AGENT_GRPC_ADDR


def test_resolve_audio_agent_addr_registry_error_falls_back(monkeypatch):
    import shared.utils.service_registry as registry_mod
    from shared.clients import _grpc_stubs as stubs

    class _Registry:
        def get_one(self, name, lab_name=None):
            raise RuntimeError('redis down')

    monkeypatch.setattr(registry_mod, 'RedisServiceRegistry', _Registry)
    assert stubs.resolve_audio_agent_addr() == stubs.AUDIO_AGENT_GRPC_ADDR


@pytest.fixture(autouse=True)
def _clear_agent_addr_cache():
    from shared.clients import _grpc_stubs as stubs
    stubs._audio_agent_addr_cache.clear()
    yield
    stubs._audio_agent_addr_cache.clear()


def test_resolve_audio_agent_addr_cached_within_ttl(monkeypatch):
    import shared.utils.service_registry as registry_mod
    from shared.clients import _grpc_stubs as stubs

    hits = {'n': 0}

    class _Registry:
        def get_one(self, name, lab_name=None):
            hits['n'] += 1
            return {'host': '10.0.0.8', 'grpc_port': 50052}

    monkeypatch.setattr(registry_mod, 'RedisServiceRegistry', _Registry)
    assert stubs.resolve_audio_agent_addr('lab-a') == '10.0.0.8:50052'
    assert stubs.resolve_audio_agent_addr('lab-a') == '10.0.0.8:50052'
    assert hits['n'] == 1


# ------------------------------------------------------------ stub 双通道路由

def _patch_stub_classes(monkeypatch):
    """把生成的 Stub 类替换成记录 channel 的假类，避免真实建连。"""
    from shared.proto import audio_service_pb2_grpc as pbg
    seen = {}

    def _make(name):
        class _Stub:
            def __init__(self, channel):
                seen[name] = channel
        return _Stub

    for cls_name in ('AudioConfigServiceStub', 'AudioServiceStub', 'PlaybackServiceStub'):
        monkeypatch.setattr(pbg, cls_name, _make(cls_name))
    return seen


def test_audio_config_stub_uses_data_plane_channel(monkeypatch):
    from shared.clients import _grpc_stubs as stubs

    seen = _patch_stub_classes(monkeypatch)
    monkeypatch.setattr(stubs, '_get_audio_channel', lambda *a, **k: 'DATA')
    stubs.get_audio_config_service_stub.cache_clear()
    try:
        stubs.get_audio_config_service_stub()
    finally:
        stubs.get_audio_config_service_stub.cache_clear()
    assert seen['AudioConfigServiceStub'] == 'DATA'


def test_hardware_stubs_use_agent_channel(monkeypatch):
    from shared.clients import _grpc_stubs as stubs

    seen = _patch_stub_classes(monkeypatch)
    used = {}

    def _agent_channel(addr):
        used['addr'] = addr
        return 'AGENT'

    monkeypatch.setattr(stubs, '_get_audio_agent_channel', _agent_channel)
    monkeypatch.setattr(stubs, 'resolve_audio_agent_addr', lambda lab=None: 'AGENT:50052')
    stubs.get_audio_service_stub('lab-a')
    stubs.get_playback_service_stub('lab-a')
    stubs.get_audio_agent_config_stub('lab-a')
    assert used['addr'] == 'AGENT:50052'
    assert seen['AudioServiceStub'] == 'AGENT'
    assert seen['PlaybackServiceStub'] == 'AGENT'
    assert seen['AudioConfigServiceStub'] == 'AGENT'


# ------------------------------------------------------------ 服务端角色注册

class _FakeGrpcServer:
    def __init__(self):
        self.bound = None
        self.started = False
        self.stopped = None

    def add_insecure_port(self, addr):
        self.bound = addr
        return 1

    def start(self):
        self.started = True

    def stop(self, grace):
        self.stopped = grace


@pytest.fixture(autouse=True)
def _restore_server_globals():
    from audio_service.interfaces.grpc import server as srv
    orig_server, orig_shutdown = srv._server, srv._shutdown_started
    yield
    srv._server, srv._shutdown_started = orig_server, orig_shutdown


def _patch_registration(monkeypatch):
    """隔离 start_grpc_server 的外部依赖，返回注册调用记录。"""
    from audio_service.interfaces.grpc import server as srv
    from shared.proto import audio_service_pb2_grpc as audio_grpc

    calls = {'config': [], 'audio': [], 'playback': [], 'register': [], 'init_db': 0,
             'init_driver': 0, 'warmup': 0, 'cleaner': 0}

    monkeypatch.setattr(srv, '_configure_pydub_ffmpeg', lambda: None)
    monkeypatch.setattr(srv, 'config_manager',
                        types.SimpleNamespace(get_value=lambda *a, **k: 1))
    fake_server = _FakeGrpcServer()
    monkeypatch.setattr(srv, 'grpc', types.SimpleNamespace(server=lambda *a, **k: fake_server))

    monkeypatch.setattr(audio_grpc, 'add_AudioConfigServiceServicer_to_server',
                        lambda svc, server: calls['config'].append(svc))
    monkeypatch.setattr(audio_grpc, 'add_AudioServiceServicer_to_server',
                        lambda svc, server: calls['audio'].append(svc))
    monkeypatch.setattr(audio_grpc, 'add_PlaybackServiceServicer_to_server',
                        lambda svc, server: calls['playback'].append(svc))
    monkeypatch.setattr(srv, '_register_audio_agent',
                        lambda port: calls['register'].append(port))
    return calls, fake_server


def test_server_role_registers_data_plane_config_servicer(monkeypatch):
    from audio_service.interfaces.grpc import server as srv
    from audio_service.interfaces.grpc.servicers import (
        AudioConfigServiceServicer, DataPlaneAudioConfigServicer,
    )

    calls, fake_server = _patch_registration(monkeypatch)
    monkeypatch.setenv('AUDIO_ROLE', 'server')

    import shared.models.database as dbmod
    monkeypatch.setattr(dbmod, 'init_db', lambda **k: calls.__setitem__('init_db', 1))

    import audio_service.infrastructure.persistence.soft_delete_cleaner as cleaner_mod

    class _Cleaner:
        def start(self):
            calls['cleaner'] = 1

    monkeypatch.setattr(cleaner_mod, 'get_cleaner', lambda: _Cleaner())

    import audio_service.infrastructure.acl.tag_acl_repository as tag_mod
    monkeypatch.setattr(tag_mod, 'start_tag_acl_warmup',
                        lambda: calls.__setitem__('warmup', 1))

    srv.start_grpc_server(port=50052)

    assert fake_server.started is True
    assert calls['init_db'] == 1 and calls['cleaner'] == 1 and calls['warmup'] == 1
    assert calls['init_driver'] == 0
    assert len(calls['config']) == 1
    assert isinstance(calls['config'][0], DataPlaneAudioConfigServicer)
    assert isinstance(calls['config'][0], AudioConfigServiceServicer)
    assert calls['audio'] == [] and calls['playback'] == []
    assert calls['register'] == []


def test_data_plane_rejects_preview_rpcs():
    """数据面无试听能力：两 RPC 必须显式 UNIMPLEMENTED（§3.1/§5.1）。"""
    import grpc
    from audio_service.interfaces.grpc.servicers import DataPlaneAudioConfigServicer

    class _Ctx:
        def __init__(self):
            self.aborted = None

        def abort(self, code, message):
            self.aborted = (code, message)
            raise RuntimeError(code.name)

    svc = DataPlaneAudioConfigServicer()
    ctx = _Ctx()
    with pytest.raises(RuntimeError):
        svc.PreviewAudio(pb.PreviewAudioRequest(audio_id=1), ctx)
    assert ctx.aborted[0] == grpc.StatusCode.UNIMPLEMENTED
    ctx = _Ctx()
    with pytest.raises(RuntimeError):
        svc.StopPreviewAudio(pb.StopPreviewAudioRequest(audio_id=1), ctx)
    assert ctx.aborted[0] == grpc.StatusCode.UNIMPLEMENTED


def test_agent_role_registers_preview_only(monkeypatch):
    from audio_service.interfaces.grpc import server as srv
    from audio_service.interfaces.grpc.servicers import (
        AudioServiceServicer, PlaybackServiceServicer, PreviewAudioConfigServicer,
    )

    calls, fake_server = _patch_registration(monkeypatch)
    monkeypatch.setenv('AUDIO_ROLE', 'agent')

    import audio_service.infrastructure.audio.audio_engine as engine_mod
    monkeypatch.setattr(engine_mod.audio_service, 'init_driver',
                        lambda: calls.__setitem__('init_driver', 1))

    srv.start_grpc_server(port=50052)

    assert fake_server.started is True
    assert calls['init_db'] == 0 and calls['warmup'] == 0
    assert calls['init_driver'] == 1
    assert len(calls['config']) == 1
    assert isinstance(calls['config'][0], PreviewAudioConfigServicer)
    assert len(calls['audio']) == 1 and isinstance(calls['audio'][0], AudioServiceServicer)
    assert len(calls['playback']) == 1
    assert isinstance(calls['playback'][0], PlaybackServiceServicer)
    assert calls['register'] == [50052]


# ------------------------------------------------- 执行机历史回写本地重试队列

def _queue_module(tmp_path, monkeypatch):
    import audio_service.infrastructure.acl.playback_history_queue as q
    monkeypatch.setenv('PLAYBACK_HISTORY_QUEUE_DIR', str(tmp_path))
    monkeypatch.setattr(q, '_ensure_worker', lambda: None)  # 不启后台线程
    return q


def test_history_queue_success_does_not_persist(tmp_path, monkeypatch):
    q = _queue_module(tmp_path, monkeypatch)
    monkeypatch.setattr(q, '_send', lambda record: True)

    assert q.submit_playback_history({'audio_id': 1}) is True
    assert q.flush_pending() == 0
    assert not (tmp_path / 'pending.jsonl').exists()


def test_history_queue_failure_persists_with_idempotency_key(tmp_path, monkeypatch):
    import json
    q = _queue_module(tmp_path, monkeypatch)

    def _boom(record):
        raise RuntimeError('server down')

    monkeypatch.setattr(q, '_send', _boom)

    assert q.submit_playback_history({'audio_id': 2}) is False
    lines = (tmp_path / 'pending.jsonl').read_text(encoding='utf-8').splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record['data'] == {'audio_id': 2}
    assert record['idempotency_key']


def test_history_queue_flush_drops_sent_records(tmp_path, monkeypatch):
    q = _queue_module(tmp_path, monkeypatch)
    monkeypatch.setattr(q, '_send', lambda record: record['data']['audio_id'] == 1)
    q._append({'idempotency_key': 'a', 'data': {'audio_id': 1}})
    q._append({'idempotency_key': 'b', 'data': {'audio_id': 2}})

    assert q.flush_pending() == 1
    remaining = q._read_all()
    assert [r['idempotency_key'] for r in remaining] == ['b']


def test_history_queue_flush_keeps_all_on_rpc_error(tmp_path, monkeypatch):
    q = _queue_module(tmp_path, monkeypatch)

    def _boom(record):
        raise RuntimeError('server down')

    monkeypatch.setattr(q, '_send', _boom)
    q._append({'idempotency_key': 'a', 'data': {'audio_id': 1}})

    assert q.flush_pending() == 1
    assert len(q._read_all()) == 1


# ------------------------------------------- RecordPlaybackHistory / ResolveAudioByName

def test_record_playback_history_forwards_idempotency_key():
    from audio_service.interfaces.grpc.servicers import AudioConfigServiceServicer

    svc = AudioConfigServiceServicer()
    captured = {}

    class _Cmd:
        def handle_record_playback_history(self, data):
            captured.update(data)
            return {'success': True}

    svc._cmd_handler = _Cmd()
    resp = svc.RecordPlaybackHistory(pb.RecordPlaybackHistoryRequest(
        data=dumps({'audio_id': 3}), idempotency_key='k1'))

    assert resp.success is True
    assert captured['idempotency_key'] == 'k1'
    assert captured['audio_id'] == 3


def test_record_playback_history_error_returns_failure():
    from audio_service.interfaces.grpc.servicers import AudioConfigServiceServicer

    svc = AudioConfigServiceServicer()

    class _Cmd:
        def handle_record_playback_history(self, data):
            raise RuntimeError('db down')

    svc._cmd_handler = _Cmd()
    resp = svc.RecordPlaybackHistory(pb.RecordPlaybackHistoryRequest(data='{}'))
    assert resp.success is False
    assert 'db down' in resp.message


def test_resolve_audio_by_name_returns_items():
    from audio_service.interfaces.grpc.servicers import AudioConfigServiceServicer

    svc = AudioConfigServiceServicer()
    seen = {}

    class _Query:
        def handle_resolve_by_names(self, names):
            seen['names'] = names
            return {'success': True, 'data': [{'id': 9, 'name': 'a.wav'}]}

    svc._query_handler = _Query()
    resp = svc.ResolveAudioByName(pb.ResolveAudioByNameRequest(
        data=dumps({'names': ['a.wav']})))

    assert resp.success is True
    assert seen['names'] == ['a.wav']
    assert loads(resp.data, [])[0]['id'] == 9


def _make_history_handler():
    from audio_service.application.handlers.audio_command_handler import AudioCommandHandler

    handler = object.__new__(AudioCommandHandler)

    class _Repo:
        def __init__(self):
            self.records = []
            self.committed = False

        def record_playback_history(self, data):
            self.records.append(data)

        def commit(self):
            self.committed = True

    handler.repo = _Repo()
    return handler


def test_record_playback_history_skips_duplicate_key(monkeypatch):
    import shared.utils.redis_pubsub as pubsub

    class _Redis:
        def set(self, *a, **k):
            return False  # NX 未设置成功 = 幂等命中

    monkeypatch.setattr(pubsub, 'RedisPubSub',
                        lambda: types.SimpleNamespace(redis_client=_Redis()))
    handler = _make_history_handler()

    result = handler.handle_record_playback_history(
        {'audio_id': 1, 'idempotency_key': 'dup'})

    assert result.get('success') is True
    assert result.get('message') == 'duplicate'
    assert handler.repo.records == []


def test_record_playback_history_writes_and_pops_internal_fields(monkeypatch):
    import shared.utils.redis_pubsub as pubsub

    class _Redis:
        def set(self, *a, **k):
            return True

    monkeypatch.setattr(pubsub, 'RedisPubSub',
                        lambda: types.SimpleNamespace(redis_client=_Redis()))
    handler = _make_history_handler()

    result = handler.handle_record_playback_history(
        {'audio_id': 1, 'idempotency_key': 'k', 'user_id': 7})

    assert result.get('success') is True
    assert handler.repo.records == [{'audio_id': 1}]
    assert handler.repo.committed is True


def test_record_playback_history_redis_error_still_writes(monkeypatch):
    import shared.utils.redis_pubsub as pubsub

    def _boom():
        raise RuntimeError('redis down')

    monkeypatch.setattr(pubsub, 'RedisPubSub', _boom)
    handler = _make_history_handler()

    result = handler.handle_record_playback_history(
        {'audio_id': 2, 'idempotency_key': 'k2'})

    assert result.get('success') is True
    assert handler.repo.records == [{'audio_id': 2}]


# --------------------------------------------------- agent 元数据 ACL 走 gRPC

def test_agent_metadata_get_audio_uses_grpc(monkeypatch):
    import shared.clients.grpc_clients as clients
    from audio_service.infrastructure.acl.audio_metadata_acl import AudioMetadataProvider

    monkeypatch.setenv('AUDIO_ROLE', 'agent')
    calls = {}

    class _Stub:
        def GetAudiosByIds(self, request):
            calls['ids'] = loads(request.data, {})['ids']
            return types.SimpleNamespace(
                success=True,
                data=dumps([{'id': 5, 'name': 'x.wav', 'file_path': '/p/x.wav'}]))

    monkeypatch.setattr(clients, 'get_audio_config_service_stub', lambda: _Stub())
    meta = AudioMetadataProvider().get_audio(5)

    assert calls['ids'] == [5]
    assert meta.id == 5 and meta.filename == 'x.wav' and meta.file_path == '/p/x.wav'


def test_agent_metadata_find_by_name_uses_grpc(monkeypatch):
    import shared.clients.grpc_clients as clients
    from audio_service.infrastructure.acl.audio_metadata_acl import AudioMetadataProvider

    monkeypatch.setenv('AUDIO_ROLE', 'agent')
    calls = {}

    class _Stub:
        def ResolveAudioByName(self, request):
            calls['names'] = loads(request.data, {})['names']
            return types.SimpleNamespace(success=True, data=dumps([{'id': 6, 'name': 'n.wav'}]))

    monkeypatch.setattr(clients, 'get_audio_config_service_stub', lambda: _Stub())
    meta = AudioMetadataProvider().find_audio_by_name('n.wav')

    assert calls['names'] == ['n.wav']
    assert meta.id == 6


def test_agent_metadata_record_history_uses_queue(monkeypatch):
    import audio_service.infrastructure.acl.playback_history_queue as queue_mod
    from audio_service.infrastructure.acl.audio_metadata_acl import AudioMetadataProvider

    monkeypatch.setenv('AUDIO_ROLE', 'agent')
    submitted = {}
    monkeypatch.setattr(queue_mod, 'submit_playback_history',
                        lambda data: submitted.update(data) or True)

    AudioMetadataProvider().record_playback_history({'audio_id': 8})

    assert submitted == {'audio_id': 8}


def test_server_metadata_uses_local_repo(monkeypatch):
    from audio_service.infrastructure.acl.audio_metadata_acl import AudioMetadataProvider

    monkeypatch.setenv('AUDIO_ROLE', 'server')

    class _Repo:
        def __init__(self):
            self.calls = []

        def get_audio(self, audio_id):
            self.calls.append(('get', audio_id))
            return 'local-audio'

        def record_playback_history(self, data):
            self.calls.append(('history', data))

        def commit(self):
            self.calls.append(('commit', None))

    repo = _Repo()
    provider = AudioMetadataProvider(repo=repo)

    assert provider.get_audio(1) == 'local-audio'
    provider.record_playback_history({'audio_id': 1})
    assert repo.calls == [('get', 1), ('history', {'audio_id': 1}), ('commit', None)]
