# -*- coding: utf-8 -*-
"""INT-1790（A2）HTTP 流式（SSE / chunked）与事件切轮单测。

覆盖卡面「单测：SSE 帧解析（多行 data、空 event、retry）、切轮、超时」：

1. `transport/sse_client.py`
   - SSE 帧：多行 `data:` 拼接、`event:` / `id:` / `retry:` 字段、注释心跳、
     空 data 帧不派发、非 JSON data → 502 错误事件；
   - chunked 兜底：非 `text/event-stream` 响应按「一行一个 JSON」分帧；
   - 非 2xx → 连接失败（error_source=sse、biz_code=HTTP status）；
   - 空闲超时 → 504（不挂死）；开启重连则按 `Last-Event-ID` 续读；
   - 整体时长上限 → 504 `stream duration exceeded`。
2. `domain/services/stream_round_splitter.py`
   - 句子边界切轮 / `append_mode` 拼接 / 零声明退化为一条 message 一轮 /
     会话结束收尾 / `{"code":0,"data":{...}}` 标准格式 / 业务码透出。
3. `core/stream_session_executor.py`
   - 端到端（真实 transport + 真实切轮，执行器/ACL 用替身）：3 个事件含 1 个
     句子结束标记 → 2 轮，`rounds[i].output` 有值，结果与评估提交各一次。

测试内的 mock 服务是进程内临时 HTTP 服务（随机端口），不依赖 docker。
"""
import os
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from api_test_service.domain.services.stream_round_splitter import (
    StreamRoundSplitter,
)
from api_test_service.infrastructure.adapters.transport.sse_client import (
    EVENT_END_STREAM,
    EVENT_ERROR,
    EVENT_HEARTBEAT,
    EVENT_MESSAGE,
    HttpStreamClient,
)


# ──────────────────────────── 临时流式服务 ────────────────────────────

class _StreamHandler(BaseHTTPRequestHandler):
    """按 server.script 逐块输出；HTTP/1.0 无 content-length → 边写边读。"""

    protocol_version = 'HTTP/1.0'

    def do_GET(self):  # noqa: N802（BaseHTTPRequestHandler 约定）
        srv = self.server
        srv.requests.append({k.lower(): v for k, v in self.headers.items()})
        status = getattr(srv, 'status', 200)
        self.send_response(status)
        self.send_header('Content-Type', getattr(srv, 'content_type',
                                                 'text/event-stream'))
        self.end_headers()
        if status >= 400:
            self.wfile.write(b'boom')
            self.wfile.flush()
            return
        try:
            for chunk, delay in srv.script(self, len(srv.requests)):
                if delay:
                    time.sleep(delay)
                if chunk:
                    self.wfile.write(chunk.encode('utf-8')
                                     if isinstance(chunk, str) else chunk)
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get('Content-Length') or 0)
        self.rfile.read(length) if length else None
        return self.do_GET()

    def log_message(self, *args):
        pass


@contextmanager
def _serve(script, content_type='text/event-stream', status=200):
    srv = ThreadingHTTPServer(('127.0.0.1', 0), _StreamHandler)
    srv.daemon_threads = True
    srv.script = script
    srv.content_type = content_type
    srv.status = status
    srv.requests = []
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{srv.server_address[1]}/stream', srv, thread
    finally:
        srv.shutdown()
        srv.server_close()


def _events(client, limit=50):
    """排空客户端事件（最多 limit 条；error / end_stream 为终止事件）"""
    out = []
    for _ in range(limit):
        event = client.recv()
        out.append(event)
        if event['event_type'] in (EVENT_END_STREAM, EVENT_ERROR):
            break
    return out


# ──────────────────────────── SSE 帧解析 ────────────────────────────

