# -*- coding: utf-8 -*-
"""INT-2250 单测：评估等待轮询期失败分类与快速失败。

覆盖缺陷卡验收点：
  1. 轮询期端点不可达（连接级失败）→ 连续 N 次即收敛为「端点不可达」，
     不再空等到 evaluation_service.eval_max_wait_time（缺省 72000s = 20h）；
  2. 端点超时（ReadTimeout / 等待上限）与业务失败分别分类，错误文案可定位；
  3. 轮询形成的失败原因不再塌缩成 "Unknown error"，__error__ / __error_kind__
     透传到最终 resp_data（落 TRD.error_message）；
  4. {"code":0,"data":null} 不再 AttributeError，也不会被当成端点故障换端点重投；
  5. 换兜底端点重投前按 (task_id, test_case_id, 维度组) 判重。
"""
import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from evaluation_service.infrastructure.evaluation_api.api_request_handler import (
    ApiRequestHandler,
    EvalTaskRegistry,
)
from evaluation_service.infrastructure.evaluation_api.evaluation_api_client import (
    evaluationApiClient,
)
from shared.models.common_enums import EvalErrorKind


CONN_ERROR = {
    '__error__': 'GET http://ep-a/api/get_status/et-1 请求异常: HTTPConnectionPool ... refused',
    '__error_kind__': EvalErrorKind.CONNECTION.value,
}
TIMEOUT_ERROR = {
    '__error__': 'GET http://ep-a/api/get_status/et-1 请求异常: Read timed out.',
    '__error_kind__': EvalErrorKind.TIMEOUT.value,
}
BUSINESS_ERROR = {'__error__': 'API 返回错误: 500，请求URL: http://ep-a/api/get_status/et-1'}


@pytest.fixture(autouse=True)
def _clean_registry():
    """注册表是类级状态，用例前后清空，避免跨用例串味。"""
    EvalTaskRegistry._entries.clear()
    EvalTaskRegistry._cancelled.clear()
    EvalTaskRegistry._cancelled_cases.clear()
    yield
    EvalTaskRegistry._entries.clear()
    EvalTaskRegistry._cancelled.clear()
    EvalTaskRegistry._cancelled_cases.clear()


def _poll_host(statuses, result=None):
    """构造 wait_for_task_completion 所需的最小子集：状态按顺序返回，用尽后重复最后一个。"""
    seq = list(statuses)
    calls = {'n': 0}

    def _get_status(url, eval_task_id, timeout=30):
        idx = min(calls['n'], len(seq) - 1)
        calls['n'] += 1
        return seq[idx]

    host = SimpleNamespace(
        _log=MagicMock(),
        _wait_for_redis_callback=MagicMock(return_value=None),
        get_task_status=MagicMock(side_effect=_get_status),
        get_task_result=MagicMock(return_value=result or {'code': 0, 'data': {'result': {'wer': 0.1}}}),
        calls=calls,
    )
    return host


def _wait(host, max_wait=600, poll_interval=0.01):
    return ApiRequestHandler.wait_for_task_completion(
        host, 'http://ep-a', 'et-1', max_wait_time=max_wait, poll_interval=poll_interval,
        test_case_id='c1', task_id=1,
    )


# ==================== 1. 轮询期快速失败与分类 ====================

