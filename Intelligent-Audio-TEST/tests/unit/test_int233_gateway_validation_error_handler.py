# -*- coding: utf-8 -*-
"""INT-233 专项：网关统一 ValidationError → 422 结构化错误。

缺陷（INT-138 全量回归·实机半场）：
- GET /api/v1/testcases?dimension_id=abc → 500（INT-193 修复新增参数
  引入的触发点；修复前该参数被 extra="ignore" 忽略 → 200）
- GET /api/v1/{tasks,groups,audios}?page=abc → 500（既有模式，早于
  INT-193 存在：service 层 model_validate(raw query) 的 ValidationError
  在网关无统一出口）
- GET /api/v1/published-tasks?page=abc → 500（同族：手动 int() 解析
  抛 ValueError，同样无出口）

修复：
- api_gateway.utils.error_handlers.register_error_handlers 在 create_app
  注册统一异常处理器：任意路由内未捕获的 pydantic ValidationError
  → 422 {"success": false, "code": INVALID_PARAMS(100)}
- published_task get_all 手动 int() 解析补 try/except → 422（口径对齐）

覆盖：
1. 真实路由端到端：INT-193 触发点 testcases?dimension_id=abc 与四个点名
   端点 page=abc → 422 结构化错误（不再 500），校验失败不触达 ACL/gRPC
2. 合法路径回归（issue 期望口径）：dimension_id=121 → 200 且过滤值透传
   ACL；dimension_id=999999（合法但不存在）→ 200 空列表
3. published-tasks：page=abc → 422；缺省/钳制行为保持（page<1 → 1、
   perPage 上限 100）

测试基建对齐 test_int165（最小 app + RequestAdapterMiddleware + 假 auth）。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_gateway.application.services.audio import audio_query_service
from api_gateway.application.services.published_task import published_task_service
from api_gateway.application.services.task import task_query_service
from api_gateway.application.services.testcase import testcase_query_service
from api_gateway.infrastructure import request_adapter
from api_gateway.middleware import RequestAdapterMiddleware
from api_gateway.routes.audio_bp import router as audio_router
from api_gateway.routes.group_bp import router as group_router
from api_gateway.routes.published_task_bp import router as published_task_router
from api_gateway.routes.task_bp import router as task_router
from api_gateway.routes.testcase_bp import router as testcase_router
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.utils.error_handlers import register_error_handlers


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _fake_auth(request, call_next):
        request.state.permissions = ['*']
        return await call_next(request)

    # 与 create_app 相同的统一异常处理器注册
    register_error_handlers(app)

    app.include_router(testcase_router, prefix='/api/v1/testcases', tags=['testcases'])
    app.include_router(task_router, prefix='/api/v1/tasks', tags=['tasks'])
    app.include_router(group_router, prefix='/api/v1/groups', tags=['groups'])
    app.include_router(audio_router, prefix='/api/v1/audios', tags=['audios'])
    app.include_router(
        published_task_router, prefix='/api/v1/published-tasks',
        tags=['published-tasks'])
    return app


@pytest.fixture()
def client():
    return TestClient(_make_app())


class _RecordingAcl:
    """记录调用并返回固定结果的 ACL 桩（用于断言校验失败不触达下游）。"""

    def __init__(self, result=None):
        self.calls = []
        self._result = result or {'success': True, 'data': {}}

    def list_testcases(self, **kwargs):
        self.calls.append(kwargs)
        return self._result

    def list_tasks(self, **kwargs):
        self.calls.append(kwargs)
        return self._result

    def get_all(self, **kwargs):
        self.calls.append(kwargs)
        return self._result


@pytest.fixture()
def acl_stubs(monkeypatch):
    stubs = {
        'testcase': _RecordingAcl(),
        'task': _RecordingAcl(),
        'audio': _RecordingAcl(),
    }
    monkeypatch.setattr(testcase_query_service, '_testcase_acl', stubs['testcase'])
    monkeypatch.setattr(task_query_service, '_task_acl', stubs['task'])
    monkeypatch.setattr(audio_query_service, '_audio_acl', stubs['audio'])
    return stubs


class TestUnifiedValidationErrorHandler:
    """真实路由端到端：非法类型查询参数 → 422 结构化错误（不再 500）。"""

    def test_testcases_dimension_id_abc_returns_422(self, client, acl_stubs):
        """INT-193 触发点复验：dimension_id=abc 不再 500（修复前 → 200 忽略）。"""
        resp = client.get('/api/v1/testcases?dimension_id=abc')
        assert resp.status_code == 422
        body = resp.json()
        assert body['success'] is False
        assert body['code'] == int(ErrorCode.INVALID_PARAMS)
        assert 'dimension_id' in body['message']
        assert acl_stubs['testcase'].calls == []  # 校验失败不得触达 ACL/gRPC

    def test_named_endpoints_page_abc_return_422(self, client, acl_stubs):
        """issue 点名的四个端点 page=abc 全部 422（回归前全部 500）。"""
        for url in ('/api/v1/testcases?page=abc',
                    '/api/v1/tasks?page=abc',
                    '/api/v1/groups?page=abc',
                    '/api/v1/audios?page=abc'):
            resp = client.get(url)
            assert resp.status_code == 422, url
            body = resp.json()
            assert body['success'] is False, url
            assert body['code'] == int(ErrorCode.INVALID_PARAMS), url
            assert 'page' in body['message'], url
        assert acl_stubs['testcase'].calls == []
        assert acl_stubs['task'].calls == []
        assert acl_stubs['audio'].calls == []

    def test_non_int_bool_param_returns_422(self, client):
        """非数值型参数（bool）的非法输入同口径（tasks favorite=abc）。"""
        resp = client.get('/api/v1/tasks?favorite=abc')
        assert resp.status_code == 422
        assert resp.json()['code'] == int(ErrorCode.INVALID_PARAMS)


class TestLegalPathRegression:
    """合法路径回归：过滤生效 / 合法但不存在 → 200 空结果。"""

    def test_dimension_id_exists_filters_and_passes_int_to_acl(
            self, client, monkeypatch):
        stub = _RecordingAcl({'success': True, 'data': {
            'items': [{'id': 'c1', 'name': '维度用例', 'type': 'api'}],
            'total': 1, 'page': 1, 'per_page': 10, 'pages': 1,
        }})
        monkeypatch.setattr(testcase_query_service, '_testcase_acl', stub)

        resp = client.get('/api/v1/testcases?dimension_id=121')
        assert resp.status_code == 200
        body = resp.json()
        assert body['success'] is True
        assert body['data']['total'] == 1
        assert body['data']['items'][0]['id'] == 'c1'
        assert stub.calls and stub.calls[0]['dimension_id'] == 121

    def test_dimension_id_absent_returns_200_empty(self, client, monkeypatch):
        """合法但不存在（999999）→ 200 空列表，而非 4xx。"""
        stub = _RecordingAcl({'success': True, 'data': {
            'items': [], 'total': 0, 'page': 1, 'per_page': 10, 'pages': 0,
        }})
        monkeypatch.setattr(testcase_query_service, '_testcase_acl', stub)

        resp = client.get('/api/v1/testcases?dimension_id=999999')
        assert resp.status_code == 200
        body = resp.json()
        assert body['success'] is True
        assert body['data']['items'] == []
        assert body['data']['total'] == 0


class TestTaskListConstructionFailure500:
    """INT-755：/tasks 列表嵌套模型校验失败 → 结构化 500（不再裸 500 无日志）。

    常驻后端 /tasks 恒 500 的根因为响应构造未捕获异常（嵌套模型字段
    None 触发 pydantic ValidationError 直接冒出 FastAPI）。修复后网关
    在构造处捕获并打全栈日志，返回可读 500，本测试直测真实路由端到端。
    """

    def test_list_bad_nested_device_returns_500(self, client, monkeypatch):
        class _BadAcl:
            def list_tasks(self, **kwargs):
                return {'success': True, 'data': {
                    'items': [{
                        'id': 1, 'name': '坏任务', 'status': 'running',
                        'devices': [{'id': None, 'name': '坏设备'}],
                        'reports': {}, 'apis': [], 'source_tasks': [], 'labs': [],
                    }],
                    'total': 1, 'page': 1, 'per_page': 10, 'pages': 1,
                }}
        monkeypatch.setattr(task_query_service, '_task_acl', _BadAcl())

        resp = client.get('/api/v1/tasks')
        assert resp.status_code == 500
        body = resp.json()
        assert body['success'] is False
        assert '任务列表' in body['message']

    def test_list_valid_items_returns_200(self, client, monkeypatch):
        """合法嵌套数据不回归：列表正常 200。"""
        class _OkAcl:
            def list_tasks(self, **kwargs):
                return {'success': True, 'data': {
                    'items': [{
                        'id': 1, 'name': '好任务', 'status': 'running',
                        'devices': [], 'reports': {}, 'apis': [],
                        'source_tasks': [], 'labs': [],
                    }],
                    'total': 1, 'page': 1, 'per_page': 10, 'pages': 1,
                }}
        monkeypatch.setattr(task_query_service, '_task_acl', _OkAcl())

        resp = client.get('/api/v1/tasks')
        assert resp.status_code == 200
        assert resp.json()['data']['total'] == 1


class TestPublishedTaskPagination:
    """published-tasks 手动 int() 解析同族 500 修复（INT-233）。"""

    @staticmethod
    def _acl(result=None):
        class _PtAcl:
            def __init__(self):
                self.calls = []
                self._result = result or {'success': True, 'data': {
                    'items': [], 'total': 0}}

            def get_list(self, **kwargs):
                self.calls.append(kwargs)
                return self._result
        return _PtAcl()

    def test_page_abc_returns_422(self, client, monkeypatch):
        acl = self._acl()
        monkeypatch.setattr(published_task_service, '_pt_acl', acl)
        resp = client.get('/api/v1/published-tasks?page=abc')
        assert resp.status_code == 422
        body = resp.json()
        assert body['success'] is False
        assert body['code'] == int(ErrorCode.INVALID_PARAMS)
        assert acl.calls == []

    def test_defaults_and_clamping_preserved(self, client, monkeypatch):
        """修复不回归既有清洗行为：缺省 1/10、page<1 抬到 1、perPage 上限 100。"""
        acl = self._acl()
        monkeypatch.setattr(published_task_service, '_pt_acl', acl)

        assert client.get('/api/v1/published-tasks').status_code == 200
        assert acl.calls[0]['page'] == 1
        assert acl.calls[0]['per_page'] == 10

        client.get('/api/v1/published-tasks?page=0&perPage=150')
        assert acl.calls[1]['page'] == 1
        assert acl.calls[1]['per_page'] == 100

        client.get('/api/v1/published-tasks?page=2&per_page=5')
        assert acl.calls[2]['page'] == 2
        assert acl.calls[2]['per_page'] == 5
