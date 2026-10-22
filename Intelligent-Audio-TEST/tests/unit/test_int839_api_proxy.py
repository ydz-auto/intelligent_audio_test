# -*- coding: utf-8 -*-
"""INT-839 #1 api_test_service 网络代理单测（proxy_type / proxy_url 全链路）

覆盖（验收标准 7）：
- proxy_utils：URL 拼接 / 分解 / websocket-client 参数映射 / socks 类型可用性
- CRUD：create/update 透传 + 非法组合后端校验
- 健康检查：http/https 走 requests.proxies、ws/wss 走 websocket-client 代理参数
- api_client：_call_http proxies 注入、_call_websocket ws 代理参数
- realtime_ws_client：connect() 同套 websocket-client 代理参数
- secret_mask：proxy_url 内 user:pass 段脱敏（自由文本 + 结构化 payload）
- 迁移脚本：幂等可重跑（列已存在 SKIP，缺列 ADD）
"""
import os
import sys

# api_crud_service 导入链拉起 shared BaseConfig，补齐必填环境变量（不触库/不触网）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

from types import SimpleNamespace
from unittest import mock

import pytest

from api_test_service.application import api_crud_service as api_crud_module
from api_test_service.application.api_crud_service import APICrudService
from api_test_service.infrastructure.adapters.transport import APIClient
from api_test_service.infrastructure.adapters.proxy_utils import (
    PROXY_TYPES,
    build_proxy_url,
    split_proxy_url,
    validate_proxy,
    websocket_proxy_kwargs,
)
from api_test_service.infrastructure.adapters.transport import RealtimeWSClient
from shared.utils.secret_mask import mask_mapping, mask_text


# ═══════════════════ proxy_utils ═══════════════════