class TestPollingFastFail:
    def test_connection_failures_converge_fast(self):
        """端点不可达：连续 3 次即收敛为「端点不可达」，不再等满 max_wait。"""
        host = _poll_host([CONN_ERROR])
        resp = _wait(host, max_wait=600)

        assert resp['__error_kind__'] == EvalErrorKind.CONNECTION.value
        assert '评估端点不可达' in resp['__error__']
        assert 'http://ep-a' in resp['__error__']
        assert '连续 3 次' in resp['__error__']
        # 快速失败：只轮询了阈值次数，远小于 600s / 0.01s 的轮询次数
        assert host.calls['n'] == 3

    def test_timeout_failures_classified_as_timeout(self):
        """端点超时（ReadTimeout）：分类为 timeout，文案「结果未知」，不冒充不可达。"""
        host = _poll_host([TIMEOUT_ERROR])
        resp = _wait(host, max_wait=600)

        assert resp['__error_kind__'] == EvalErrorKind.TIMEOUT.value
        assert '响应超时' in resp['__error__']
        assert '结果未知' in resp['__error__']
        assert host.calls['n'] == 3

    def test_business_query_failures_classified_as_business(self):
        """状态查询持续返回业务错误（HTTP 5xx 等）：按 business 类别快速失败。"""
        host = _poll_host([BUSINESS_ERROR])
        resp = _wait(host, max_wait=600)

        assert resp['__error_kind__'] == EvalErrorKind.BUSINESS.value
        assert '状态查询连续失败' in resp['__error__']
        assert '500' in resp['__error__']
        assert host.calls['n'] == 6

    def test_transient_failures_reset_streak(self):
        """偶发失败不误杀：连续 2 次失败后恢复，计数清零，最终正常出结果。"""
        host = _poll_host([
            CONN_ERROR,
            CONN_ERROR,
            {'code': 0, 'data': {'status': 'processing'}},
            CONN_ERROR,
            CONN_ERROR,
            {'code': 0, 'data': {'status': 'completed'}},
        ])
        resp = _wait(host, max_wait=600)

        assert '__error__' not in resp
        assert resp['code'] == 0
        assert resp['data']['result']['wer'] == 0.1
        assert host.calls['n'] == 6

    def test_max_wait_exhausted_carries_timeout_kind(self):
        """等待上限耗尽属「结果未知」：带 timeout 类别与端点/配置定位信息。"""
        host = _poll_host([{'code': 0, 'data': {'status': 'processing'}}])
        resp = _wait(host, max_wait=0.05, poll_interval=0.01)

        assert resp['__error_kind__'] == EvalErrorKind.TIMEOUT.value
        assert '评估任务超时' in resp['__error__']
        assert 'http://ep-a' in resp['__error__']
        assert 'eval_max_wait_time' in resp['__error__']

    def test_status_query_data_null_does_not_crash(self):
        """get_status 返回 {"code":0,"data":null} 时按 pending 处理，不 AttributeError。"""
        host = _poll_host([
            {'code': 0, 'data': None},
            {'code': 0, 'data': {'status': 'completed'}},
        ])
        resp = _wait(host, max_wait=600)

        assert '__error__' not in resp
        assert resp['code'] == 0
        assert resp['data']['result']['wer'] == 0.1


# ==================== 2. 异常分类（连接级 vs 超时） ====================

class TestExceptionClassification:
    def _handler(self):
        h = ApiRequestHandler()
        h._log = lambda *a, **k: None
        return h

    def test_connect_timeout_marked_connection(self, monkeypatch):
        import requests
        import evaluation_service.infrastructure.evaluation_api.api_request_handler as mod

        def _raise(*a, **k):
            raise requests.exceptions.ConnectTimeout('connection timed out')
        monkeypatch.setattr(mod.requests, 'get', _raise)

        resp = self._handler().make_api_request('http://x/api/get_status/1', 'GET', {}, {})
        assert resp['__error_kind__'] == EvalErrorKind.CONNECTION.value

    def test_read_timeout_marked_timeout(self, monkeypatch):
        """连接已建立但无响应（ReadTimeout）→ timeout，不触发兜底端点切换。"""
        import requests
        import evaluation_service.infrastructure.evaluation_api.api_request_handler as mod

        def _raise(*a, **k):
            raise requests.exceptions.ReadTimeout('read timed out')
        monkeypatch.setattr(mod.requests, 'get', _raise)

        resp = self._handler().make_api_request('http://x/api/get_status/1', 'GET', {}, {})
        assert resp['__error_kind__'] == EvalErrorKind.TIMEOUT.value
        assert 'GET' in resp['__error__'] and 'http://x/api/get_status/1' in resp['__error__']

    def test_create_task_upload_read_timeout_marked_timeout(self, monkeypatch):
        import requests
        import evaluation_service.infrastructure.evaluation_api.api_request_handler as mod

        def _raise(*a, **k):
            raise requests.exceptions.ReadTimeout('read timed out')
        monkeypatch.setattr(mod.requests, 'post', _raise)

        resp = self._handler().create_task_upload('http://x', {}, {}, task_id=1)
        assert resp['__error_kind__'] == EvalErrorKind.TIMEOUT.value


# ==================== 3. 错误原因透传（不再 Unknown error） ====================

