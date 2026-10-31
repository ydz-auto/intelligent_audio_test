# -*- coding: utf-8 -*-
"""INT-2241 用例 REST 路由权限回归。

背景（INT-2225 走查问题 1/7）：`api_gateway/routes/testcase_bp.py` 中
  - GET  /testcases/{id}            无 require_permission
  - POST /testcases                 无 require_permission
  - DELETE /testcases/{id}          无 require_permission
  - POST /testcases/{id}/stop_preview 无 require_permission（连字符别名有）
  - POST /testcases/batch           仅 testcase:read，而动作含删除/复制/改配置
任何已登录用户可绕过 testcase:create / testcase:delete / testcase:read 执行读写。

修复：
  1. get_one      → testcase:read
  2. create       → testcase:create
  3. delete       → testcase:delete
  4. stop_preview 两条别名统一 testcase:preview
  5. batch        → 路由依赖按 action 细分权限：delete/restore/rename_tag →
     testcase:delete，copy 系 → testcase:copy，其余 → testcase:update
     （只读权限不再放行）

测试基建对齐 tests/unit/test_int449_stop_permission.py（最小 app +
RequestAdapterMiddleware + 假认证中间件），handler/ACL 以成功桩避免触达真实 gRPC。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_gateway.application.services.auth.token_service import TokenService
from api_gateway.application.services.mcp.tools_registry import get_tool
from api_gateway.application.services.testcase.testcase_command_service import (
    TestCaseCommandService,
)
from api_gateway.application.services.testcase.testcase_query_service import (
    TestCaseQueryService,
)
from api_gateway.infrastructure.acl import TestCaseConfigAclRepositoryImpl
from api_gateway.middleware import RequestAdapterMiddleware
from api_gateway.routes.testcase_bp import router as testcase_router
from api_gateway.utils.response import success_response

PREFIX = '/api/v1/testcases'


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _fake_auth(request, call_next):
        """对齐 AuthMiddleware 语义：Bearer JWT → request.state.permissions。"""
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            try:
                payload = TokenService.verify(auth[7:])
                request.state.permissions = payload.get('permissions', [])
            except Exception:  # noqa: BLE001 — 令牌无效等价未认证
                request.state.permissions = []
        else:
            request.state.permissions = []
        return await call_next(request)

    app.include_router(testcase_router, prefix=PREFIX, tags=['testcases'])
    return app


@pytest.fixture()
def client():
    return TestClient(_make_app())


@pytest.fixture(autouse=True)
def handler_stubs(monkeypatch):
    """成功桩：门禁缺失时 handler 会被执行并返回 200 → 403 断言失败暴露缺口。

    修复后权限门禁在 handler 之前抛 403，桩仅服务阳性对照与「具备权限 → 通过」。
    """
    monkeypatch.setattr(
        TestCaseQueryService, 'get_one',
        staticmethod(lambda tc_id: success_response({'id': tc_id}, 'ok')))
    monkeypatch.setattr(
        TestCaseCommandService, 'create',
        staticmethod(lambda: success_response({'id': 'new'}, 'created')))
    monkeypatch.setattr(
        TestCaseCommandService, 'delete',
        staticmethod(lambda tc_id: success_response(None, 'deleted')))
    monkeypatch.setattr(
        TestCaseCommandService, 'stop_preview',
        staticmethod(lambda tc_id: success_response(None, 'stopped')))
    # batch 走真实服务逻辑（含按 action 的权限细分），只桩掉 ACL
    monkeypatch.setattr(
        TestCaseConfigAclRepositoryImpl, 'batch_action',
        lambda self, data: {'success': True, 'data': None, 'message': 'ok'})


def _bearer(user_id, username, permissions):
    return {'Authorization': 'Bearer ' + TokenService.create_token(
        user_id=user_id, username=username, role_id=1,
        permissions=permissions)}


READ_ONLY = ['testcase:read']
GUEST = []
ADMIN = ['*']


def _post_batch(client, perms, action):
    return client.post(f'{PREFIX}/batch',
                       json={'ids': ['tc-1'], 'action': action},
                       headers=_bearer(9, 'u', perms))


class TestDetailRequiresRead:

    def test_read_only_passes(self, client):
        resp = client.get(f'{PREFIX}/tc-1', headers=_bearer(1, 'u', READ_ONLY))
        assert resp.status_code == 200, resp.text

    def test_guest_403(self, client):
        resp = client.get(f'{PREFIX}/tc-1', headers=_bearer(2, 'guest', GUEST))
        assert resp.status_code == 403, resp.text

    def test_non_read_write_perm_403(self, client):
        """仅有写权限（无 read）不得读详情。"""
        resp = client.get(f'{PREFIX}/tc-1',
                          headers=_bearer(3, 'u', ['testcase:create']))
        assert resp.status_code == 403, resp.text


class TestCreateRequiresCreate:

    def test_creator_passes(self, client):
        resp = client.post(PREFIX, json={'name': 'x'},
                           headers=_bearer(1, 'u', ['testcase:read', 'testcase:create']))
        assert resp.status_code == 200, resp.text

    def test_read_only_403(self, client):
        resp = client.post(PREFIX, json={'name': 'x'},
                           headers=_bearer(2, 'u', READ_ONLY))
        assert resp.status_code == 403, resp.text


class TestDeleteRequiresDelete:

    def test_deleter_passes(self, client):
        resp = client.delete(f'{PREFIX}/tc-1',
                             headers=_bearer(1, 'u', ['testcase:read', 'testcase:delete']))
        assert resp.status_code == 200, resp.text

    def test_read_only_403(self, client):
        resp = client.delete(f'{PREFIX}/tc-1', headers=_bearer(2, 'u', READ_ONLY))
        assert resp.status_code == 403, resp.text

    def test_update_perm_is_not_delete(self, client):
        """testcase:update 不得用于删除（权限点不可互相顶替）。"""
        resp = client.delete(f'{PREFIX}/tc-1',
                             headers=_bearer(3, 'u', ['testcase:read', 'testcase:update']))
        assert resp.status_code == 403, resp.text


class TestStopPreviewRequiresPreview:

    @pytest.mark.parametrize('path', [f'{PREFIX}/tc-1/stop_preview',
                                      f'{PREFIX}/tc-1/stop-preview'])
    def test_read_only_403(self, client, path):
        """下划线/连字符两条别名都必须门禁（原下划线别名裸奔）。"""
        resp = client.post(path, headers=_bearer(1, 'u', READ_ONLY))
        assert resp.status_code == 403, resp.text

    @pytest.mark.parametrize('path', [f'{PREFIX}/tc-1/stop_preview',
                                      f'{PREFIX}/tc-1/stop-preview'])
    def test_previewer_passes(self, client, path):
        resp = client.post(path, headers=_bearer(2, 'u',
                                                 ['testcase:read', 'testcase:preview']))
        assert resp.status_code == 200, resp.text


class TestBatchActionPermissions:

    def test_read_only_403(self, client):
        """只读权限不再可执行批量写。"""
        resp = _post_batch(client, READ_ONLY, 'update_spl')
        assert resp.status_code == 403, resp.text

    def test_updater_can_update(self, client):
        resp = _post_batch(client, ['testcase:read', 'testcase:update'], 'update_spl')
        assert resp.status_code == 200, resp.text

    def test_updater_cannot_delete(self, client):
        """testcase:update 不能执行破坏性 delete。"""
        resp = _post_batch(client, ['testcase:read', 'testcase:update'], 'delete')
        assert resp.status_code == 403, resp.text

    def test_updater_cannot_copy(self, client):
        resp = _post_batch(client, ['testcase:read', 'testcase:update'], 'copy')
        assert resp.status_code == 403, resp.text

    @pytest.mark.parametrize('action', ['delete', 'restore', 'rename_tag'])
    def test_deleter_can_destructive(self, client, action):
        resp = _post_batch(client, ['testcase:read', 'testcase:delete'], action)
        assert resp.status_code == 200, resp.text

    @pytest.mark.parametrize('action', ['copy', 'copy_to_group', 'copy_by_group',
                                        'copy_by_tag'])
    def test_copier_can_copy(self, client, action):
        resp = _post_batch(client, ['testcase:read', 'testcase:copy'], action)
        assert resp.status_code == 200, resp.text

    def test_admin_passes(self, client):
        resp = _post_batch(client, ADMIN, 'delete')
        assert resp.status_code == 200, resp.text


class TestBatchMalformedAction:
    """action 非字符串时权限判定不得崩溃（INT-233：非法请求回 400，不 500）。"""

    @pytest.mark.parametrize('action', [{'x': 1}, ['delete'], 123, None])
    def test_admin_malformed_action_400(self, client, action):
        resp = _post_batch(client, ADMIN, action)
        assert resp.status_code == 400, resp.text
        assert '请求数据验证失败' in resp.text, resp.text

    @pytest.mark.parametrize('action', [{'x': 1}, ['delete']])
    def test_read_only_malformed_action_403(self, client, action):
        """只读用户即使传畸形 action 也只得到 403（默认要求 update），不得 500。"""
        resp = _post_batch(client, READ_ONLY, action)
        assert resp.status_code == 403, resp.text


class TestToolsRegistryConsistency:
    """与 MCP tools_registry 声明的权限点逐条一致。"""

    @pytest.mark.parametrize('tool_name,method,path,perm', [
        ('testcase_get', 'get', f'{PREFIX}/tc-1', 'testcase:read'),
        ('testcase_create', 'post', PREFIX, 'testcase:create'),
        ('testcase_delete', 'delete', f'{PREFIX}/tc-1', 'testcase:delete'),
    ])
    def test_declared_permission_suffices(self, client, tool_name, method,
                                          path, perm):
        tool = get_tool(tool_name)
        assert tool is not None
        assert perm in tool['permissions'], \
            f'{tool_name} 声明权限 {tool["permissions"]} 不含 {perm}'
        resp = getattr(client, method)(path, headers=_bearer(7, 'u', [perm]))
        assert resp.status_code != 403, \
            f'{tool_name} 声明权限 {perm} 却仍 403: {resp.text}'

    def test_declared_permission_is_required(self, client):
        """未声明权限的用户调用同一端点必须 403（声明与实际门禁一致）。"""
        for method, path in (('get', f'{PREFIX}/tc-1'),
                             ('post', PREFIX),
                             ('delete', f'{PREFIX}/tc-1')):
            resp = getattr(client, method)(path, headers=_bearer(8, 'u', GUEST))
            assert resp.status_code == 403, \
                f'{method.upper()} {path} 应 403，实际 {resp.status_code}'