class TestProxyUtils:

    def test_build_proxy_url(self):
        assert build_proxy_url('http', 'user:pass@host:8080') == 'http://user:pass@host:8080'
        assert build_proxy_url('socks5', 'user:pass@host:1080') == 'socks5://user:pass@host:1080'
        assert build_proxy_url(None, 'user:pass@host:8080') is None
        assert build_proxy_url('http', '') is None
        assert build_proxy_url(None, None) is None

    def test_build_proxy_url_strips_scheme_prefix(self):
        """审计 P2 修复：proxy_url 误带 scheme 前缀时不拼出双重 scheme"""
        assert build_proxy_url('http', 'http://user:pass@host:8080') == 'http://user:pass@host:8080'
        assert build_proxy_url('socks5', 'socks5://user:pass@host:1080') == 'socks5://user:pass@host:1080'

    def test_split_proxy_url_full(self):
        host, port, user, password = split_proxy_url('user:pass@proxy.local:8080')
        assert host == 'proxy.local'
        assert port == 8080
        assert user == 'user'
        assert password == 'pass'

    def test_split_proxy_url_no_auth(self):
        host, port, user, password = split_proxy_url('proxy.local:8080')
        assert host == 'proxy.local'
        assert port == 8080
        assert user is None
        assert password is None

    def test_split_proxy_url_no_port(self):
        host, port, user, password = split_proxy_url('user:pass@proxy.local')
        assert host == 'proxy.local'
        assert port is None
        assert user == 'user'
        assert password == 'pass'

    def test_split_proxy_url_urlencoded_password(self):
        host, port, user, password = split_proxy_url('user:p%40ss@proxy.local:8080')
        assert user == 'user'
        assert password == 'p@ss'

    def test_split_proxy_url_strips_scheme(self):
        host, port, user, password = split_proxy_url('http://user:pass@proxy.local:8080')
        assert host == 'proxy.local'
        assert user == 'user'

    def test_split_proxy_url_invalid_port_raises(self):
        with pytest.raises(ValueError):
            split_proxy_url('user:pass@proxy.local:notaport')

    def test_websocket_proxy_kwargs_http(self):
        kwargs = websocket_proxy_kwargs('http', 'user:pass@proxy.local:8080')
        assert kwargs['http_proxy_host'] == 'proxy.local'
        assert kwargs['http_proxy_port'] == 8080
        assert kwargs['http_proxy_auth'] == ('user', 'pass')
        assert kwargs['proxy_type'] == 'http'

    def test_websocket_proxy_kwargs_https_maps_to_http_connect(self):
        """https 代理端点默认走 http CONNECT 隧道语义（INT-839 契约）。"""
        kwargs = websocket_proxy_kwargs('https', 'user:pass@proxy.local:443')
        assert kwargs['proxy_type'] == 'http'

    def test_websocket_proxy_kwargs_socks_types(self):
        kwargs = websocket_proxy_kwargs('socks5', 'user:pass@proxy.local:1080')
        assert kwargs['proxy_type'] == 'socks5'
        kwargs = websocket_proxy_kwargs('socks5h', 'user:pass@proxy.local:1080')
        assert kwargs['proxy_type'] == 'socks5h'

    def test_websocket_proxy_kwargs_default_port(self):
        kwargs = websocket_proxy_kwargs('socks5', 'user:pass@proxy.local')
        assert kwargs['http_proxy_port'] == 1080
        kwargs = websocket_proxy_kwargs('http', 'user:pass@proxy.local')
        assert kwargs['http_proxy_port'] == 80

    def test_websocket_proxy_kwargs_no_proxy_empty(self):
        assert websocket_proxy_kwargs(None, None) == {}
        assert websocket_proxy_kwargs('', '') == {}

    def test_validate_proxy_none_ok(self):
        assert validate_proxy(None, None) is None
        assert validate_proxy('', '') is None

    def test_validate_proxy_empty_type_requires_empty_url(self):
        err = validate_proxy('', 'user:pass@host:8080')
        assert err and 'proxy_url' in err

    def test_validate_proxy_type_requires_url(self):
        err = validate_proxy('http', '')
        assert err and 'proxy_url' in err

    def test_validate_proxy_type_must_be_supported(self):
        err = validate_proxy('socks4', 'user:pass@host:1080')
        assert err and 'socks4' in err
        for t in ('http', 'https', 'socks5', 'socks5h'):
            assert validate_proxy(t, 'user:pass@host:8080') is None

    def test_validate_proxy_requires_user_pass_auth(self):
        err = validate_proxy('http', 'host:8080')
        assert err and 'user:pass@' in err
        err = validate_proxy('http', 'user@host:8080')
        assert err and 'user:pass@' in err
        err = validate_proxy('http', ':pass@host:8080')
        assert err and 'user:pass@' in err

    def test_validate_proxy_invalid_port(self):
        err = validate_proxy('http', 'user:pass@host:notaport')
        assert err and '端口' in err

    def test_validate_proxy_rejects_scheme_prefix(self):
        """审计 P2 修复：契约规定 proxy_url 不含 scheme，带 scheme 前缀拒绝入库"""
        for scheme in ('http', 'https', 'socks5'):
            err = validate_proxy('http', f'{scheme}://user:pass@host:8080')
            assert err, f'{scheme}:// 前缀应被拒绝'
            assert 'scheme' in err


# ═══════════════════ CRUD ═══════════════════

class _FakeEventBus:
    def publish(self, channel, event_type, payload):
        pass


def _install_repo(monkeypatch, repo):
    monkeypatch.setattr(api_crud_module, 'EventBus', _FakeEventBus)
    monkeypatch.setattr(api_crud_module, 'api_test_repository', repo)


class _CreateRepo:
    def __init__(self):
        self.captured = {}

    def create_api(self, data):
        self.captured.update(data)
        return SimpleNamespace(id=21)


class _ProxyUpdateRepo:
    def __init__(self, current_proxy_type=None, current_proxy_url=None):
        self.captured = {}
        self.current_proxy_type = current_proxy_type
        self.current_proxy_url = current_proxy_url

    def _api(self):
        return SimpleNamespace(
            id=9, name='API-1', url='http://example.com', status='online',
            output_types=[], device_type='http_api', api_endpoints=[],
            proxy_type=self.current_proxy_type, proxy_url=self.current_proxy_url,
        )

    def get_api(self, api_id):
        return self._api()

    def update_api(self, api_id, fields):
        self.captured.update(fields)
        return self._api()


