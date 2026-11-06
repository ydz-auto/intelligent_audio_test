# -*- coding: utf-8 -*-
"""INT-2287：维度健康探测以 api_url 为目标、空结果不再算 online、api_settings.timeout 生效。

背景：``EndpointHealthChecker.check_endpoints`` 只遍历 ``api_endpoints[].url/endpoint``，
而库内真实端点在 ``dimensions.api_url``（单列）、``api_endpoints[].url`` 普遍是空串，
导致一个端点都没探测就返回 ``results=[] / all_online=True``，调用方据此把不可达维度
写成「在线」。

本文件钉死（不连库、不连外网，本地回环 HTTP 替身）：
1. api_url 有值、api_endpoints[].url 全空串 → 真的探测 api_url（旧实现 0 次探测）；
2. api_endpoints 里有 url 时一并探测（去重保序），任一失败 → all_online=False；
3. api_url 与 api_endpoints 都空 → configured=False、results=[]、all_online=False + 明确文案；
4. 端点只要有 HTTP 响应（<500，含 404/405 这种评估服务根路径常态）算可达；5xx 算离线；
5. api_settings.timeout（毫秒）换算成 requests 秒数，探测封顶 10s；
6. Application 层 health_check：无端点落 offline 并回明确 message（不再 400/online）。
"""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost:1/unused')

from evaluation_service.domain.services.endpoint_helpers import (  # noqa: E402
    DEFAULT_API_TIMEOUT_SECONDS,
    MIN_API_TIMEOUT_SECONDS,
    get_api_timeout_seconds,
)
from evaluation_service.infrastructure.evaluation_api import health_checker  # noqa: E402
from evaluation_service.infrastructure.evaluation_api.health_checker import (  # noqa: E402
    EndpointHealthChecker,
)


# ==================== 本地回环 HTTP 替身 ====================


class _Handler(BaseHTTPRequestHandler):
    # path -> (status_code, body)
    routes = {}

    def do_GET(self):  # noqa: N802
        status, body = self.routes.get(self.path, (404, {'msg': 'not found'}))
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # 静默
        pass


@pytest.fixture()
def endpoint_server():
    handler = type('IsolatedHandler', (_Handler,), {'routes': {}})
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_address[1]}', handler.routes
    finally:
        server.shutdown()
        server.server_close()


def _settings(timeout_ms=None, headers=None):
    settings = {'method': 'POST'}
    if timeout_ms is not None:
        settings['timeout'] = timeout_ms
    if headers is not None:
        settings['headers'] = headers
    return settings


# ==================== 超时换算 ====================


class TestApiTimeoutSeconds:
    def test_milliseconds_to_seconds(self):
        assert get_api_timeout_seconds({'timeout': 30000}) == 30.0
        assert get_api_timeout_seconds({'timeout': 1500}) == 1.5

    def test_absent_or_invalid_falls_back(self):
        assert get_api_timeout_seconds(None) == DEFAULT_API_TIMEOUT_SECONDS
        assert get_api_timeout_seconds({}) == DEFAULT_API_TIMEOUT_SECONDS
        assert get_api_timeout_seconds({'timeout': None}) == DEFAULT_API_TIMEOUT_SECONDS
        assert get_api_timeout_seconds({'timeout': 'abc'}) == DEFAULT_API_TIMEOUT_SECONDS
        assert get_api_timeout_seconds({'timeout': 0}) == DEFAULT_API_TIMEOUT_SECONDS
        assert get_api_timeout_seconds({'timeout': -5}) == DEFAULT_API_TIMEOUT_SECONDS

    def test_tiny_value_floored(self):
        assert get_api_timeout_seconds({'timeout': 5}) == MIN_API_TIMEOUT_SECONDS


# ==================== 探测目标解析与判定 ====================