class TestErrorPropagation:
    @staticmethod
    def _fake_client(wait_return):
        return SimpleNamespace(
            _log=MagicMock(),
            wait_for_task_completion=MagicMock(return_value=wait_return),
        )

    def test_polling_failure_reason_and_kind_preserved(self):
        """轮询失败原因与类别透传到 resp_data（原先塌缩成 "Unknown error"）。"""
        client = self._fake_client({
            '__error__': '评估端点不可达: 端点 http://ep-a 连续 3 次查询状态失败',
            '__error_kind__': EvalErrorKind.CONNECTION.value,
        })

        resp = evaluationApiClient._process_async_result(
            client, {'code': 0, 'data': {'eval_task_id': 'e-2250'}},
            'http://ep-a', 1, 'c1', None, dim_names=['wer'],
        )

        assert resp['__error__'].startswith('评估端点不可达')
        assert resp['__error_kind__'] == EvalErrorKind.CONNECTION.value

    def test_timeout_reason_preserved(self):
        client = self._fake_client({
            '__error__': '评估任务超时: eval_task_id=e-2250',
            '__error_kind__': EvalErrorKind.TIMEOUT.value,
        })

        resp = evaluationApiClient._process_async_result(
            client, {'code': 0, 'data': {'eval_task_id': 'e-2250'}},
            'http://ep-a', 1, 'c1', None,
        )
        assert resp['__error__'].startswith('评估任务超时')
        assert resp['__error_kind__'] == EvalErrorKind.TIMEOUT.value

    def test_create_response_data_null_no_attribute_error(self):
        """{"code":0,"data":null}：不发散异常、不带 connection 类别（不换端点重投）。"""
        client = SimpleNamespace(_log=MagicMock())

        resp = evaluationApiClient._process_async_result(
            client, {'code': 0, 'data': None}, 'http://ep-a', 1, 'c1', None,
        )

        assert '未携带 eval_task_id' in resp['__error__']
        assert 'data=null' in resp['__error__']
        assert '__error_kind__' not in resp


# ==================== 4. 换端点重投判重 ====================

class TestFallbackRedispatchDedup:
    def _client(self):
        client = evaluationApiClient()
        client._log = MagicMock()
        return client

    def test_same_group_inflight_on_fallback_skips_redispatch(self, monkeypatch):
        """同一维度组已在该兜底端点在途 → 跳过重投，不重复提交同一评估。"""
        client = self._client()
        monkeypatch.setattr(client, '_get_fallback_urls', lambda exclude_url=None: ['http://ep-b'])
        called = {'n': 0}

        def _unexpected(*a, **k):
            called['n'] += 1
            raise AssertionError('同一评估已在途，不应重复提交')
        monkeypatch.setattr(client, '_try_single_fallback', _unexpected)

        EvalTaskRegistry.register('e-other', 1, 'http://ep-b', test_case_id='c1', dim_key=('wer',))
        selected_url, resp = client._try_configured_fallback_urls(
            'http://ep-a', [], 'POST', {}, {}, 1, 'c1', None, ['wer'], {},
            audio_field_names=None, primary_error=CONN_ERROR,
        )

        assert called['n'] == 0
        assert resp is None
        assert selected_url == 'http://ep-a'

    def test_different_dim_group_is_not_deduped(self, monkeypatch):
        """不同维度组并发提交是合法的，判重不能误伤。"""
        seen = []

        def _fake_single(fallback_url, endpoints, method, headers, payload,
                         task_id, test_case_id, api_id, dim_names, dim_info,
                         audio_field_names=None):
            seen.append((fallback_url, tuple(dim_names)))
            return True, fallback_url, {'score': 1.0}

        client = self._client()
        monkeypatch.setattr(client, '_get_fallback_urls', lambda exclude_url=None: ['http://ep-b'])
        monkeypatch.setattr(client, '_try_single_fallback', _fake_single)

        EvalTaskRegistry.register('e-other', 1, 'http://ep-b', test_case_id='c1', dim_key=('ser',))
        selected_url, resp = client._try_configured_fallback_urls(
            'http://ep-a', [], 'POST', {}, {}, 1, 'c1', None, ['wer'], {},
            audio_field_names=None, primary_error=CONN_ERROR,
        )

        assert seen == [('http://ep-b', ('wer',))]
        assert selected_url == 'http://ep-b'
        assert resp == {'score': 1.0}


class TestRegistryInflight:
    def test_matches_task_case_endpoint_and_dim_key(self):
        EvalTaskRegistry.register('e1', '1', 'http://ep-a', test_case_id='c1', dim_key=('wer',))

        assert EvalTaskRegistry.has_inflight(1, 'c1', 'http://ep-a', ('wer',)) is True
        assert EvalTaskRegistry.has_inflight(1, 'c1', 'http://ep-a', ('ser',)) is False
        assert EvalTaskRegistry.has_inflight(1, 'c1', 'http://ep-b', ('wer',)) is False
        assert EvalTaskRegistry.has_inflight(2, 'c1', 'http://ep-a', ('wer',)) is False
        assert EvalTaskRegistry.has_inflight(1, 'c2', 'http://ep-a', ('wer',)) is False

    def test_any_of_scope_when_not_limited(self):
        EvalTaskRegistry.register('e1', 1, 'http://ep-a', test_case_id='c1')
        assert EvalTaskRegistry.has_inflight(1, 'c1') is True
        assert EvalTaskRegistry.has_inflight(1, 'c1', 'http://ep-b') is False

    def test_unregistered_task_is_not_inflight(self):
        EvalTaskRegistry.register('e1', 1, 'http://ep-a', test_case_id='c1')
        EvalTaskRegistry.unregister('e1')
        assert EvalTaskRegistry.has_inflight(1, 'c1') is False


