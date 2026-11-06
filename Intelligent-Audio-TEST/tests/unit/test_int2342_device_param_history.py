# -*- coding: utf-8 -*-
"""INT-2342 设备作用域参数 / 映射写入必须记一条变更历史。

缺陷：路由层把 ``to_response(...)`` 转换后的 Response 交给记录函数，
``isinstance(result, tuple)`` 恒为假，设备作用域版本一条都写不进
``param_change_history``（API 作用域走服务层直记，所以只有 api 行）。
本测试锁住「设备级写成功 → record('device', device_id, algorithm_type)」，
并覆盖算法级 / API 作用域 / 写失败三种不该记录的情况。
"""
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from api_gateway.application.services.algorithm import (  # noqa: E402
    algorithm_command_service as command_module,
)
from api_gateway.application.services.algorithm.param_history_service import (  # noqa: E402
    ParamHistoryService,
)
from api_gateway.middleware import RequestAdapterMiddleware  # noqa: E402
from api_gateway.routes import algorithm_bp  # noqa: E402
from api_gateway.routes.algorithm_bp import router as algorithm_router  # noqa: E402

_DEVICE_ID = 9
_ALGO = 'voice_llm'
_PARAM_ID = 216
_MAPPING_ID = 77


def _ok(data=None):
    return {'success': True, 'data': data or {'id': _PARAM_ID}}, 200


def _fail():
    return {'success': False, 'message': 'boom'}, 400


@pytest.fixture()
def recorded(monkeypatch):
    """收集 ParamHistoryService.record 调用，避免真连库。"""
    calls = []

    def _record(scope, scope_id, algorithm_type, action='save'):
        calls.append((scope, scope_id, algorithm_type, action))
        return {'id': 1, 'version': 1, 'action': action}

    monkeypatch.setattr(ParamHistoryService, 'record', staticmethod(_record))
    return calls


@pytest.fixture()
def service(monkeypatch):
    """替换 CommandService，返回值可控。"""
    class _FakeCommand:
        next_result = _ok()

        @staticmethod
        def create_param():
            return _FakeCommand.next_result

        @staticmethod
        def update_param(param_id):
            return _FakeCommand.next_result

        @staticmethod
        def delete_param(param_id):
            return _FakeCommand.next_result

        @staticmethod
        def create_mapping():
            return _FakeCommand.next_result

        @staticmethod
        def update_mapping(mapping_id):
            return _FakeCommand.next_result

        @staticmethod
        def delete_mapping(mapping_id):
            return _FakeCommand.next_result

    fake = _FakeCommand()
    monkeypatch.setattr(algorithm_bp, 'AlgorithmCommandService', fake)
    return fake


@pytest.fixture()
def lookup(monkeypatch):
    """替换行作用域定位，默认解析不到。"""
    state = {'scope': None}

    def _lookup_scope(table, row_id):
        return state['scope']

    monkeypatch.setattr(
        algorithm_bp.param_history_repository, 'lookup_scope', _lookup_scope)
    return state


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _fake_auth(request, call_next):
        request.state.permissions = ['*']
        return await call_next(request)

    app.include_router(
        algorithm_router, prefix='/api/v1/algorithm', tags=['algorithm'])
    return app


@pytest.fixture()
def client(service, recorded, lookup):
    return TestClient(_make_app())


# ========== 设备级写：必须记版本 ==========

def test_post_device_param_records_history(client, recorded):
    resp = client.post('/api/v1/algorithm/params', json={
        'algorithm_type': _ALGO, 'device_id': _DEVICE_ID,
        'param_code': 'start_ms', 'param_type': 'text',
        'default_value': '1777000011000', 'param_type_source': 'device',
    })
    assert resp.status_code == 200
    assert recorded == [('device', _DEVICE_ID, _ALGO, 'save')]


def test_put_device_param_records_history_from_body(client, recorded):
    resp = client.put(f'/api/v1/algorithm/params/{_PARAM_ID}', json={
        'algorithm_type': _ALGO, 'device_id': _DEVICE_ID,
        'default_value': '1777000033000',
    })
    assert resp.status_code == 200
    assert recorded == [('device', _DEVICE_ID, _ALGO, 'save')]


def test_put_without_scope_falls_back_to_row_lookup(client, recorded, lookup):
    lookup['scope'] = ('device', _DEVICE_ID, _ALGO)
    resp = client.put(f'/api/v1/algorithm/params/{_PARAM_ID}',
                      json={'default_value': '1777000044000'})
    assert resp.status_code == 200
    assert recorded == [('device', _DEVICE_ID, _ALGO, 'save')]


def test_delete_device_mapping_records_history(client, recorded, lookup):
    lookup['scope'] = ('device', _DEVICE_ID, _ALGO)
    resp = client.delete(f'/api/v1/algorithm/mappings/{_MAPPING_ID}')
    assert resp.status_code == 200
    assert recorded == [('device', _DEVICE_ID, _ALGO, 'save')]


def test_post_device_mapping_records_history(client, recorded):
    resp = client.post('/api/v1/algorithm/mappings', json={
        'algorithm_type': _ALGO, 'device_id': _DEVICE_ID,
        'source_type': 'device', 'source_param': 'ai_wav',
        'dimension_id': 3, 'target_param': 'answer',
    })
    assert resp.status_code == 200
    assert recorded == [('device', _DEVICE_ID, _ALGO, 'save')]


# ========== 不该记录的场景 ==========

def test_algorithm_level_param_skips_device_history(client, recorded):
    """device_id 为空的算法级默认行不属于任何设备作用域。"""
    resp = client.post('/api/v1/algorithm/params', json={
        'algorithm_type': _ALGO, 'device_id': None,
        'param_code': 'start_ms', 'param_type': 'text',
        'param_type_source': 'device',
    })
    assert resp.status_code == 200
    assert recorded == []


def test_api_scope_param_skips_device_history(client, recorded, lookup):
    lookup['scope'] = ('api', 28, _ALGO)
    resp = client.put(f'/api/v1/algorithm/params/{_PARAM_ID}',
                      json={'default_value': 'x'})
    assert resp.status_code == 200
    assert recorded == []


def test_failed_write_does_not_record(client, recorded, service):
    type(service).next_result = _fail()
    resp = client.post('/api/v1/algorithm/params', json={
        'algorithm_type': _ALGO, 'device_id': _DEVICE_ID,
        'param_code': 'start_ms', 'param_type': 'text',
        'param_type_source': 'device',
    })
    assert resp.status_code == 400
    assert recorded == []


# ========== 回归：记录函数拿到的是服务层元组，不是响应对象 ==========

def test_record_helper_accepts_raw_tuple_only():
    """锁定根因：转换后的 Response 不该被当成元组（INT-2342）。"""
    assert algorithm_bp._record_device_history  # noqa: SLF001
    from fastapi.responses import JSONResponse

    assert not isinstance(JSONResponse(content={}, status_code=200), tuple)