class TestSseFrames:
    def test_multiline_data_event_id_retry(self):
        def script(handler, n):
            yield ': keep-alive\n\n', 0
            yield 'event: delta\n', 0
            yield 'id: 7\n', 0
            yield 'retry: 500\n', 0
            yield 'data: {"code": 0,\n', 0
            yield 'data:  "data": {"asr_result": "你好"}}\n', 0
            yield '\n', 0

        with _serve(script) as (url, srv, _):
            client = HttpStreamClient(url, idle_timeout_ms=2000)
            assert client.connect() is True
            events = _events(client)
            client.close()

        assert events[0]['event_type'] == EVENT_HEARTBEAT
        message = events[1]
        assert message['event_type'] == EVENT_MESSAGE
        # 多行 data 按 \n 拼接后整体 JSON 解析
        assert message['payload']['data'] == {'asr_result': '你好'}
        # event: 字段进 payload（且不污染 field_path 根）
        assert message['payload']['event'] == 'delta'
        assert events[-1]['event_type'] == EVENT_END_STREAM
        assert client.output['last_event_id'] == '7'

    def test_empty_data_frame_not_dispatched(self):
        def script(handler, n):
            yield 'event: ping\n\n', 0
            yield 'data: {"a": 1}\n\n', 0

        with _serve(script) as (url, srv, _):
            client = HttpStreamClient(url, idle_timeout_ms=2000)
            assert client.connect() is True
            events = _events(client)
            client.close()

        messages = [e for e in events if e['event_type'] == EVENT_MESSAGE]
        assert len(messages) == 1
        assert messages[0]['payload'] == {'a': 1, 'sse_event': ''}

    def test_invalid_json_frame_yields_error_event(self):
        def script(handler, n):
            yield 'data: not-json\n\n', 0

        with _serve(script) as (url, srv, _):
            client = HttpStreamClient(url, idle_timeout_ms=2000)
            assert client.connect() is True
            events = _events(client)
            client.close()

        error = [e for e in events if e['event_type'] == EVENT_ERROR][0]
        assert error['payload']['code'] == 502

    def test_non_2xx_fails_connect(self):
        with _serve(lambda h, n: iter(()), status=404) as (url, srv, _):
            client = HttpStreamClient(url, idle_timeout_ms=2000)
            assert client.connect() is False
            assert client.error_source == 'sse'
            assert client.biz_code == 404
            assert '404' in client.output['error']

    def test_chunked_json_lines_fallback(self):
        def script(handler, n):
            yield '{"asr_result": "a"}\n', 0
            yield '{"asr_result": "b"}\n', 0

        with _serve(script, content_type='application/x-ndjson') as (url, srv, _):
            client = HttpStreamClient(url, idle_timeout_ms=2000)
            assert client.connect() is True
            assert client.line_mode == 'chunked'
            events = _events(client)
            client.close()

        messages = [e['payload'] for e in events if e['event_type'] == EVENT_MESSAGE]
        assert [m['asr_result'] for m in messages] == ['a', 'b']

    def test_idle_timeout_returns_504(self):
        def script(handler, n):
            yield 'data: {"asr_result": "a"}\n\n', 0
            yield None, 1.0  # 挂住不发送

        with _serve(script) as (url, srv, _):
            client = HttpStreamClient(url, idle_timeout_ms=200)
            assert client.connect() is True
            first = client.recv()
            second = client.recv()
            client.close()

        assert first['event_type'] == EVENT_MESSAGE
        assert second['event_type'] == EVENT_ERROR
        assert second['payload']['code'] == 504
        assert 'idle timeout' in second['payload']['message']
        assert client.closed is True

    def test_max_duration_guard(self):
        def script(handler, n):
            for _ in range(100):
                yield 'data: {"n": 1}\n\n', 0.05

        with _serve(script) as (url, srv, _):
            client = HttpStreamClient(url, idle_timeout_ms=2000,
                                      max_duration_ms=300)
            assert client.connect() is True
            events = _events(client)
            client.close()

        error = [e for e in events if e['event_type'] == EVENT_ERROR][0]
        assert error['payload']['code'] == 504
        assert 'duration' in error['payload']['message']

    def test_reconnect_resumes_with_last_event_id(self):
        def script(handler, n):
            if n == 1:
                yield 'id: 1\ndata: {"asr_result": "a"}\n\n', 0
                yield None, 1.0  # 断流：不关闭连接但不再发送 → 客户端空闲超时重连
                return
            yield 'id: 2\ndata: {"asr_result": "b"}\n\n', 0

        with _serve(script) as (url, srv, _):
            client = HttpStreamClient(url, idle_timeout_ms=200, retry_ms=10,
                                      reconnect_enabled=True,
                                      max_reconnect_attempts=2)
            assert client.connect() is True
            events = _events(client, limit=10)
            client.close()

        types = [e['event_type'] for e in events]
        assert types[:2] == [EVENT_MESSAGE, EVENT_HEARTBEAT]
        assert events[1]['payload']['reconnected'] is True
        assert types[2] == EVENT_MESSAGE
        assert events[2]['payload']['asr_result'] == 'b'
        assert client.output['retry_count'] == 1
        assert srv.requests[1].get('last-event-id') == '1'

    def test_reconnect_exhausted_returns_504(self):
        def script(handler, n):
            yield None, 1.0
            return
            yield  # pragma: no cover

        with _serve(script) as (url, srv, _):
            client = HttpStreamClient(url, idle_timeout_ms=150, retry_ms=10,
                                      reconnect_enabled=True,
                                      max_reconnect_attempts=1)
            assert client.connect() is True
            events = _events(client, limit=5)
            client.close()

        types = [e['event_type'] for e in events]
        assert types[0] == EVENT_HEARTBEAT       # 第一次重连
        assert types[-1] == EVENT_ERROR          # 次数用尽 → 504
        assert events[-1]['payload']['code'] == 504
        assert len(srv.requests) == 2