class TestCheckEndpoints:
    def test_probes_api_url_when_endpoint_urls_blank(self, endpoint_server):
        """核心缺陷：api_endpoints[].url 全空串时，旧实现 0 探测恒 online。"""
        base, routes = endpoint_server
        routes['/api'] = (200, {'ok': True})
        checker = EndpointHealthChecker()

        probe = checker.check_endpoints(
            endpoints=[{'url': '', 'endpoint': '', 'name': '', 'max_process': 5}],
            api_settings=_settings(),
            api_url=base,
        )

        assert probe['configured'] is True
        assert [item['url'] for item in probe['results']] == [base]
        assert probe['results'][0]['status'] == 'online'
        assert probe['all_online'] is True

    def test_probes_each_endpoint_url_and_fails_on_any_offline(self, endpoint_server):
        base, routes = endpoint_server
        routes['/health'] = (200, {'ok': True})
        routes['/boom'] = (503, {'msg': 'down'})
        checker = EndpointHealthChecker()

        probe = checker.check_endpoints(
            endpoints=[
                {'url': f'{base}/health'},
                {'endpoint': f'{base}/missing'},
                {'url': f'{base}/boom'},
            ],
            api_settings=_settings(),
            api_url=None,
        )

        urls = [item['url'] for item in probe['results']]
        assert urls == [f'{base}/health', f'{base}/missing', f'{base}/boom']
        statuses = {item['url']: item['status'] for item in probe['results']}
        assert statuses[f'{base}/health'] == 'online'
        assert statuses[f'{base}/missing'] == 'online'
        assert statuses[f'{base}/boom'] == 'offline'
        assert probe['all_online'] is False

    def test_http_response_below_500_counts_as_reachable(self, endpoint_server):
        """评估服务根路径回 404/405 是常态，端点仍可达。"""
        base, routes = endpoint_server
        checker = EndpointHealthChecker()

        probe = checker.check_endpoints(endpoints=[], api_settings={}, api_url=f'{base}/root')

        assert probe['results'][0]['status_code'] == 404
        assert probe['results'][0]['status'] == 'online'
        assert '端点可达' in probe['results'][0]['message']
        assert probe['all_online'] is True

    def test_no_target_is_not_online(self):
        """两者都空 → 未配置端点：空列表不得算「在线」。"""
        checker = EndpointHealthChecker()

        probe = checker.check_endpoints(
            endpoints=[{'url': '', 'endpoint': '', 'name': ''}],
            api_settings=_settings(),
            api_url='',
        )

        assert probe['results'] == []
        assert probe['all_online'] is False
        assert probe['configured'] is False
        assert '未配置 API 端点' in probe['message']

    def test_duplicate_urls_deduped(self, endpoint_server):
        base, routes = endpoint_server
        routes['/api'] = (200, {'ok': True})
        checker = EndpointHealthChecker()

        probe = checker.check_endpoints(
            endpoints=[{'url': base}, {'url': base}],
            api_settings=_settings(),
            api_url=base,
        )

        assert [item['url'] for item in probe['results']] == [base]

    def test_unreachable_endpoint_offline_with_error(self):
        """不可达端点（连接被拒）：offline + error，不再 online。"""
        checker = EndpointHealthChecker()

        probe = checker.check_endpoints(
            endpoints=[], api_settings={}, api_url='http://127.0.0.1:1',
        )

        assert probe['results'][0]['status'] == 'offline'
        assert probe['results'][0]['error']
        assert probe['all_online'] is False

    def test_api_settings_timeout_used_and_capped(self, endpoint_server, monkeypatch):
        """api_settings.timeout（毫秒）用于出站请求，探测封顶 PROBE_TIMEOUT_CAP_SECONDS。"""
        base, routes = endpoint_server
        routes['/api'] = (200, {'ok': True})
        captured = []
        real_get = health_checker.requests.get

        def _recording_get(url, **kwargs):
            captured.append(kwargs.get('timeout'))
            return real_get(url, **kwargs)

        monkeypatch.setattr(health_checker.requests, 'get', _recording_get)
        checker = EndpointHealthChecker()

        checker.check_endpoints(endpoints=[], api_settings=_settings(3000), api_url=base)
        checker.check_endpoints(endpoints=[], api_settings=_settings(30000), api_url=base)

        assert captured == [3.0, float(health_checker.PROBE_TIMEOUT_CAP_SECONDS)]

    def test_headers_from_api_settings_forwarded(self, endpoint_server, monkeypatch):
        base, routes = endpoint_server
        routes['/api'] = (200, {'ok': True})
        seen = {}
        real_get = health_checker.requests.get

        def _recording_get(url, **kwargs):
            seen.update(kwargs.get('headers') or {})
            return real_get(url, **kwargs)

        monkeypatch.setattr(health_checker.requests, 'get', _recording_get)

        EndpointHealthChecker().check_endpoints(
            endpoints=[], api_settings=_settings(headers={'X-Token': 'abc'}), api_url=base,
        )

        assert seen == {'X-Token': 'abc'}


# ==================== Application 层 health_check ====================


class _StubDimension:
    def __init__(self, **kwargs):
        self.id = 1
        self.name = '接线测试_维度'
        self.deleted = False
        self.created_by_user_id = None
        self.visibility = 'shared'
        self.api_url = None
        self.api_endpoints = []
        self.api_settings = {}
        self.api_status = 'online'
        for key, value in kwargs.items():
            setattr(self, key, value)


class _StubRepo:
    def __init__(self, dim):
        self._dim = dim
        self.commits = 0

    def get_dimension(self, dim_id):
        return self._dim

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


@pytest.fixture()
def command_service(monkeypatch):
    from evaluation_service.application.commands.evaluation_command_service import (
        evaluation_command_service,
    )

    original = evaluation_command_service.repo
    yield evaluation_command_service, monkeypatch
    monkeypatch.setattr(evaluation_command_service, 'repo', original)


