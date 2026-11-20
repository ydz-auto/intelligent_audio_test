# -*- coding: utf-8 -*-
"""权限实时化单测：JWT 调权后无需重新登录即生效。

覆盖：
- permission_cache.resolve_permissions：首次 RPC、TTL 内命中缓存、
  invalidate 后重拉、RPC 失败回落 JWT 快照、TTL=0 关闭实时化
- AuthMiddleware._resolve_bearer：JWT 身份使用实时权限（不是 payload 快照）
- TokenService.refresh：续期按当前权限重算，不复制旧快照
- 管理端 notice：开启实时化按 TTL 提示，关闭时回落 JWT 快照文案
"""
import json
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from api_gateway.application.services.auth.token_service import TokenService  # noqa: E402
from api_gateway.infrastructure.permission_cache import (  # noqa: E402
    invalidate_permissions,
    resolve_permissions,
)


class _FakeAuthStub:
    """模拟 auth_service stub：GetUserPermissions 返回当前权限或抛错。"""

    def __init__(self):
        self.permissions = ['audio:read']
        self.fail = False
        self.raise_error = False
        self.calls = []

    def GetUserPermissions(self, request, **kwargs):
        self.calls.append(request.user_id)
        if self.raise_error:
            raise RuntimeError('auth_service 不可达')
        if self.fail:
            return SimpleNamespace(success=False, message='用户不存在', data='')
        return SimpleNamespace(
            success=True,
            message='ok',
            data=json.dumps({'permissions': self.permissions}),
        )


@pytest.fixture()
def fake_stub(monkeypatch):
    stub = _FakeAuthStub()
    import api_gateway.infrastructure.grpc_proxies.auth_proxies as auth_proxies
    monkeypatch.setattr(auth_proxies, 'get_auth_service_stub', lambda: stub)
    return stub


@pytest.fixture(autouse=True)
def _permission_cache_isolation(monkeypatch):
    from api_gateway.config.config import Config
    monkeypatch.setattr(Config, 'AUTH_PERMISSION_CACHE_TTL_SECONDS', 10)
    monkeypatch.setattr(Config, 'AUTH_PERMISSION_RPC_TIMEOUT_SECONDS', 3)
    invalidate_permissions()
    yield
    invalidate_permissions()


class TestResolvePermissions:

    def test_first_call_uses_live_permissions(self, fake_stub):
        assert resolve_permissions(7, ['task:read']) == ['audio:read']
        assert fake_stub.calls == [7]

    def test_second_call_hits_cache(self, fake_stub):
        resolve_permissions(7, ['task:read'])
        fake_stub.permissions = ['task:read']
        assert resolve_permissions(7, ['task:read']) == ['audio:read']
        assert fake_stub.calls == [7]

    def test_invalidate_forces_refetch(self, fake_stub):
        resolve_permissions(7, ['task:read'])
        fake_stub.permissions = ['task:read']
        invalidate_permissions(7)
        assert resolve_permissions(7, ['audio:read']) == ['task:read']
        assert fake_stub.calls == [7, 7]

    def test_rpc_raise_falls_back_to_snapshot(self, fake_stub):
        fake_stub.raise_error = True
        assert resolve_permissions(7, ['task:read']) == ['task:read']

    def test_rpc_failure_falls_back_and_is_not_cached(self, fake_stub):
        fake_stub.fail = True
        assert resolve_permissions(7, ['task:read']) == ['task:read']
        fake_stub.fail = False
        fake_stub.permissions = ['audio:read']
        assert resolve_permissions(7, ['task:read']) == ['audio:read']
        assert fake_stub.calls == [7, 7]

    def test_empty_permissions_are_cached(self, fake_stub):
        fake_stub.permissions = []
        assert resolve_permissions(7, ['task:read']) == []
        assert resolve_permissions(7, ['task:read']) == []
        assert fake_stub.calls == [7]

    def test_ttl_zero_disables_realtime(self, fake_stub, monkeypatch):
        from api_gateway.config.config import Config
        monkeypatch.setattr(Config, 'AUTH_PERMISSION_CACHE_TTL_SECONDS', 0)
        assert resolve_permissions(7, ['task:read']) == ['task:read']
        assert fake_stub.calls == []

    def test_anonymous_skips_rpc(self, fake_stub):
        assert resolve_permissions(0, []) == []
        assert fake_stub.calls == []


class TestBearerIdentityUsesLivePermissions:

    def test_jwt_identity_permissions_are_live(self, fake_stub):
        from api_gateway.middleware import AuthMiddleware
        token = TokenService.create_token(7, 'u1', 2, ['task:read'])
        identity = AuthMiddleware._resolve_bearer(None, token)
        assert identity is not None
        assert identity[0] == 7
        assert identity[1] == 'u1'
        assert identity[3] == ['audio:read']

    def test_token_refresh_recomputes_permissions(self, fake_stub):
        token = TokenService.create_token(7, 'u1', 2, ['task:read'])
        refreshed = TokenService.refresh(token)
        payload = TokenService.verify(refreshed)
        assert payload['permissions'] == ['audio:read']
        assert payload['user_id'] == 7


class TestPermissionNotice:

    def test_notice_states_auto_effect_when_realtime_enabled(self):
        from api_gateway.application.services.auth.management_common import (
            with_notice,
        )
        payload, _ = with_notice(({'success': True}, 200))
        assert '10 秒内自动生效' in payload['notice']
        assert '无需重新登录' in payload['notice']

    def test_notice_falls_back_when_realtime_disabled(self, monkeypatch):
        from api_gateway.application.services.auth.management_common import (
            PERMISSION_CHANGE_NOTICE,
            with_notice,
        )
        from api_gateway.config.config import Config
        monkeypatch.setattr(Config, 'AUTH_PERMISSION_CACHE_TTL_SECONDS', 0)
        payload, _ = with_notice(({'success': True}, 200))
        assert payload['notice'] == PERMISSION_CHANGE_NOTICE