class TestCrudProxy:

    def test_create_saves_proxy_fields(self, monkeypatch):
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.create({
            'name': 'API-P', 'api_url': 'http://example.com', 'meta': {},
            'proxy_type': 'http', 'proxy_url': 'user:pass@proxy.local:8080',
        })
        assert res['code'] == 201
        assert repo.captured['proxy_type'] == 'http'
        assert repo.captured['proxy_url'] == 'user:pass@proxy.local:8080'

    def test_create_normalizes_blank_proxy_to_none(self, monkeypatch):
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.create({
            'name': 'API-P', 'api_url': 'http://example.com', 'meta': {},
            'proxy_type': '', 'proxy_url': '   ',
        })
        assert res['code'] == 201
        assert repo.captured['proxy_type'] is None
        assert repo.captured['proxy_url'] is None

    def test_create_rejects_proxy_without_auth(self, monkeypatch):
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.create({
            'name': 'API-P', 'api_url': 'http://example.com', 'meta': {},
            'proxy_type': 'http', 'proxy_url': 'proxy.local:8080',
        })
        assert res['code'] == 400
        assert 'user:pass@' in res['message']
        assert not repo.captured

    def test_create_rejects_empty_type_with_url(self, monkeypatch):
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.create({
            'name': 'API-P', 'api_url': 'http://example.com', 'meta': {},
            'proxy_type': '', 'proxy_url': 'user:pass@proxy.local:8080',
        })
        assert res['code'] == 400
        assert 'proxy_url' in res['message']
        assert not repo.captured

    def test_create_rejects_invalid_proxy_type(self, monkeypatch):
        repo = _CreateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.create({
            'name': 'API-P', 'api_url': 'http://example.com', 'meta': {},
            'proxy_type': 'socks4', 'proxy_url': 'user:pass@proxy.local:1080',
        })
        assert res['code'] == 400
        assert 'socks4' in res['message']

    def test_update_sets_proxy_fields(self, monkeypatch):
        repo = _ProxyUpdateRepo()
        _install_repo(monkeypatch, repo)
        res = APICrudService.update(9, {
            'proxy_type': 'socks5', 'proxy_url': 'user:pass@proxy.local:1080',
        })
        assert res['code'] == 200
        assert repo.captured['proxy_type'] == 'socks5'
        assert repo.captured['proxy_url'] == 'user:pass@proxy.local:1080'

    def test_update_clears_proxy_with_none(self, monkeypatch):
        repo = _ProxyUpdateRepo(current_proxy_type='http',
                                current_proxy_url='user:pass@proxy.local:8080')
        _install_repo(monkeypatch, repo)
        res = APICrudService.update(9, {'proxy_type': None, 'proxy_url': None})
        assert res['code'] == 200
        assert repo.captured['proxy_type'] is None
        assert repo.captured['proxy_url'] is None

    def test_update_url_without_type_rejected(self, monkeypatch):
        repo = _ProxyUpdateRepo(current_proxy_type=None, current_proxy_url=None)
        _install_repo(monkeypatch, repo)
        res = APICrudService.update(9, {'proxy_url': 'user:pass@proxy.local:8080'})
        assert res['code'] == 400
        assert 'proxy_url' in res['message']
        assert 'proxy_type' not in repo.captured

    def test_update_type_only_keeps_existing_url_ok(self, monkeypatch):
        repo = _ProxyUpdateRepo(current_proxy_type='http',
                                current_proxy_url='user:pass@proxy.local:8080')
        _install_repo(monkeypatch, repo)
        res = APICrudService.update(9, {'proxy_type': 'socks5'})
        assert res['code'] == 200
        assert repo.captured['proxy_type'] == 'socks5'

    def test_api_to_dict_returns_proxy_fields(self):
        api = SimpleNamespace(
            id=1, name='API', api_url='http://example.com', status='online', meta={},
            api_endpoints=[], output_types=[], device_type='http_api',
            proxy_type='socks5', proxy_url='user:pass@host:1080',
        )
        d = APICrudService._api_to_dict(api)
        assert d['proxy_type'] == 'socks5'
        assert d['proxy_url'] == 'user:pass@host:1080'


# ═══════════════════ 健康检查双分支 ═══════════════════