class TestReworkP3:
    """A2 返工：P3-1 事件名键按配置、P3-2 线缆 retry 限幅 + 退避可中断。"""

    def test_event_name_field_written_to_configured_key(self):
        def script(handler, n):
            yield 'event: delta\ndata: {"a": 1}\n\n', 0

        with _serve(script) as (url, srv, _):
            client = HttpStreamClient(url, idle_timeout_ms=2000,
                                      event_name_field='evt')
            assert client.connect() is True
            events = _events(client)
            client.close()

        payload = [e['payload'] for e in events
                   if e['event_type'] == EVENT_MESSAGE][0]
        assert payload['evt'] == 'delta'
        # 默认键不被占用（配置了 evt 就该写 evt）
        assert 'event' not in payload
        assert client.output['event_name_field'] == 'evt'

    def test_wire_retry_cannot_exceed_config(self):
        """配置 retry_ms=10 时，服务端 `retry: 2000` 不得把退避放大到 2s。"""
        def script(handler, n):
            if n == 1:
                yield 'retry: 2000\ndata: {"a": 1}\n\n', 0
                yield None, 1.0
                return
            yield 'data: {"a": 2}\n\n', 0

        with _serve(script) as (url, srv, _):
            client = HttpStreamClient(url, idle_timeout_ms=200,
                                      retry_ms=10, reconnect_enabled=True,
                                      max_reconnect_attempts=1)
            assert client.connect() is True
            started = time.time()
            events = _events(client, limit=10)
            elapsed = time.time() - started
            client.close()

        assert EVENT_HEARTBEAT in [e['event_type'] for e in events]
        assert client.output['retry_count'] == 1
        assert client.output['retry_ms'] == 10
        assert elapsed < 1.0, f'线缆 retry 覆盖了配置：{elapsed:.2f}s'

    def test_wire_retry_clamped_to_write_side_max(self):
        def script(handler, n):
            yield 'retry: 86400000\ndata: {"a": 1}\n\n', 0

        with _serve(script) as (url, srv, _):
            client = HttpStreamClient(url, idle_timeout_ms=2000)
            assert client.connect() is True
            _events(client)
            client.close()

        # 配置退避上限 1000ms：线缆 24 小时值既不能放大配置，也不能越过写侧上限
        assert client.output['retry_ms'] == 1000
        assert client._backoff_seconds() <= 1.0

    def test_configured_retry_clamped_on_execution_side(self):
        """旧数据 / 直连 SQL 绕过写侧校验时，执行侧仍把配置限幅到 60000。"""
        with _serve(lambda h, n: iter(())) as (url, srv, _):
            client = HttpStreamClient(url, idle_timeout_ms=2000,
                                      retry_ms=86400000)
            client.close()

        assert client.output['retry_ms'] == 60000

    def test_backoff_capped_by_remaining_max_duration(self):
        with _serve(lambda h, n: iter(())) as (url, srv, _):
            client = HttpStreamClient(url, idle_timeout_ms=2000, retry_ms=5000,
                                      max_duration_ms=400,
                                      reconnect_enabled=True)
            assert client.connect() is True
            assert client._backoff_seconds() <= 0.4
            client.close()

    def test_backoff_aborted_by_control_signal(self):
        """退避等待期间命中停止 / 用例移除 → 立即收尾，不等满 5s。"""
        def script(handler, n):
            yield None, 1.0
            return

        with _serve(script) as (url, srv, _):
            client = HttpStreamClient(url, idle_timeout_ms=150, retry_ms=5000,
                                      reconnect_enabled=True,
                                      max_reconnect_attempts=2,
                                      abort_check=lambda: True)
            assert client.connect() is True
            started = time.time()
            events = _events(client, limit=5)
            elapsed = time.time() - started
            client.close()

        error = [e for e in events if e['event_type'] == EVENT_ERROR][0]
        assert 'reconnect aborted' in error['payload']['message']
        assert elapsed < 1.0

    def test_build_client_passes_event_name_field(self):
        from api_test_service.core import stream_session_executor as module

        api_config = _api_config(
            'http://127.0.0.1:1/stream',
            meta={'sse': {'event_name_field': 'evt'}})
        executor = module.StreamSessionExecutor(_ExecutorStub())
        client = executor._build_client(
            api_config, 'http://127.0.0.1:1/stream', 'GET', {}, None,
            module.StreamSessionExecutor._sse_config(api_config))
        assert client.output['event_name_field'] == 'evt'
        assert client.output['retry_ms'] == 1000