# ==================== 维度配置的超时在评估请求链上生效 ====================


def _make_api_client():
    from evaluation_service.infrastructure.evaluation_api.evaluation_api_client import (
        evaluationApiClient,
    )

    client = evaluationApiClient()
    client.logs = []
    client._log = lambda **kwargs: client.logs.append(kwargs)
    return client


class TestApiSettingsTimeoutWiring:
    def test_make_api_request_with_fallback_resolves_configured_timeout(self):
        client = _make_api_client()
        captured = {}

        def _fake_acquire(*args, **kwargs):
            captured.update(kwargs)
            return {'code': 0}

        client._acquire_and_execute = _fake_acquire

        client.make_api_request_with_fallback(
            endpoints=[{'url': 'http://ep-a'}], method='POST', headers={}, payload={},
            task_id=1, dim_names=['d1'], api_url='http://ep-a',
            api_settings={'timeout': 30000},
        )

        assert captured['request_timeout'] == 30.0

    def test_absent_api_settings_keeps_legacy_default(self):
        client = _make_api_client()
        captured = {}

        def _fake_acquire(*args, **kwargs):
            captured.update(kwargs)
            return {'code': 0}

        client._acquire_and_execute = _fake_acquire

        client.make_api_request_with_fallback(
            endpoints=[{'url': 'http://ep-a'}], method='POST', headers={}, payload={},
            task_id=1, dim_names=['d1'], api_url='http://ep-a',
        )

        assert captured['request_timeout'] == DEFAULT_API_TIMEOUT_SECONDS

    def test_create_async_task_forwards_resolved_timeout(self):
        client = _make_api_client()
        seen = {}

        def _fake_create_task(url, payload, timeout=None, task_id=None):
            seen.update(url=url, timeout=timeout, task_id=task_id)
            return {'code': 0}

        client.create_task = _fake_create_task

        client._create_async_task(
            'http://ep-a', {'f': 1}, {}, {'task_type': 'wer'}, 7, 'c1', None,
            request_timeout=2.5,
        )

        assert seen == {'url': 'http://ep-a', 'timeout': 2.5, 'task_id': 7}

    def test_create_task_falls_back_to_named_default(self, monkeypatch):
        """未传超时（None）时 create_task 仍用 10s 缺省，不回退成「无超时」。"""
        from evaluation_service.infrastructure.evaluation_api import api_request_handler

        client = _make_api_client()
        seen = {}

        def _fake_post(url, json=None, timeout=None, **kwargs):
            seen['timeout'] = timeout
            raise api_request_handler.requests.exceptions.ConnectionError('boom')

        monkeypatch.setattr(api_request_handler.requests, 'post', _fake_post)

        client.create_task('http://ep-a', {})

        assert seen['timeout'] == api_request_handler.DEFAULT_CREATE_TASK_TIMEOUT_SECONDS


class TestHealthCheckCommand:
    def test_probes_api_url_and_persists_online(self, endpoint_server, command_service):
        base, routes = endpoint_server
        routes['/api'] = (200, {'ok': True})
        service, monkeypatch = command_service
        dim = _StubDimension(api_url=base, api_endpoints=[{'url': '', 'endpoint': ''}])
        repo = _StubRepo(dim)
        monkeypatch.setattr(service, 'repo', repo)

        result = service.health_check(dim.id)

        assert result['success'] is True
        assert result['data']['overall_status'] == 'online'
        assert result['data']['results'][0]['url'] == base
        assert dim.api_status == 'online'
        assert repo.commits == 1

    def test_unreachable_endpoint_persists_offline(self, command_service):
        service, monkeypatch = command_service
        dim = _StubDimension(api_url='http://127.0.0.1:1')
        repo = _StubRepo(dim)
        monkeypatch.setattr(service, 'repo', repo)

        result = service.health_check(dim.id)

        assert result['success'] is True
        assert result['data']['overall_status'] == 'offline'
        assert result['data']['results'][0]['status'] == 'offline'
        assert dim.api_status == 'offline'

    def test_no_endpoint_configured_reports_offline_with_message(self, command_service):
        """两者都空：不再返回 online，也不再用 400 掩盖——offline + 明确文案。"""
        service, monkeypatch = command_service
        dim = _StubDimension(api_url=None, api_endpoints=[{'url': '', 'endpoint': ''}])
        repo = _StubRepo(dim)
        monkeypatch.setattr(service, 'repo', repo)

        result = service.health_check(dim.id)

        assert result['success'] is True
        assert result['data'] == {'results': [], 'overall_status': 'offline'}
        assert '未配置 API 端点' in result['message']
        assert dim.api_status == 'offline'
        assert repo.commits == 1