class _HealthRepo:
    """test_connection 用：聚合根形态（proxy 字段生效）。"""

    def __init__(self, api_url=None, endpoints=None, proxy_type=None, proxy_url=None):
        self.api_url = api_url or 'http://api.example.com'
        self.endpoints = endpoints or []
        self.proxy_type = proxy_type
        self.proxy_url = proxy_url

    def get_api(self, api_id):
        return SimpleNamespace(
            id=7, name='API-H', url=self.api_url, status='online',
            output_types=[], device_type='http_api',
            api_endpoints=self.endpoints,
            proxy_type=self.proxy_type, proxy_url=self.proxy_url,
            default_max_process=5, default_max_timeout=30,
            default_max_audio_duration=60, max_process=5, max_timeout=30,
        )

    def update_api(self, api_id, fields):
        return None


class TestHealthCheckProxy:

    @staticmethod
    def _install_log_noop(monkeypatch):
        # 健康检查落日志经 log_and_emit → DatabaseLogHandler（惰性创建），
        # 测试内替换为 no-op，避免拉起 DB 日志 worker
        monkeypatch.setattr(api_crud_module, 'log_not_emit', lambda **kw: None)

    def test_http_health_uses_proxies(self, monkeypatch):
        import requests
        captured = {}

        def fake_get(url, timeout=None, headers=None, proxies=None, **kw):
            captured['url'] = url
            captured['proxies'] = proxies
            return SimpleNamespace(status_code=200, text='{}', encoding='utf-8', json=lambda: {})

        monkeypatch.setattr(requests, 'get', fake_get)
        repo = _HealthRepo(proxy_type='http', proxy_url='user:pass@proxy.local:8080')
        _install_repo(monkeypatch, repo)
        self._install_log_noop(monkeypatch)

        res = APICrudService.test_connection(7)
        assert res['data']['api_url_status'] == 'True'
        assert captured['proxies'] == {'http': 'http://user:pass@proxy.local:8080',
                                       'https': 'http://user:pass@proxy.local:8080'}
        # 健康检查 URL 追加 /health 前缀路径
        assert captured['url'] == 'http://api.example.com/health'

    def test_http_health_no_proxy_proxies_none(self, monkeypatch):
        import requests
        captured = {}

        def fake_get(url, timeout=None, headers=None, proxies=None, **kw):
            captured['proxies'] = proxies
            return SimpleNamespace(status_code=200, text='{}', encoding='utf-8', json=lambda: {})

        monkeypatch.setattr(requests, 'get', fake_get)
        repo = _HealthRepo(proxy_type=None, proxy_url=None)
        _install_repo(monkeypatch, repo)
        self._install_log_noop(monkeypatch)

        res = APICrudService.test_connection(7)
        assert res['data']['api_url_status'] == 'True'
        assert captured['proxies'] is None

    def test_ws_health_uses_websocket_proxy_kwargs(self, monkeypatch):
        import websocket as ws_client
        captured = {}

        class _FakeWS:
            def settimeout(self, t):
                pass

            def connect(self, url, **kwargs):
                captured['url'] = url
                captured['kwargs'] = kwargs

            def close(self):
                pass

        monkeypatch.setattr(ws_client, 'WebSocket', _FakeWS)
        repo = _HealthRepo(api_url='ws://api.example.com/ws',
                           proxy_type='socks5', proxy_url='user:pass@proxy.local:1080')
        _install_repo(monkeypatch, repo)
        self._install_log_noop(monkeypatch)

        res = APICrudService.test_connection(7)
        assert res['data']['api_url_status'] == 'True'
        assert captured['kwargs']['http_proxy_host'] == 'proxy.local'
        assert captured['kwargs']['http_proxy_port'] == 1080
        assert captured['kwargs']['http_proxy_auth'] == ('user', 'pass')
        assert captured['kwargs']['proxy_type'] == 'socks5'

    def test_ws_endpoint_health_uses_proxy_kwargs(self, monkeypatch):
        import requests
        import websocket as ws_client
        captured = {}

        def fake_get(url, timeout=None, headers=None, proxies=None, **kw):
            # api_url 为 http → 走 requests.get 分支，200 避免影响端点断言
            return SimpleNamespace(status_code=200, text='{}', encoding='utf-8', json=lambda: {})

        monkeypatch.setattr(requests, 'get', fake_get)

        class _FakeWS:
            def settimeout(self, t):
                pass

            def connect(self, url, **kwargs):
                captured['url'] = url
                captured['kwargs'] = kwargs

            def close(self):
                pass

        monkeypatch.setattr(ws_client, 'WebSocket', _FakeWS)
        repo = _HealthRepo(
            api_url='http://api.example.com',
            endpoints=[{'endpoint': 'ws://api.example.com/stream', 'max_timeout': 30}],
            proxy_type='http', proxy_url='user:pass@proxy.local:8080')
        _install_repo(monkeypatch, repo)
        self._install_log_noop(monkeypatch)

        res = APICrudService.test_connection(7)
        assert captured['url'] == 'ws://api.example.com/stream'
        assert captured['kwargs']['http_proxy_host'] == 'proxy.local'
        assert captured['kwargs']['proxy_type'] == 'http'