# ──────────────────────────── 事件切轮 ────────────────────────────

def _splitter(**overrides):
    meta = {'asr_mapping': 'asr_result', 'trans_mapping': 'translation_result',
            'sentence_end_mapping': 'is_sentence_end',
            'session_end_mapping': 'session_finished', 'append_mode': True}
    meta.update(overrides)
    return StreamRoundSplitter(meta)


class TestRoundSplitter:
    def test_sentence_boundary_splits_rounds(self):
        splitter = _splitter()
        closed = []
        closed += splitter.feed({'asr_result': '你'})
        closed += splitter.feed({'asr_result': '好', 'is_sentence_end': True})
        closed += splitter.feed({'asr_result': '世界'})
        closed += splitter.flush()

        assert len(closed) == 2
        assert closed[0].asr == '你好'
        assert closed[0].event_count == 2
        assert closed[0].sentence_end is True
        assert closed[1].asr == '世界'
        assert closed[1].event_count == 1

    def test_append_mode_false_keeps_latest(self):
        splitter = _splitter(append_mode=False)
        splitter.feed({'asr_result': 'a'})
        closed = splitter.feed({'asr_result': 'b', 'is_sentence_end': True})
        assert closed[0].asr == 'b'

    def test_zero_declaration_one_message_per_round(self):
        meta = {'asr_mapping': 'asr_result'}
        splitter = StreamRoundSplitter(meta)
        assert splitter.sentence_boundary_declared is False
        rounds = []
        for text in ('a', 'b', 'c'):
            rounds += splitter.feed({'asr_result': text})
        assert [r.asr for r in rounds] == ['a', 'b', 'c']
        assert splitter.flush() == []

    def test_session_end_closes_open_round(self):
        splitter = _splitter()
        splitter.feed({'asr_result': 'a'})
        closed = splitter.feed({'asr_result': 'b', 'session_finished': True})
        assert len(closed) == 1
        assert closed[0].session_end is True
        assert closed[0].asr == 'ab'

    def test_standard_code_data_wrapper(self):
        splitter = _splitter()
        closed = splitter.feed(
            {'code': 0, 'data': {'asr_result': 'x', 'is_sentence_end': True}})
        assert closed[0].asr == 'x'
        assert closed[0].biz_code is None

    def test_business_error_carried(self):
        splitter = _splitter()
        closed = splitter.feed({'code': 5001, 'msg': 'bad',
                                'data': {'is_sentence_end': True}})
        assert closed[0].biz_code == 5001
        assert closed[0].biz_msg == 'bad'

    def test_translation_fallback_text(self):
        splitter = _splitter(append_mode=False)
        closed = splitter.feed({'translation_result': 'hello',
                                'is_sentence_end': True})
        assert closed[0].trans == 'hello'
        assert closed[0].text == 'hello'


