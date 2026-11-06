# -*- coding: utf-8 -*-
"""INT-61 打回修复：会话亲和「路由」接线单测

P1 阻断项回归——resolve() 生产消费点全部锁定：
- task_service 派发侧：websocket_api 用例认领后 route_or_bind 绑定并按绑定
  直连派发（认领即绑定）；http_api 用例与降级场景回退默认通道
- api_test_service 启动门禁：绑定在其它存活实例的启动请求转发持有实例，
  不在本地执行；降级/本地绑定/转发不可达时本地执行
- StopAPITest / GetAPITestStatus 处理器：绑定在其它存活实例时转发持有实例
  （双副本下控制/状态轮询不再打到无会话副本）
- peer_rpc 转发：直连目标解析、转发去重窗、不可达返回 None
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace

import pytest

import shared.utils.realtime_session_registry as registry_mod
import api_test_service.infrastructure.peer_rpc as peer_rpc_mod
from shared.utils.realtime_session_registry import RealtimeSessionRegistry

SERVICE = 'api_test_service'
TASK = 2001

AFFINITY_REMOTE = {'instance_id': 'inst-B', 'is_local': False,
                   'rerouted': False, 'degraded': False}
AFFINITY_LOCAL = {'instance_id': 'inst-A', 'is_local': True,
                  'rerouted': False, 'degraded': False}
AFFINITY_DEGRADED = {'instance_id': 'inst-A', 'is_local': True,
                     'rerouted': False, 'degraded': True}

TARGET_B = {'instance_id': 'inst-B', 'host': 'inst-b.host', 'grpc_port': 50071}


class _FakeRegistry:
    """可控 resolve/route_or_bind 的注册表桩"""

    def __init__(self, resolve_result=None, route_result=None, raise_exc=None):
        self._resolve_result = resolve_result
        self._route_result = route_result
        self._raise_exc = raise_exc

    def resolve(self, task_id, local_instance_id=None):
        if self._raise_exc:
            raise self._raise_exc
        return dict(self._resolve_result or AFFINITY_LOCAL)

    def route_or_bind(self, task_id):
        if self._raise_exc:
            raise self._raise_exc
        return self._route_result


@pytest.fixture(autouse=True)
def _clear_forward_dedup():
    peer_rpc_mod._recent_start_forwards.clear()
    yield
    peer_rpc_mod._recent_start_forwards.clear()


# ==================== peer_rpc 转发 ====================

class _FakeStub:
    def __init__(self, resp=None, exc=None):
        self.calls = []
        self._resp = resp
        self._exc = exc

    def CreateAPITest(self, req, *a, **k):
        self.calls.append(('CreateAPITest', req))
        if self._exc:
            raise self._exc
        return self._resp

    def StopAPITest(self, req, *a, **k):
        self.calls.append(('StopAPITest', req))
        if self._exc:
            raise self._exc
        return self._resp

    def GetAPITestStatus(self, req, *a, **k):
        self.calls.append(('GetAPITestStatus', req))
        if self._exc:
            raise self._exc
        return self._resp


def _patch_peer(monkeypatch, target=TARGET_B, resp=None, exc=None):
    stub = _FakeStub(resp=resp, exc=exc)
    monkeypatch.setattr(peer_rpc_mod, 'get_instance_target',
                        lambda **k: target)
    monkeypatch.setattr('shared.clients.grpc_instance_client.get_api_test_service_stub_for_instance',
                        lambda host, grpc_port: stub)
    return stub


def _resp(payload):
    return SimpleNamespace(success=True, message='ok', data=json.dumps(payload))


class TestForwardCreateApiTest:
    def test_forwards_to_holder_instance(self, monkeypatch):
        stub = _patch_peer(monkeypatch, resp=_resp({'success': True, 'message': 'API test task started'}))
        result = peer_rpc_mod.forward_create_api_test(TASK, [11], [], 'inst-B')
        assert result['success'] is True
        rpc, req = stub.calls[0]
        assert rpc == 'CreateAPITest'
        assert req.task_id == str(TASK)
        assert json.loads(req.test_config)['case_ids'] == [11]

    def test_target_unresolvable_returns_none(self, monkeypatch):
        monkeypatch.setattr(peer_rpc_mod, 'get_instance_target', lambda **k: None)
        assert peer_rpc_mod.forward_create_api_test(TASK, [], [], 'inst-B') is None

    def test_peer_unreachable_returns_none(self, monkeypatch):
        _patch_peer(monkeypatch, exc=ConnectionError('peer down'))
        assert peer_rpc_mod.forward_create_api_test(TASK, [], [], 'inst-B') is None

    def test_dedup_window_blocks_second_forward(self, monkeypatch):
        _patch_peer(monkeypatch, resp=_resp({'success': True}))
        assert peer_rpc_mod.forward_create_api_test(TASK, [], [], 'inst-B') is not None
        assert peer_rpc_mod.forward_create_api_test(TASK, [], [], 'inst-B') is None


class TestForwardStopAndStatus:
    def test_stop_forward(self, monkeypatch):
        stub = _patch_peer(monkeypatch, resp=_resp({'success': True, 'message': 'stopped'}))
        result = peer_rpc_mod.forward_stop_api_test(TASK, 'inst-B')
        assert result['success'] is True
        rpc, req = stub.calls[0]
        assert rpc == 'StopAPITest'
        assert req.task_id == str(TASK)

    def test_status_forward(self, monkeypatch):
        stub = _patch_peer(monkeypatch, resp=_resp(
            {'task_id': TASK, 'status': 'running', 'round_progress': None}))
        result = peer_rpc_mod.forward_get_api_test_status(TASK, 'inst-B')
        assert result['status'] == 'running'
        rpc, _ = stub.calls[0]
        assert rpc == 'GetAPITestStatus'

    def test_unreachable_returns_none(self, monkeypatch):
        _patch_peer(monkeypatch, exc=ConnectionError('peer down'))
        assert peer_rpc_mod.forward_stop_api_test(TASK, 'inst-B') is None
        assert peer_rpc_mod.forward_get_api_test_status(TASK, 'inst-B') is None


# ==================== api_test_service 启动门禁 ====================

@pytest.fixture
def service():
    from api_test_service.core.api_test_service import api_test_service
    api_test_service.init_app()
    return api_test_service


class TestStartAffinityGate:
    def test_bound_elsewhere_forwards_and_skips_local(self, service, monkeypatch):
        service._session_registry = _FakeRegistry(resolve_result=AFFINITY_REMOTE)
        forwarded = {'success': True, 'task_id': TASK, 'message': 'from holder'}
        calls = []
        monkeypatch.setattr(peer_rpc_mod, 'forward_create_api_test',
                            lambda task_id, case_ids, api_ids, instance_id:
                            calls.append((task_id, case_ids, api_ids, instance_id))
                            or forwarded)
        result = service.start_task(TASK, [11], [])
        assert result is forwarded
        assert calls == [(TASK, [11], [], 'inst-B')]
        assert TASK not in service._running_tasks  # 本地未执行

    def test_forward_unreachable_falls_back_local_gate_passes(self, service, monkeypatch):
        service._session_registry = _FakeRegistry(resolve_result=AFFINITY_REMOTE)
        monkeypatch.setattr(peer_rpc_mod, 'forward_create_api_test',
                            lambda *a, **k: None)
        assert service._affinity_forward_start(TASK, [], []) is None  # 交还本地流程

    def test_local_binding_executes_locally(self, service, monkeypatch):
        service._session_registry = _FakeRegistry(resolve_result=AFFINITY_LOCAL)
        called = []
        monkeypatch.setattr(peer_rpc_mod, 'forward_create_api_test',
                            lambda *a, **k: called.append(1))
        assert service._affinity_forward_start(TASK, [], []) is None
        assert called == []

    def test_degraded_executes_locally(self, service, monkeypatch):
        service._session_registry = _FakeRegistry(resolve_result=AFFINITY_DEGRADED)
        monkeypatch.setattr(peer_rpc_mod, 'forward_create_api_test',
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError('must not forward')))
        assert service._affinity_forward_start(TASK, [], []) is None

    def test_resolve_exception_executes_locally(self, service):
        service._session_registry = _FakeRegistry(raise_exc=RuntimeError('boom'))
        assert service._affinity_forward_start(TASK, [], []) is None

    def test_start_task_delegates_to_gate_first(self, service, monkeypatch):
        forwarded = {'success': True, 'task_id': TASK}
        monkeypatch.setattr(service, '_affinity_forward_start',
                            lambda task_id, case_ids, api_ids: forwarded)
        assert service.start_task(TASK, [], []) is forwarded
        assert TASK not in service._running_tasks


# ==================== Stop / Status 处理器亲和路由 ====================

class TestStopStatusHandlerGates:
    def _patch_registry(self, monkeypatch, resolve_result):
        monkeypatch.setattr(registry_mod, 'RealtimeSessionRegistry',
                            lambda *a, **k: _FakeRegistry(resolve_result=resolve_result))

    def test_stop_forwards_when_bound_elsewhere(self, monkeypatch):
        self._patch_registry(monkeypatch, AFFINITY_REMOTE)
        from api_test_service.application.handlers.command_handlers import (
            StopAPITestCommand, stop_api_test_handler, _forward_if_bound_elsewhere,
        )
        forwarded = {'success': True, 'message': 'stopped'}
        monkeypatch.setattr(peer_rpc_mod, 'forward_stop_api_test',
                            lambda task_id, instance_id: forwarded)
        result = stop_api_test_handler.handle(StopAPITestCommand(task_id=TASK))
        assert result is forwarded
        assert result['task_id'] == TASK
        assert _forward_if_bound_elsewhere is not None  # 助手可导入

    def test_stop_local_when_binding_local(self, monkeypatch):
        self._patch_registry(monkeypatch, AFFINITY_LOCAL)
        from api_test_service.application.handlers.command_handlers import (
            StopAPITestCommand, stop_api_test_handler,
        )
        from api_test_service.core.api_test_service import api_test_service
        api_test_service.init_app()
        result = stop_api_test_handler.handle(StopAPITestCommand(task_id=TASK))
        assert result['success'] is True  # 本地停语义（幂等）

    def test_status_forwards_when_bound_elsewhere(self, monkeypatch):
        self._patch_registry(monkeypatch, AFFINITY_REMOTE)
        from api_test_service.application.handlers.query_handlers import (
            GetAPITestStatusQuery, get_api_test_status_handler,
        )
        forwarded = {'task_id': TASK, 'status': 'running'}
        monkeypatch.setattr(peer_rpc_mod, 'forward_get_api_test_status',
                            lambda task_id, instance_id: forwarded)
        result = get_api_test_status_handler.handle(GetAPITestStatusQuery(task_id=TASK))
        assert result['status'] == 'running'

    def test_status_local_when_degraded(self, monkeypatch):
        self._patch_registry(monkeypatch, AFFINITY_DEGRADED)
        from api_test_service.application.handlers.query_handlers import (
            GetAPITestStatusQuery, get_api_test_status_handler,
        )
        from api_test_service.core.api_test_service import api_test_service
        api_test_service.init_app()
        result = get_api_test_status_handler.handle(GetAPITestStatusQuery(task_id=TASK))
        assert result['status'] == 'idle'  # 本地内存语义（无会话副本兜底行为不变）

    def test_forward_unreachable_falls_back_local(self, monkeypatch):
        self._patch_registry(monkeypatch, AFFINITY_REMOTE)
        from api_test_service.application.handlers.query_handlers import (
            GetAPITestStatusQuery, get_api_test_status_handler,
        )
        from api_test_service.core.api_test_service import api_test_service
        api_test_service.init_app()
        monkeypatch.setattr(peer_rpc_mod, 'forward_get_api_test_status',
                            lambda task_id, instance_id: None)
        result = get_api_test_status_handler.handle(GetAPITestStatusQuery(task_id=TASK))
        assert result['status'] == 'idle'

    def test_helper_forwarded_dict_gets_task_id(self, monkeypatch):
        self._patch_registry(monkeypatch, AFFINITY_REMOTE)
        from api_test_service.application.handlers.command_handlers import _forward_if_bound_elsewhere
        result = _forward_if_bound_elsewhere(TASK, lambda task_id, instance_id: {'success': True})
        assert result == {'success': True, 'task_id': TASK}

    def test_helper_none_when_forward_unreachable(self, monkeypatch):
        self._patch_registry(monkeypatch, AFFINITY_REMOTE)
        from api_test_service.application.handlers.command_handlers import _forward_if_bound_elsewhere
        assert _forward_if_bound_elsewhere(TASK, lambda task_id, instance_id: None) is None


# ==================== task_service 派发侧（认领即绑定） ====================

from task_service.core.execution_engine.mixins.task_dispatch import TaskDispatchMixin


class _TcRel:
    def __init__(self, tc_rel_id, device_id=None):
        self.id = tc_rel_id
        self.device_id = device_id


class _DispatchHarness(TaskDispatchMixin):
    """TaskDispatchMixin 最小宿主：只实现用例分发路径依赖"""

    def __init__(self):
        self.exec_calls = []

    def _log(self, level, content, task_id=None, **k):
        pass

    def _claim_case(self, task_id, tc_rel_id, session):
        return 1

    def _execute_api_case(self, task_id, tc_rel_id, dispatch_target=None,
                          device_type=None, device_id=None):
        self.exec_calls.append({'task_id': task_id, 'tc_rel_id': tc_rel_id,
                                'dispatch_target': dispatch_target,
                                'device_type': device_type,
                                'device_id': device_id})

    def _finalize_dispatch_failure(self, tc_rel):
        pass


class _FakeSession:
    def commit(self):
        pass

    def rollback(self):
        pass


class TestDispatchSideRouting:
    def _patch_route(self, monkeypatch, route_result=None, raise_exc=None):
        monkeypatch.setattr(registry_mod, 'RealtimeSessionRegistry',
                            lambda *a, **k: _FakeRegistry(route_result=route_result,
                                                          raise_exc=raise_exc))

    def test_websocket_case_routes_by_binding(self, monkeypatch):
        self._patch_route(monkeypatch, route_result=TARGET_B)
        h = _DispatchHarness()
        h._dispatch_api_case(TASK, _TcRel(11), _FakeSession(),
                             device_type='websocket_api')
        assert h.exec_calls[0]['dispatch_target'] == TARGET_B
        assert h.exec_calls[0]['tc_rel_id'] == 11

    def test_http_case_bypasses_affinity(self, monkeypatch):
        """http_api 用例不走亲和路由（回退默认负载均衡通道），行为不变"""
        self._patch_route(monkeypatch, route_result=TARGET_B)
        h = _DispatchHarness()
        h._dispatch_api_case(TASK, _TcRel(12), _FakeSession(), device_type='http_api')
        # 若误走亲和，dispatch_target 会是 TARGET_B
        assert h.exec_calls[0]['dispatch_target'] is None

    def test_route_failure_falls_back_default_channel(self, monkeypatch):
        """route_or_bind 异常 → None → 默认通道，分发不失败"""
        self._patch_route(monkeypatch, raise_exc=RuntimeError('redis down'))
        h = _DispatchHarness()
        h._dispatch_api_case(TASK, _TcRel(13), _FakeSession(),
                             device_type='websocket_api')
        assert h.exec_calls[0]['dispatch_target'] is None

    def test_route_degraded_returns_none_target(self, monkeypatch):
        self._patch_route(monkeypatch, route_result=None)
        h = _DispatchHarness()
        h._dispatch_api_case(TASK, _TcRel(14), _FakeSession(),
                             device_type='websocket_api')
        assert h.exec_calls[0]['dispatch_target'] is None

    def test_route_or_bind_wired_to_shared_registry(self, monkeypatch):
        """_route_realtime_dispatch 消费 RealtimeSessionRegistry.route_or_bind"""
        seen = []
        monkeypatch.setattr(registry_mod, 'RealtimeSessionRegistry',
                            lambda *a, **k: SimpleNamespace(
                                route_or_bind=lambda task_id: seen.append(task_id) or TARGET_B))
        h = _DispatchHarness()
        target = h._route_realtime_dispatch(TASK)
        assert target == TARGET_B
        assert seen == [TASK]


# ==================== 多副本注册地址（亲和路由可寻址前提） ====================

class TestAdvertiseHost:
    def test_env_override_wins(self, monkeypatch):
        from api_test_service.app import _self_advertise_host, _ADVERTISE_HOST_ENV
        monkeypatch.setenv(_ADVERTISE_HOST_ENV, '10.1.2.3')
        assert _self_advertise_host() == '10.1.2.3'

    def test_resolved_or_fallback_is_non_empty(self, monkeypatch):
        """缺省解析本机地址（多副本逐实例可直达），失败回退 SERVICE_HOST"""
        from api_test_service.app import _self_advertise_host, _ADVERTISE_HOST_ENV
        monkeypatch.delenv(_ADVERTISE_HOST_ENV, raising=False)
        assert _self_advertise_host()