# ═══════════════════ api_client ═══════════════════

class TestApiClientProxy:

    def test_call_http_proxies_injected(self, monkeypatch):
        import requests
        captured = {}

        def fake_get(url, params=None, headers=None, timeout=None, proxies=None):
            captured['proxies'] = proxies
            return SimpleNamespace(status_code=200, text='{}', encoding='utf-8', json=lambda: {})

        monkeypatch.setattr(requests, 'get', fake_get)
        result = APIClient._call_http(
            'http://api.example.com/api', method='GET',
            proxy_type='http', proxy_url='user:pass@proxy.local:8080')
        assert result['status_code'] == 200
        assert captured['proxies'] == {'http': 'http://user:pass@proxy.local:8080',
                                       'https': 'http://user:pass@proxy.local:8080'}

    def test_call_http_no_proxy_no_proxies(self, monkeypatch):
        import requests
        captured = {}

        def fake_get(url, params=None, headers=None, timeout=None, proxies=None):
            captured['proxies'] = proxies
            return SimpleNamespace(status_code=200, text='{}', encoding='utf-8', json=lambda: {})

        monkeypatch.setattr(requests, 'get', fake_get)
        APIClient._call_http('http://api.example.com/api', method='GET')
        assert captured['proxies'] is None

    def test_call_websocket_proxy_kwargs_injected(self, monkeypatch):
        import websocket as ws_client
        captured = {}

        class _FakeWS:
            def settimeout(self, t):
                pass

            def send(self, *a, **k):
                pass

            def send_binary(self, *a, **k):
                pass

            def recv(self, *a, **k):
                return None  # 空消息 → 内层循环立即退出

            def close(self):
                pass

        def fake_create_connection(url, timeout=None, header=None, **kwargs):
            captured['url'] = url
            captured['kwargs'] = kwargs
            return _FakeWS()

        monkeypatch.setattr(ws_client, 'create_connection', fake_create_connection)
        result = APIClient._call_websocket(
            'ws://api.example.com/ws', data=None, headers=None, timeout=5, meta={},
            proxy_type='http', proxy_url='user:pass@proxy.local:8080')
        assert result['status_code'] == 200
        assert captured['kwargs']['http_proxy_host'] == 'proxy.local'
        assert captured['kwargs']['http_proxy_port'] == 8080
        assert captured['kwargs']['http_proxy_auth'] == ('user', 'pass')
        assert captured['kwargs']['proxy_type'] == 'http'

    def test_call_dispatches_proxy_to_websocket(self, monkeypatch):
        import websocket as ws_client

        def fake_create_connection(url, timeout=None, header=None, **kwargs):
            ws = SimpleNamespace()
            ws.settimeout = lambda t: None
            ws.send = lambda *a, **k: None
            ws.send_binary = lambda *a, **k: None
            ws.recv = lambda *a, **k: None
            ws.close = lambda *a, **k: None
            return ws

        monkeypatch.setattr(ws_client, 'create_connection', fake_create_connection)
        result = APIClient.call(
            'ws://api.example.com/ws', data=None, meta={},
            proxy_type='socks5', proxy_url='user:pass@proxy.local:1080')
        assert result['status_code'] == 200