# ──────────────────────────── 执行器端到端（真实 transport） ────────────────────────────

class _ConcurrencyStub:
    def acquire(self, api_id, task_id, tc_rel_id, max_process=None):
        return True

    def release(self, api_id, task_id):
        pass


class _EngineStub:
    def __init__(self):
        self.progress_calls = 0

    def _emit_progress(self, task_id, force=False):
        self.progress_calls += 1


class _ResultProcessorStub:
    def __init__(self):
        self.calls = []
        self.failures = []

    def create_multi_round_test_result(self, **kwargs):
        self.calls.append(kwargs)
        return 'result-1'

    def update_task_case_failure(self, task_id, tc_rel_id, error_msg):
        self.failures.append(error_msg)


class _ExecutorStub:
    def __init__(self):
        self.logs = []
        self._concurrency = _ConcurrencyStub()
        self.execution_engine = _EngineStub()
        self._result_processor = _ResultProcessorStub()

    def _log(self, level='INFO', content='', **kwargs):
        self.logs.append((level, content))

    def _handle_control(self, task_id):
        pass

    def _is_case_removed(self, task_id, test_case_id):
        return False


_SSE_META = {
    'asr_mapping': 'asr_result',
    'trans_mapping': 'translation_result',
    'sentence_end_mapping': 'is_sentence_end',
    'session_end_mapping': 'session_finished',
    'append_mode': True,
    'sse': {'idle_timeout_ms': 500},
}


def _api_config(url, meta=None):
    return SimpleNamespace(
        id=5, endpoint=url, api_endpoints=[], default_max_process=1,
        meta={**_SSE_META, **(meta or {})}, max_timeout=5, vendor=None,
        protocol='sse', streaming=True, proxy_type=None, proxy_url=None)


class TestStreamSessionExecutor:
    def _run(self, monkeypatch, script, meta=None, content_type='text/event-stream',
             removed_after=None):
        from api_test_service.core import stream_session_executor as module

        evaluated = []
        monkeypatch.setattr(module, 'collect_round_eval_fields',
                            lambda output, **kw: {'answer': output.get('text', '')})
        monkeypatch.setattr(module, 'submit_case_evaluation',
                            lambda **kw: evaluated.append(kw))

        with _serve(script, content_type=content_type) as (url, srv, _):
            executor_stub = _ExecutorStub()
            if removed_after is not None:
                # 第 removed_after 次检测起视为「用例已被移除」（模拟执行中删除）
                state = {'n': 0}

                def _removed(task_id, test_case_id):
                    state['n'] += 1
                    return state['n'] >= removed_after

                executor_stub._is_case_removed = _removed
            executor = module.StreamSessionExecutor(executor_stub)
            data = {
                'task_id': 1, 'test_case_id': 2, 'case_name': 'sse-用例',
                'algorithm_type': 'translation',
                'api_configs': [_api_config(url, meta=meta)],
                'api_specific_config': {},
                'case_algorithm_params': {},
            }
            ok = executor.execute(1, 100, data, {'rounds': [], 'reference_params': {}})
        return ok, executor_stub, evaluated, srv

    def test_three_events_one_sentence_end(self, monkeypatch):
        def script(handler, n):
            yield 'data: {"asr_result": "a"}\n\n', 0
            yield 'data: {"asr_result": "b"}\n\n', 0
            yield 'data: {"asr_result": "c", "is_sentence_end": true}\n\n', 0
            yield 'data: {"asr_result": "d", "session_finished": true}\n\n', 0

        ok, stub, evaluated, srv = self._run(monkeypatch, script)
        assert ok is True  # execute() 与 WS 会话一致恒 True（终态由结果处理器回写）
        call = stub._result_processor.calls[0]
        rounds = call['aggregated']['algorithm_result']['rounds']
        assert [r['round_number'] for r in rounds] == [1, 2]
        assert rounds[0]['output'] == {'answer': 'abc'}
        assert rounds[1]['output'] == {'answer': 'd'}
        assert rounds[0]['event_count'] == 3
        assert call['success'] is True
        assert len(evaluated) == 1
        assert evaluated[0]['result_id'] == 'result-1'

    def test_no_message_events_marks_failure(self, monkeypatch):
        def script(handler, n):
            return
            yield  # pragma: no cover

        ok, stub, evaluated, srv = self._run(monkeypatch, script)
        call = stub._result_processor.calls[0]
        assert call['success'] is False
        assert '未收到任何流式消息' in call['aggregated']['error']
        assert evaluated == []
        assert stub._result_processor.failures == []  # 结果链路收尾，不算异常

    def test_stream_error_marks_failure(self, monkeypatch):
        def script(handler, n):
            yield 'data: {"asr_result": "a", "is_sentence_end": true}\n\n', 0
            yield None, 1.0
            return

        meta = {'asr_mapping': 'asr_result',
                'sentence_end_mapping': 'is_sentence_end',
                'sse': {'idle_timeout_ms': 200}}
        ok, stub, evaluated, srv = self._run(monkeypatch, script, meta=meta)
        call = stub._result_processor.calls[0]
        assert call['success'] is False
        assert call['aggregated']['algorithm_result']['rounds'][0]['success'] is True
        assert 'idle timeout' in call['aggregated']['error']
        assert evaluated == []


