# -*- coding: utf-8 -*-
"""INT-406 登录/登出审计事件 + AUTH_MODE=off 显式守卫回归测试。

验收标准覆盖：
1. AUTH_LOGIN / AUTH_LOGOUT 入审计枚举（shared 层 enum 化，无魔法字符串）；
   登录成功、登出各产生一条审计事件（含用户与时间，走现有审计通道落 logs）
2. AUTH_MODE=off 启动显式横幅日志；API 响应携带模式提示头（枚举/配置化，
   非硬编码）
3. 事件通道约束核查：不新增第六通道（审计仍复用 AuditLogCategory.AUTH）
"""
import json
import os
import tempfile
import time

import pytest

# 共享配置在导入期校验必填环境变量；本模块不触真库，仅满足导入校验
os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int406_') + '/audit.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.common_enums import (  # noqa: E402
    AUDIT_LOG_CATEGORIES,
    AuditEvent,
    AuditLogCategory,
)
from shared.constants.auth_mode import (  # noqa: E402
    AUTH_MODE_HEADER,
    AUTH_MODE_OFF_BANNER,
    AuthMode,
    log_auth_mode_banner,
)


def _wait_for(condition, timeout=3.0, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return condition()


@pytest.fixture()
def audit_env(monkeypatch, tmp_path):
    """独立 DatabaseLogHandler：worker 消费后由 fake batch_create_logs 承接。

    对齐 tests/unit/test_log_handler_audit_emit.py::audit_env 模式——
    验证 api_gateway 侧 write_auth_audit 走现有审计通道（category='auth'）
    落入 DB 队列，且含用户与时间打点。
    """
    import shared.clients.grpc_clients as grpc_clients_mod
    import shared.utils.log_handler._state as lh_state
    from shared.utils.log_handler import DatabaseLogHandler

    prev = lh_state._global_db_handler
    if prev is not None:
        prev.queue.put(None)
        prev_worker = getattr(prev, 'worker_thread', None)
        if prev_worker is not None:
            prev_worker.join(timeout=2.0)

    captured = []

    def _fake_batch_create(logs_payload):
        captured.extend(logs_payload)
        return [9000 + i for i in range(len(logs_payload))]

    monkeypatch.setattr(grpc_clients_mod, 'batch_create_logs', _fake_batch_create)
    monkeypatch.setattr(grpc_clients_mod, 'get_log_count', lambda: {'total': 0})
    monkeypatch.setattr(
        grpc_clients_mod, 'archive_logs',
        lambda days=30, dry_run=False: {'groups': {}, 'remaining_count': 0})
    import shared.clients.oss_client as oss_client_mod
    monkeypatch.setattr(oss_client_mod.oss, 'is_available', lambda: False)
    monkeypatch.chdir(tmp_path)
    handler = DatabaseLogHandler()
    handler._batch_size = 1
    handler.set_console_log(False)
    monkeypatch.setattr(lh_state, '_global_db_handler', handler)
    yield handler, captured
    handler.queue.put(None)


class TestAuditEventEnum:
    """验收标准 1a：AUTH_LOGIN / AUTH_LOGOUT 入审计枚举，无魔法字符串。"""

    def test_login_logout_in_audit_event_enum(self):
        assert AuditEvent.AUTH_LOGIN.value == 'AUTH_LOGIN'
        assert AuditEvent.AUTH_LOGOUT.value == 'AUTH_LOGOUT'
        values = {e.value for e in AuditEvent}
        assert 'AUTH_LOGIN' in values
        assert 'AUTH_LOGOUT' in values

    def test_no_sixth_event_channel(self):
        """验收标准 4：审计通道仍复用 AuditLogCategory.AUTH，不新增类别/通道。"""
        assert AUDIT_LOG_CATEGORIES == frozenset({'auth', 'benchmark', 'device'})
        assert AuditLogCategory.AUTH.value == 'auth'


class TestLoginLogoutAudit:
    """验收标准 1b：登录成功、登出各产生一条审计事件（含用户与时间）。"""

    def test_issue_token_emits_auth_login(self, monkeypatch):
        from api_gateway.application.services.auth import auth_audit as auth_audit_mod
        from api_gateway.application.services.auth.auth_service import AuthService
        from api_gateway.domain.entities.auth_entities import AuthUser
        from api_gateway.domain.value_objects.auth_value_objects import UserInfo

        captured = []
        monkeypatch.setattr(
            auth_audit_mod, 'write_auth_audit',
            lambda event, module, content: captured.append((event, module, content)))
        monkeypatch.setattr(
            AuthService, '_find_or_create_user',
            staticmethod(lambda user_info, provider='': AuthUser(
                id=42, username='alice', role_id=1, permissions=['*'])))

        result = AuthService._issue_token(UserInfo(username='alice'), provider='')
        assert 'access_token' in result
        assert len(captured) == 1, '登录成功应恰好产生一条 AUTH_LOGIN 审计'
        event, module, content = captured[0]
        assert event is AuditEvent.AUTH_LOGIN
        assert module == 'auth_login'
        assert content['operator_id'] == 42
        assert content['operator'] == 'alice'
        assert content['target_id'] == 42
        assert content['provider'] == 'password'

    def test_logout_emits_auth_logout(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api_gateway.application.services.auth import auth_audit as auth_audit_mod
        from api_gateway.middleware import AuthMiddleware, RequestAdapterMiddleware
        from api_gateway.routes.auth_bp import router as auth_router

        captured = []
        monkeypatch.setattr(
            auth_audit_mod, 'write_auth_audit',
            lambda event, module, content: captured.append((event, module, content)))

        app = FastAPI()
        app.add_middleware(RequestAdapterMiddleware)
        app.add_middleware(AuthMiddleware, auth_mode='off')
        app.include_router(auth_router, prefix='/api/v1/auth')

        with TestClient(app) as client:
            resp = client.post('/api/v1/auth/logout')
            assert resp.status_code == 200, resp.text
        assert len(captured) == 1, '登出应恰好产生一条 AUTH_LOGOUT 审计'
        event, module, content = captured[0]
        assert event is AuditEvent.AUTH_LOGOUT
        assert module == 'auth_logout'
        # AUTH_MODE=off：AuthMiddleware 注入 dev_user（user_id=0 归一未认证）
        assert content['operator'] == 'dev_user'
        assert content['operator_id'] == 0

    def test_oauth_callback_login_also_emits_auth_login(self, monkeypatch):
        """OAuth 登录（huawei）同样落 AUTH_LOGIN，provider 标识登录通道。"""
        from api_gateway.application.services.auth import auth_audit as auth_audit_mod
        from api_gateway.application.services.auth.auth_service import AuthService
        from api_gateway.domain.entities.auth_entities import AuthUser
        from api_gateway.domain.value_objects.auth_value_objects import UserInfo

        captured = []
        monkeypatch.setattr(
            auth_audit_mod, 'write_auth_audit',
            lambda event, module, content: captured.append((event, module, content)))
        monkeypatch.setattr(
            AuthService, '_find_or_create_user',
            staticmethod(lambda user_info, provider='': AuthUser(
                id=9, username='zhangsan', role_id=2, permissions=[])))

        AuthService._issue_token(UserInfo(username='zhangsan'), provider='huawei')
        assert len(captured) == 1
        _, _, content = captured[0]
        assert content['provider'] == 'huawei'


class TestAuthModeHeader:
    """验收标准 2：API 响应携带模式提示头（枚举/配置化，非硬编码）。"""

    def test_header_reports_off(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api_gateway.middleware import AuthModeHeaderMiddleware

        app = FastAPI()
        app.add_middleware(AuthModeHeaderMiddleware, auth_mode='off')

        @app.get('/ping')
        def ping():
            return {'ok': True}

        with TestClient(app) as client:
            resp = client.get('/ping')
        assert resp.headers.get(AUTH_MODE_HEADER) == 'off'

    def test_header_reports_dev(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api_gateway.middleware import AuthModeHeaderMiddleware

        app = FastAPI()
        app.add_middleware(AuthModeHeaderMiddleware, auth_mode='dev')

        @app.get('/ping')
        def ping():
            return {'ok': True}

        with TestClient(app) as client:
            resp = client.get('/ping')
        assert resp.headers.get(AUTH_MODE_HEADER) == 'dev'


class TestOffModeBanner:
    """验收标准 2：AUTH_MODE=off 启动显式横幅日志（非 off 静默）。"""

    def test_off_mode_logs_explicit_banner(self, caplog):
        import logging

        logger = logging.getLogger('test_auth_mode_banner_off')
        with caplog.at_level(logging.WARNING, logger='test_auth_mode_banner_off'):
            log_auth_mode_banner(logger, AuthMode.OFF)
        assert any(AUTH_MODE_OFF_BANNER in r.message for r in caplog.records)

    def test_dev_mode_no_banner(self, caplog):
        import logging

        logger = logging.getLogger('test_auth_mode_banner_dev')
        with caplog.at_level(logging.WARNING, logger='test_auth_mode_banner_dev'):
            log_auth_mode_banner(logger, 'dev')
        assert not any(
            r.levelno == logging.WARNING and r.name == 'test_auth_mode_banner_dev'
            for r in caplog.records), '非 off 模式不得打安全横幅'


class TestAuditChannel:
    """验收标准 1c + 4：api_gateway 审计走现有通道（category='auth'）落 DB 队列。"""

    def test_login_audit_lands_in_db_queue(self, audit_env):
        from api_gateway.application.services.auth.auth_audit import write_auth_audit

        _, captured = audit_env
        write_auth_audit(AuditEvent.AUTH_LOGIN, 'auth_login', {
            'operator_id': 42, 'operator': 'alice', 'provider': 'password',
        })
        assert _wait_for(lambda: len(captured) >= 1), 'AUTH_LOGIN 审计未进入 DB 队列'
        entry = captured[0]
        assert entry['category'] == 'auth'
        assert entry['source'] == 'api_gateway'
        assert entry['time'], '审计条目应含时间打点'
        payload = json.loads(entry['content'])
        assert payload['event'] == 'AUTH_LOGIN'
        assert payload['operator_id'] == 42
        assert payload['operator'] == 'alice'

    def test_logout_audit_lands_in_db_queue(self, audit_env):
        from api_gateway.application.services.auth.auth_audit import write_auth_audit

        _, captured = audit_env
        write_auth_audit(AuditEvent.AUTH_LOGOUT, 'auth_logout', {
            'operator_id': 7, 'operator': 'bob',
        })
        assert _wait_for(lambda: len(captured) >= 1), 'AUTH_LOGOUT 审计未进入 DB 队列'
        entry = captured[0]
        assert entry['category'] == 'auth'
        payload = json.loads(entry['content'])
        assert payload['event'] == 'AUTH_LOGOUT'
        assert payload['operator_id'] == 7