# ═══════════════════ realtime_ws_client ═══════════════════

class TestRealtimeWSClientProxy:

    def test_connect_proxy_kwargs_from_init(self, monkeypatch):
        import websocket as ws_client
        captured = {}

        class _FakeWS:
            def recv(self, *a, **k):
                return None

            def close(self):
                pass

            def send(self, *a, **k):
                pass

        def fake_create_connection(url, header=None, timeout=None, enable_multithread=None, **kwargs):
            captured['url'] = url
            captured['kwargs'] = kwargs
            return _FakeWS()

        monkeypatch.setattr(ws_client, 'create_connection', fake_create_connection)
        client = RealtimeWSClient('ws://api.example.com/rt',
                                  proxy_type='socks5', proxy_url='user:pass@proxy.local:1080')
        assert client.connect() is True
        assert captured['kwargs']['http_proxy_host'] == 'proxy.local'
        assert captured['kwargs']['http_proxy_port'] == 1080
        assert captured['kwargs']['http_proxy_auth'] == ('user', 'pass')
        assert captured['kwargs']['proxy_type'] == 'socks5'
        client.close()

    def test_connect_no_proxy_no_kwargs(self, monkeypatch):
        import websocket as ws_client
        captured = {}

        class _FakeWS:
            def recv(self, *a, **k):
                return None

            def close(self):
                pass

            def send(self, *a, **k):
                pass

        def fake_create_connection(url, header=None, timeout=None, enable_multithread=None, **kwargs):
            captured['kwargs'] = kwargs
            return _FakeWS()

        monkeypatch.setattr(ws_client, 'create_connection', fake_create_connection)
        client = RealtimeWSClient('ws://api.example.com/rt')
        assert client.connect() is True
        # 无代理：不注入 http_proxy_host（kwargs 不含代理键）
        assert 'http_proxy_host' not in captured['kwargs']
        client.close()

    def test_connect_call_param_overrides_init(self, monkeypatch):
        import websocket as ws_client
        captured = {}

        class _FakeWS:
            def recv(self, *a, **k):
                return None

            def close(self):
                pass

            def send(self, *a, **k):
                pass

        def fake_create_connection(url, header=None, timeout=None, enable_multithread=None, **kwargs):
            captured['kwargs'] = kwargs
            return _FakeWS()

        monkeypatch.setattr(ws_client, 'create_connection', fake_create_connection)
        client = RealtimeWSClient('ws://api.example.com/rt',
                                  proxy_type='http', proxy_url='user:pass@a.local:8080')
        assert client.connect(proxy_type='socks5h', proxy_url='u:p@b.local:1080') is True
        assert captured['kwargs']['http_proxy_host'] == 'b.local'
        assert captured['kwargs']['proxy_type'] == 'socks5h'
        client.close()


# ═══════════════════ secret_mask ═══════════════════