# ──────────────────── 终审返工（F1 / F2 / F3） ────────────────────

class TestSseConfigNullBoundary:
    """F1：`meta.sse` 显式 `null` —— 写侧放行即执行侧取默认，不得「可存不可用」。"""

    def _config(self, sse):
        return _api_config('http://127.0.0.1:1/stream', meta={'sse': sse})

    def test_explicit_null_falls_back_to_defaults(self):
        from api_test_service.core.stream_session_executor import StreamSessionExecutor

        cfg = StreamSessionExecutor._sse_config(self._config({
            'idle_timeout_ms': None,
            'retry_ms': None,
            'max_reconnect_attempts': None,
            'event_name_field': None,
            'reconnect_enabled': None,
        }))
        assert cfg['idle_timeout_ms'] == 5000  # max_timeout=5s
        assert cfg['retry_ms'] == 1000
        assert cfg['max_reconnect_attempts'] == 2
        assert cfg['event_name_field'] == 'event'
        assert cfg['reconnect_enabled'] is False

    def test_zero_values_not_swallowed_by_default(self):
        """写侧 `retry_ms` / `max_reconnect_attempts` 均允许 0，不能被 `or` 吞成默认。"""
        from api_test_service.core.stream_session_executor import StreamSessionExecutor

        cfg = StreamSessionExecutor._sse_config(self._config({
            'retry_ms': 0, 'max_reconnect_attempts': 0}))
        assert cfg['retry_ms'] == 0
        assert cfg['max_reconnect_attempts'] == 0

    def test_write_side_accepts_explicit_null(self):
        """两侧口径一致：写侧把显式 null 视为未提交（不 400），执行侧取默认。"""
        from api_test_service.application.api_crud_service import APICrudService

        assert APICrudService._validate_sse_config(
            {'sse': {'max_reconnect_attempts': None}}) is None
        assert APICrudService._validate_sse_config(
            {'sse': {'retry_ms': None, 'idle_timeout_ms': None}}) is None

    def test_execution_side_clamps_attempts(self):
        """旧数据 / 直连 SQL 绕过写侧时，执行侧按同一上限限幅。"""
        with _serve(lambda h, n: iter(())) as (url, srv, _):
            client = HttpStreamClient(url, max_reconnect_attempts=999)
            client.close()
        assert client._max_reconnect_attempts == 10


