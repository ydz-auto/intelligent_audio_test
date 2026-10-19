# -*- coding: utf-8 -*-
"""INT-449 权限回归：task:execute 写门禁 —— 算法工程师只读观察视图不击穿 stop。

代码审计 P1（INT-449 打回）：`api_gateway/routes/task_bp.py` 的
`POST /api/v1/tasks/{id}/stop` 缺 `require_permission('task:execute')` 门禁，
任何已认证角色（含 algo_engineer / guest）可直接停止运行中任务，击穿
「算法工程师任务执行只读观察视图」验收口径。

修复：stop 路由补 `task:execute` 门禁（与同文件 start/retry/control 对齐）。

回归覆盖：
1. algo_engineer（持 task:read + task:read_execute_view，无 task:execute）调
   stop → 403（只读成立，写控制被拦截）
2. guest（无任何权限）调 stop → 403
3. 阳性对照：admin（通配 *）调 stop → 放行至 handler（200）——证明 403 来自
   权限门禁而非路由/其它错误；handler 以成功桩避免触达真实 gRPC
4. 同族写接口（start/retry/control/stop）对 algo_engineer 全部 403

测试基建对齐 test_int233（最小 app + RequestAdapterMiddleware + 假认证）。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_gateway.application.services.auth.token_service import TokenService
from api_gateway.application.services.task.task_lifecycle_service import (
    TaskLifecycleService,
)
from api_gateway.middleware import RequestAdapterMiddleware
from api_gateway.routes.task_bp import router as task_router
from api_gateway.utils.response import success_response


def _make_app() -> FastAPI:
    """最小网关应用：task_bp + RequestAdapterMiddleware + 假认证中间件。

    假认证中间件对齐 AuthMiddleware 语义：Bearer JWT → request.state.permissions。
    """
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _fake_auth(request, call_next):
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

    app.include_router(task_router, prefix='/api/v1/tasks', tags=['tasks'])
    return app


@pytest.fixture()
def client():
    return TestClient(_make_app())


@pytest.fixture()
def stop_stub(monkeypatch):
    """停止任务成功桩：若门禁缺失、handler 被执行，直接 200（不触达真实 gRPC）。

    修复前本桩会让未授权角色「成功停止」（200）→ 403 断言失败暴露 P1；
    修复后权限门禁在 handler 前抛 403，桩仅服务 admin 阳性对照。
    """

    def _fake_stop(task_id):  # noqa: ARG001 — 签名与 TaskLifecycleService.stop 对齐
        return success_response(None, '任务已停止')

    monkeypatch.setattr(TaskLifecycleService, 'stop', staticmethod(_fake_stop))


def _bearer(user_id, username, permissions):
    return {'Authorization': 'Bearer ' + TokenService.create_token(
        user_id=user_id, username=username, role_id=1,
        permissions=permissions)}


# INT-449 授权后的 algo_engineer：可见任务执行只读视图，但无 task:execute 写控制
ALGO_ENGINEER_PERMS = ['task:read', 'task:read_execute_view']
GUEST_PERMS = []


class TestStopRequiresTaskExecute:

    def test_algo_engineer_stop_403(self, client, stop_stub):
        """算法工程师只读可见但无写控制：调 stop → 403（本卡验收口径）。"""
        resp = client.post('/api/v1/tasks/37/stop',
                           headers=_bearer(1, 'algo_engineer', ALGO_ENGINEER_PERMS))
        assert resp.status_code == 403, resp.text

    def test_guest_stop_403(self, client, stop_stub):
        """guest 无任何权限：调 stop → 403。"""
        resp = client.post('/api/v1/tasks/37/stop',
                           headers=_bearer(2, 'guest', GUEST_PERMS))
        assert resp.status_code == 403, resp.text

    def test_admin_stop_reaches_handler(self, client, stop_stub):
        """阳性对照：admin 通配放行 → 200，证明 403 确系权限门禁而非其它错误。"""
        resp = client.post('/api/v1/tasks/37/stop',
                           headers=_bearer(3, 'admin', ['*']))
        assert resp.status_code == 200, resp.text

    def test_execute_write_routes_all_gated_for_algo_engineer(self, client,
                                                              stop_stub):
        """同族 task:execute 写接口对 algo_engineer 全部 403（含修复的 stop）。"""
        for path in ('/api/v1/tasks/37/start',
                     '/api/v1/tasks/37/retry',
                     '/api/v1/tasks/37/control',
                     '/api/v1/tasks/37/stop'):
            resp = client.post(path,
                               headers=_bearer(1, 'algo_engineer',
                                               ALGO_ENGINEER_PERMS))
            assert resp.status_code == 403, \
                f'{path} 应 403，实际 {resp.status_code}: {resp.text}'