class TestSecretMaskProxy:

    def test_mask_text_proxy_url_userinfo(self):
        masked = mask_text('config {"proxy_url": "user:pass@proxy.local:8080"} sent')
        assert 'user:pass@' not in masked
        assert 'proxy.local:8080' in masked
        assert '"proxy_url": "****@proxy.local:8080"' in masked

    def test_mask_text_proxy_url_kv_form(self):
        masked = mask_text('proxy_url=user:pass@proxy.local:8080, ok')
        assert 'user:pass@' not in masked
        assert '****@proxy.local:8080' in masked

    def test_mask_text_proxy_url_idempotent(self):
        once = mask_text('"proxy_url": "user:pass@proxy.local:8080"')
        assert mask_text(once) == once

    def test_mask_text_proxy_url_scheme_prefix_masked(self):
        """审计 P2 修复：误带 scheme 前缀的 proxy_url 不再明文泄露 user:pass"""
        masked = mask_text('proxy_url=http://user:pass@proxy.local:8080')
        assert 'user:pass@' not in masked
        assert 'http://****@proxy.local:8080' in masked

    def test_mask_text_proxy_url_at_in_password(self):
        """审计 P3 修复：密码含字面 @ 时按末个 @ 切分掩码，不泄露段"""
        masked = mask_text('proxy_url=user:p@ss@proxy.local:8080')
        assert 'p@ss@' not in masked
        assert 'p@ss' not in masked
        assert '****@proxy.local:8080' in masked

    def test_mask_mapping_proxy_url_userinfo(self):
        masked = mask_mapping({'proxy_url': 'user:pass@proxy.local:8080', 'host': 'x'})
        assert masked['proxy_url'] == '****@proxy.local:8080'
        assert masked['host'] == 'x'

    def test_mask_mapping_nested_proxy_url(self):
        payload = {'vendor_config': {'proxy_url': 'u:p@proxy.local:8080'}}
        masked = mask_mapping(payload)
        assert 'u:p@' not in masked['vendor_config']['proxy_url']
        assert masked['vendor_config']['proxy_url'] == '****@proxy.local:8080'

    def test_mask_mapping_proxy_url_scheme_prefix_masked(self):
        """审计 P2 修复：结构化 payload 中带 scheme 前缀的 proxy_url 同样脱敏"""
        masked = mask_mapping({'proxy_url': 'http://user:pass@proxy.local:8080'})
        assert 'user:pass@' not in masked['proxy_url']
        assert masked['proxy_url'] == 'http://****@proxy.local:8080'

    def test_mask_mapping_proxy_url_at_in_password(self):
        """审计 P3 修复：密码含字面 @ 时按末个 @ 切分掩码，不泄露段"""
        masked = mask_mapping({'proxy_url': 'user:p@ss@proxy.local:8080'})
        assert 'p@ss' not in masked['proxy_url']
        assert masked['proxy_url'] == '****@proxy.local:8080'

    def test_mask_mapping_proxy_url_no_auth_unchanged(self):
        """无认证段（无 @）时原样保留，不误伤 host:port"""
        assert mask_mapping({'proxy_url': 'proxy.local:8080'}) == {'proxy_url': 'proxy.local:8080'}


# ═══════════════════ vendor_config 契约（#2 交付） ═══════════════════

class TestVendorConfigProxyContract:
    """api_session_executor.vendor_config 必须显式携带 proxy_type / proxy_url。

    api_adapter_service 透传白名单（现状仅 api_url/headers/timeout/adapter_class/
    api_key_candidates）不会自动透传字段，缺失即「配置能存、执行不过代理」。
    """

    def test_vendor_config_carries_proxy_fields(self, monkeypatch):
        import json as _json

        from api_test_service.core import api_session_executor as ase_module
        from api_test_service.core.api_session_executor import APISessionExecutor

        class _FakeExecutor:
            @property
            def _log(self):
                return lambda *a, **k: None

        class _FakeACL:
            def __init__(self):
                self.captured = {}

            def send_round(self, req):
                self.captured['vendor_config'] = _json.loads(req.vendor_config)
                return {'output_content': 'ok', 'output_audio_path': None,
                        'response_metrics': {}}

        api_config = SimpleNamespace(
            id=1, name='API-P', api_url='http://api.example.com',
            api_endpoints=[], default_max_process=5, meta={}, max_timeout=30,
            vendor='vendor-x', adapter_class=None,
            proxy_type='http', proxy_url='user:pass@proxy.local:8080',
        )
        fake_acl = _FakeACL()
        monkeypatch.setattr(ase_module, '_adapter_acl', fake_acl)

        executor = APISessionExecutor(_FakeExecutor())
        result = executor._send_via_adapter(
            task_id=100, algorithm_type='translation',
            session=SimpleNamespace(
                session_id='s1', session_timeout=60,
                get_context=lambda: {}, get_context_for_request=lambda: {},
            ),
            round_number=1, total_rounds=1,
            rendered_headers={'Authorization': 'Bearer x'}, rendered_body={},
            api_specific_config={}, meta={}, api_config=api_config,
            timeout=70, input_text='hello', input_type='text', start_time=0,
            input_audio_path='', case_api_key='',
        )
        assert result['success'] is True
        vc = fake_acl.captured['vendor_config']
        assert vc['proxy_type'] == 'http'
        assert vc['proxy_url'] == 'user:pass@proxy.local:8080'
        assert vc['api_url'] == 'http://api.example.com'

    def test_vendor_config_omits_proxy_when_unset(self, monkeypatch):
        import json as _json

        from api_test_service.core import api_session_executor as ase_module
        from api_test_service.core.api_session_executor import APISessionExecutor

        class _FakeExecutor:
            @property
            def _log(self):
                return lambda *a, **k: None

        class _FakeACL:
            def send_round(self, req):
                vc = _json.loads(req.vendor_config)
                return {'output_content': 'ok', 'output_audio_path': None,
                        'response_metrics': {}, '_vc': vc}

        api_config = SimpleNamespace(
            id=1, name='API-N', api_url='http://api.example.com',
            api_endpoints=[], default_max_process=5, meta={}, max_timeout=30,
            vendor='vendor-x', adapter_class=None,
            proxy_type=None, proxy_url=None,
        )
        monkeypatch.setattr(ase_module, '_adapter_acl', _FakeACL())

        executor = APISessionExecutor(_FakeExecutor())
        result = executor._send_via_adapter(
            task_id=100, algorithm_type='translation',
            session=SimpleNamespace(
                session_id='s1', session_timeout=60,
                get_context=lambda: {}, get_context_for_request=lambda: {},
            ),
            round_number=1, total_rounds=1,
            rendered_headers={}, rendered_body={},
            api_specific_config={}, meta={}, api_config=api_config,
            timeout=70, input_text='hello', input_type='text', start_time=0,
            input_audio_path='', case_api_key='',
        )
        assert 'proxy_type' not in result.get('_vc', {})
        assert 'proxy_url' not in result.get('_vc', {})