class TestCaseRemovedConvergesSilently:
    """F3：执行中删除用例 → 与 Realtime（INT-305）同口径静默收敛。

    不落结果行、不发 CASE_FAILED、不提交评估；只留一条 INFO 日志。
    """

    def test_removal_before_first_event_persists_nothing(self, monkeypatch):
        executor = TestStreamSessionExecutor()

        def script(handler, n):
            yield 'data: {"asr_result": "a"}\n\n', 0
            yield 'data: {"asr_result": "b", "is_sentence_end": true}\n\n', 0

        ok, stub, evaluated, srv = executor._run(
            monkeypatch, script, removed_after=1)
        assert ok is True  # 与 WS 会话一致：execute() 恒 True
        assert stub._result_processor.calls == []
        assert stub._result_processor.failures == []
        assert evaluated == []
        assert any('用例已被移除' in content for _, content in stub.logs)

    def test_removal_during_reconnect_backoff_persists_nothing(self, monkeypatch):
        """退避期间命中移除时传输层只报 reconnect aborted，收尾前再确认一次。"""
        executor = TestStreamSessionExecutor()

        def script(handler, n):
            yield 'data: {"asr_result": "a", "is_sentence_end": true}\n\n', 0
            yield None, 1.0  # 触发空闲超时 → 进入重连退避

        meta = {'asr_mapping': 'asr_result',
                'sentence_end_mapping': 'is_sentence_end',
                'sse': {'idle_timeout_ms': 150, 'reconnect_enabled': True,
                        'retry_ms': 3000, 'max_reconnect_attempts': 3}}
        # 前两次检测（主循环）未移除；第三次（收尾确认）命中
        ok, stub, evaluated, srv = executor._run(
            monkeypatch, script, meta=meta, removed_after=3)
        assert ok is True
        assert stub._result_processor.calls == []
        assert stub._result_processor.failures == []
        assert evaluated == []


class TestMultiRoundFailureMessage:
    """F2：流式层失败（无失败轮次）落库文案不能是「0 轮失败」。"""

    def _processor(self, monkeypatch):
        from unittest.mock import MagicMock
        import api_test_service.core.api_result_processor as proc_mod
        import shared.utils.redis_pubsub as pubsub_mod

        recorded = {}

        def _submit_result(task_id, result_data):
            recorded['result_data'] = result_data
            return 77

        acl = MagicMock()
        acl.submit_result.side_effect = _submit_result
        acl.get_task_case_by_ids.return_value = []
        monkeypatch.setattr(proc_mod, '_task_data_acl', acl)
        monkeypatch.setattr(proc_mod, 'write_result_data_file', lambda *a, **k: '')
        monkeypatch.setattr(proc_mod, 'split_result_data', lambda d: (d, False))
        monkeypatch.setattr(pubsub_mod, 'EventBus', MagicMock())

        stub = SimpleNamespace(_log=lambda **kw: None, execution_engine=None)
        return proc_mod.APIResultProcessor(stub), recorded, acl

    def test_transport_error_message_is_persisted(self, monkeypatch):
        processor, recorded, acl = self._processor(monkeypatch)
        aggregated = {
            'success': False,
            'error': '流式错误[504]: idle timeout',
            'algorithm_result': {'rounds': [
                {'round_number': 1, 'success': True}], 'round_count': 1},
            'total_latency': 0.1, 'round_count': 1, 'session_summary': {},
        }
        processor.create_multi_round_test_result(
            task_id=1, test_case_id='case-1', api_config_id=5,
            algorithm_type='translation', aggregated=aggregated, success=False)

        assert recorded['result_data']['error_message'] == '流式错误[504]: idle timeout'
        assert acl.update_task_case_status.call_args.kwargs['error_message'] == \
            '流式错误[504]: idle timeout'

    def test_ws_round_failure_message_unchanged(self, monkeypatch):
        """WS 会话聚合不带 `error` 键 → 仍回退「N 轮失败」（行为不变）。"""
        processor, recorded, acl = self._processor(monkeypatch)
        aggregated = {
            'success': False,
            'algorithm_result': {'rounds': [
                {'round_number': 1, 'success': True},
                {'round_number': 2, 'success': False}], 'round_count': 2},
            'total_latency': 0.2, 'round_count': 2, 'session_summary': {},
        }
        processor.create_multi_round_test_result(
            task_id=1, test_case_id='case-1', api_config_id=5,
            algorithm_type='voice_llm', aggregated=aggregated, success=False)

        assert recorded['result_data']['error_message'] == '1 轮失败'