# ==================== 5. 真实 socket 链路：端点不可达快速收敛 ====================

_DEAD_SOCKETS = []


def _unreachable_url():
    """绑定但不 listen 的本地端口（连接立即被拒），socket 由模块级列表持有防端口复用。"""
    s = socket.socket()
    if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    s.bind(('127.0.0.1', 0))
    _DEAD_SOCKETS.append(s)
    return f'http://127.0.0.1:{s.getsockname()[1]}'


class TestRealSocketUnreachable:
    def test_real_connection_refused_converges_fast(self):
        """真实 socket（连接被拒）走完请求→分类→快速失败，耗时远小于 eval_max_wait_time。"""
        url = _unreachable_url()
        handler = ApiRequestHandler()
        handler._log = MagicMock()
        handler._wait_for_redis_callback = MagicMock(return_value=None)

        started = time.time()
        resp = handler.wait_for_task_completion(
            url, 'et-real-2250', max_wait_time=600, poll_interval=0.01)
        elapsed = time.time() - started

        assert resp['__error_kind__'] == EvalErrorKind.CONNECTION.value
        assert '评估端点不可达' in resp['__error__']
        assert url in resp['__error__']
        assert '连续 3 次' in resp['__error__']
        # 真实网络错误原文可见（可定位）
        assert 'Connection' in resp['__error__'] or 'refused' in resp['__error__'] \
            or 'Max retries exceeded' in resp['__error__']
        # Windows 上 connect 到「已 bind 未 listen」端口每次约 2s（SYN 重传），
        # 3 次阈值仍能在 30s 内收敛，远小于缺省 eval_max_wait_time=72000s
        assert elapsed < 30


# ==================== 6. 真实 HTTP 端到端：创建成功→轮询期端点挂掉 ====================

class _AbortPollEvalServer:
    """create_task 正常发号，随后 get_status 不回包直接断连（历史 RemoteDisconnected 场景）。"""

    def __init__(self):
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.0'

            def log_message(self, *args):
                pass

            def _json(self, obj, status=200):
                body = json.dumps(obj).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                outer.requests.append(('POST', self.path))
                return self._json({'code': 0, 'data': {'eval_task_id': 'et-die-2250'}})

            def do_GET(self):
                outer.requests.append(('GET', self.path))
                # 端点中途挂掉：不回包，直接断连
                self.close_connection = True

        self._server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self._server.server_address[1]}'
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._server.shutdown()
        self._server.server_close()


class TestEndpointDiesMidPollEndToEnd:
    def test_real_http_create_ok_then_poll_connection_dies(self, monkeypatch):
        """真实 HTTP：创建成功、轮询期端点断连 → 快速失败并带「端点不可达」原因。"""
        import evaluation_service.infrastructure.evaluation_api.api_request_handler as handler_mod

        stub = _AbortPollEvalServer()
        stub.start()
        try:
            monkeypatch.delenv('EVAL_FALLBACK_URLS', raising=False)
            fast_cfg = SimpleNamespace(
                get_value=lambda section, key, default=None:
                    0.01 if key == 'poll_interval' else default)
            monkeypatch.setattr(handler_mod, 'config_manager', fast_cfg)

            client = evaluationApiClient()
            client._log = MagicMock()
            client._wait_for_redis_callback = MagicMock(return_value=None)
            # 本用例不走文件上传：跳过 storage.exists 探测（离线 OSS 会串行重试数十秒）
            client._is_file_value = lambda value: False

            started = time.time()
            selected_url, resp = client.make_api_request_with_fallback(
                endpoints=[], method='POST', headers={},
                payload={'duration': 1.5},
                task_id=2250, dim_names=['wer'], api_url=stub.url,
                test_case_id='int2250-e2e', dim_info={'task_type_code': 'wer'},
            )
            elapsed = time.time() - started

            assert selected_url == stub.url
            assert resp['__error_kind__'] == EvalErrorKind.CONNECTION.value
            assert '评估端点不可达' in resp['__error__']
            assert '连续 3 次' in resp['__error__']
            # 只轮询了阈值次数，未空转至 eval_max_wait_time
            assert len([r for r in stub.requests if r[0] == 'GET']) == 3
            assert elapsed < 30
        finally:
            stub.stop()