# ═══════════════════ 迁移脚本 ═══════════════════

_MIGRATION_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..',
    'scripts', 'migrations', '202610', 'add_api_proxy_columns.py')


def _load_migration_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location('add_api_proxy_columns', _MIGRATION_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeMigrateCursor:
    """迁移脚本假游标：information_schema 查询分支按列存在性返回。"""

    def __init__(self, existing):
        self.existing = existing
        self.executed_sql = []
        self._last = None

    def execute(self, sql, params=None):
        self.executed_sql.append(sql)
        if 'information_schema.columns' in sql:
            self._last = 'check'

    def fetchone(self):
        if self._last == 'check':
            return (1,) if self.existing else None
        return None

    def close(self):
        pass


class _FakeMigrateConn:
    autocommit = True

    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        pass


def _run_migration(existing, dry_run=False):
    mod = _load_migration_module()
    cursor = _FakeMigrateCursor(existing=existing)
    conn = _FakeMigrateConn(cursor)
    captured = []
    with mock.patch.object(mod.psycopg2, 'connect', return_value=conn):
        with mock.patch('sys.stdout') as fake_stdout:
            def _write(text):
                captured.append(text)
            fake_stdout.write.side_effect = _write
            mod.migrate(dry_run=dry_run)
    return mod, cursor, ''.join(captured)


class TestProxyMigration:

    def test_columns_defined(self):
        mod = _load_migration_module()
        assert ('apis', 'proxy_type', 'VARCHAR(20)') in mod.COLUMNS
        assert ('apis', 'proxy_url', 'VARCHAR(255)') in mod.COLUMNS

    def test_api_po_has_proxy_columns(self):
        from api_test_service.infrastructure.persistence.models import API
        assert 'proxy_type' in API.__table__.columns
        assert 'proxy_url' in API.__table__.columns

    def test_migration_skips_when_columns_exist(self):
        mod, cursor, output = _run_migration(existing=True)
        assert output.count('[SKIP]') == 2
        assert not any('ALTER TABLE' in s for s in cursor.executed_sql)

    def test_migration_adds_missing_columns(self):
        mod, cursor, output = _run_migration(existing=False)
        alters = [s for s in cursor.executed_sql if 'ALTER TABLE' in s]
        assert len(alters) == 2
        assert any('proxy_type' in s for s in alters)
        assert any('proxy_url' in s for s in alters)
        assert output.count('[EXEC]') == 2

    def test_migration_dry_run_no_exec(self):
        mod, cursor, output = _run_migration(existing=False, dry_run=True)
        assert not any('ALTER TABLE' in s for s in cursor.executed_sql)
        assert '[DRY-RUN]' in output
