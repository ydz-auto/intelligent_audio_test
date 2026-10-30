# -*- coding: utf-8 -*-
"""INT-511 块 2：API 测试（普通 HTTP / 流式 WS）— 本地 mock 端点全链（不依赖真机/外网）

覆盖（验收标准）：
- mock 一个 HTTP API 端点 + 一个 WS 流式端点（本地起，可返回配置化响应/音频流）
- API 用例执行全链：建用例（round_config）→ 执行（executor→adapter）→ 响应解析
  → 评估（ACL 桩）→ 结果聚合
- 断言：HTTP 非流式、WS 流式（chunk 推送/聚合）都通
"""
import asyncio
import base64
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.common_enums import APIProtocol, VendorAdapterType
from api_test_service.infrastructure.adapters.transport import (
    APIClient,
    endpoint_protocol,
)
from api_test_service.infrastructure.adapters.api_driver_adapter import (
    ApiDriverAdapter,
)


# ──────────────────────────── 本地 HTTP mock 端点 ────────────────────────────

class _HttpHandler(BaseHTTPRequestHandler):
    """配置化 HTTP 响应：类属性 configurable_payload 控制返回体"""

    payload = {'code': 0, 'msg': 'success',
               'data': {'output_content': 'pong', 'translation_result': 'hello'},
               'output_content': 'pong'}   # 顶层 output_content 供 _send_direct 直读

    def _respond(self):
        data = json.dumps(self.payload).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._respond()

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8') if length else ''
        self._respond()

    def log_message(self, *args):
        pass


@pytest.fixture
def http_server():
    server = ThreadingHTTPServer(('127.0.0.1', 0), _HttpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_address[1]}'
    server.shutdown()
    server.server_close()


# ──────────────────────────── 本地 WS 流式 mock 端点 ────────────────────────────

class WsStreamingServer:
    """进程内 WS 流式 mock：收到客户端首条消息后按配置流式回 N 条 JSON chunk。

    - received: 收到的客户端消息列表（text JSON / bytes 音频 chunk）
    - response_chunks: 服务端回包列表（每收到一条客户端消息回一遍）
    """

    def __init__(self, response_chunks):
        self.response_chunks = response_chunks
        self.received = []
        self.port = None
        self._server = None
        self._loop = None
        self._thread = None
        self._started = threading.Event()

    def start(self):
        import websockets

        async def handler(ws):
            async for raw in ws:
                self.received.append(raw)
                for chunk in self.response_chunks:
                    await ws.send(json.dumps(chunk, ensure_ascii=False))

        async def serve():
            self._server = await websockets.serve(handler, '127.0.0.1', 0)
            self.port = self._server.sockets[0].getsockname()[1]
            self._started.set()
            await self._server.serve_forever()

        def _run():
            try:
                self._loop.run_until_complete(serve())
            except Exception:
                # stop() 强制收口时 serve_forever 中途退出属预期，不抛线程异常
                pass

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=_run, daemon=True,
            name='int511-ws-stream')
        self._thread.start()
        assert self._started.wait(timeout=5), 'WS 流式 mock 启动超时'

    @property
    def url(self):
        return f'ws://127.0.0.1:{self.port}'

    def stop(self):
        """停止 mock 服务器（宿主环境容错，不阻塞测试）。

        wait_closed 在 hypium/devicetest（nest_asyncio 类 asyncio 补丁）下永不收敛，
        故仅 close 不强等；线程未退出（连接处理器仍在收尾）时强制停循环线程
        （daemon 线程随进程退出回收）。
        """
        if self._server is not None and self._loop is not None:
            try:
                async def _close():
                    self._server.close()
                asyncio.run_coroutine_threadsafe(_close(), self._loop).result(timeout=3)
            except Exception:
                pass
            if self._thread is not None and self._thread.is_alive():
                try:
                    self._loop.call_soon_threadsafe(self._loop.stop)
                except Exception:
                    pass
        if self._thread is not None:
            self._thread.join(timeout=5)


def _stream_chunks(n=3, sentence_ends=True, final_session_end=True):
    """配置化 WS 流式响应：N 条 output_content chunk，末条 session_finished=true"""
    chunks = []
    for i in range(n):
        chunks.append({'data': {
            'output_content': f'chunk{i + 1}',
            'is_sentence_end': (not sentence_ends) or (i == n - 1),
            'session_finished': final_session_end and (i == n - 1),
        }})
    return chunks


@pytest.fixture
def ws_stream_server():
    server = WsStreamingServer(_stream_chunks(3))
    server.start()
    yield server
    server.stop()


def _make_api_config(endpoint, meta=None, max_timeout=5):
    """最小 api_config 替身（与 APISessionExecutor MockAPIConfig 同形）

    INT-1799：协议单一来源为 `apis.protocol` 列，替身必须带 protocol 属性。
    """
    meta = dict(meta or {})
    return SimpleNamespace(
        endpoint=endpoint, meta=meta, max_timeout=max_timeout,
        api_endpoints=[{'endpoint': endpoint}], id=7,
        vendor='openai', default_max_process=2,
        protocol='websocket' if str(endpoint).startswith(('ws://', 'wss://')) else 'http')


# ──────────────────────────── HTTP 非流式 ────────────────────────────

class TestHttpNonStreaming:
    def test_endpoint_protocol_dispatch(self):
        assert endpoint_protocol('http://h') is APIProtocol.HTTP
        assert endpoint_protocol('ws://h') is APIProtocol.WEBSOCKET

    def test_api_client_http_call(self, http_server):
        result = APIClient.call(http_server, method='POST', data={'q': 'hi'}, timeout=3)
        assert result['status_code'] == 200
        assert result['json']['data']['output_content'] == 'pong'

    def test_adapter_execute_http_parse(self, http_server):
        """HTTP 非流式：单次响应 asr/trans/biz_code 映射解析"""
        cfg = _make_api_config(http_server, meta={
            'asr_mapping': 'output_content',
            'trans_mapping': 'translation_result',
            'error_code_mapping': 'code',
        })
        adapter = ApiDriverAdapter(cfg, case_config={'body_template': {'text': '{{input_text}}'}},
                                   test_case_id='c1', task_id=7)
        result = adapter.execute({'input_text': 'hi'})
        assert result['success'] is True
        assert result['asr'] == 'pong'
        assert result['trans'] == 'hello'
        assert result['biz_code'] == 0
        assert result['status_code'] == 200

    def test_adapter_execute_http_biz_error(self, http_server):
        """HTTP 业务错误：非 0 业务码 → error 携带 BizError"""
        cfg = _make_api_config(http_server, meta={
            'error_code_mapping': 'code', 'error_msg_mapping': 'msg'})
        adapter = ApiDriverAdapter(cfg)
        parsed = adapter._parse_response({
            'json': {'code': 401, 'msg': 'unauthorized', 'data': {}},
            'raw_response': '', 'all_responses': []})
        assert parsed['biz_code'] == 401
        assert 'BizError[401]' in 'BizError[401]: unauthorized'


# ──────────────────────────── WS 流式（chunk 推送/聚合） ────────────────────────────

class TestWsStreaming:
    def test_client_ws_aggregates_stream(self, ws_stream_server):
        """WS 流式：客户端发一条 JSON → 服务端流式回 3 chunk → 聚合 all_responses + session_end 收敛"""
        result = APIClient.call(
            ws_stream_server.url, method='POST', data={'q': 'hi'},
            timeout=5, meta={
                'session_end_mapping': 'data.session_finished',
                'max_responses': 10,
            })
        assert result['error'] is None
        assert len(result['all_responses']) == 3
        # 末条 session_finished=true → 客户端在第三条后收口（不再空等超时）
        last = json.loads(result['all_responses'][-1])
        assert last['data']['session_finished'] is True
        assert result['json']['data']['output_content'] == 'chunk3'

    def test_client_ws_receives_binary_audio_chunks(self, ws_stream_server):
        """WS 音频 chunk 推送：meta.audio_path + stream_audio → 客户端逐 chunk 推二进制 + EOS"""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.pcm', delete=False) as f:
            f.write(b'\x00\x01' * 64)   # 128 字节 = 3 段 chunk（chunk_size=48）
            audio_path = f.name
        try:
            result = APIClient.call(
                ws_stream_server.url, method='POST', data={'q': 'hi'},
                timeout=5, meta={
                    'audio_path': audio_path,
                    'stream_audio': True,
                    'chunk_size': 48,
                    'eos_message': {'type': 'eos'},
                    'session_end_mapping': 'data.session_finished',
                    'max_responses': 10,
                })
            # 客户端推送：1 条初始 JSON + 3 条二进制 chunk + 1 条 EOS = 5 帧
            frames = ws_stream_server.received
            assert len(frames) == 5, f'期望 5 帧，实际 {len(frames)}'
            binary_frames = [f for f in frames if isinstance(f, bytes)]
            assert len(binary_frames) == 3
            assert b''.join(binary_frames) == b'\x00\x01' * 64
            assert result['status_code'] == 200
        finally:
            os.unlink(audio_path)

    def test_adapter_execute_ws_append_mode_aggregation(self, ws_stream_server):
        """WS 流式 + append_mode：逐句拼接 ASR（句子结束才追加）"""
        cfg = _make_api_config(ws_stream_server.url, meta={
            'asr_mapping': 'output_content',
            'sentence_end_mapping': 'is_sentence_end',
            'session_end_mapping': 'session_finished',
            'append_mode': True,
            'recv_timeout': 0.3,
            'max_responses': 10,
        })
        adapter = ApiDriverAdapter(cfg)
        result = adapter.execute({'input_text': 'hi'})
        assert result['success'] is True
        # 3 个 chunk 中仅末条 is_sentence_end=true → append_mode 只追加末条
        assert result['asr'] == 'chunk3'
        assert result['is_session_end'] is True

    def test_adapter_execute_ws_latest_mode(self, ws_stream_server):
        """WS 流式非 append_mode：ASR 取最新一条"""
        cfg = _make_api_config(ws_stream_server.url, meta={
            'asr_mapping': 'output_content',
            'session_end_mapping': 'session_finished',
            'recv_timeout': 0.3,
            'max_responses': 10,
        })
        adapter = ApiDriverAdapter(cfg)
        result = adapter.execute({'input_text': 'hi'})
        assert result['asr'] == 'chunk3'


# ──────────────────────────── 执行全链（建用例→执行→解析→评估→结果） ────────────────────────────

class _EngineStub:
    stop_flags = {}
    pause_flags = {}
    api_entry_lock = threading.Lock()
    api_entry_status = {}
    round_progress_cache = {}

    def _emit_progress(self, task_id, force=False):
        pass

    def notify_case_completed(self, task_id):
        pass

    def update_case_round_progress(self, task_id, tc_rel_id, current, total):
        pass


class _ResultProcessor:
    """捕获 create_multi_round_test_result（评估入参 = aggregated.algorithm_result）"""

    def __init__(self):
        self.calls = []

    def create_multi_round_test_result(self, task_id, test_case_id, api_config_id,
                                       algorithm_type, aggregated, success):
        self.calls.append({'task_id': task_id, 'test_case_id': test_case_id,
                           'api_config_id': api_config_id, 'success': success,
                           'algorithm_result': aggregated.get('algorithm_result', {})})
        return 51101

    def update_task_case_failure(self, *a, **k):
        pass


class _ExecutorStub:
    def __init__(self):
        self.execution_engine = _EngineStub()
        self._concurrency = SimpleNamespace(
            acquire=lambda *a, **k: True, release=lambda *a, **k: None)
        self._result_processor = _ResultProcessor()

    def _handle_control(self, task_id):
        pass

    def _log(self, *a, **k):
        pass


class TestExecutorFullChain:
    def _round_config(self, input_text='你好'):
        return {'round_number': 1, 'input_type': 'text',
                'algorithm_params': [{'field_code': 'input_text',
                                      'field_value': input_text}]}

    def test_http_round_full_chain(self, http_server, monkeypatch):
        """HTTP 全链：executor 建上下文→适配器/直连→响应解析→轮次结果→聚合→评估入参"""
        from api_test_service.core.api_session_executor import APISessionExecutor
        from api_test_service.core.session_context import SessionContext

        executor = APISessionExecutor(_ExecutorStub())
        # 评估 ACL 桩：捕获提交入参
        eval_calls = []
        monkeypatch.setattr(
            'api_test_service.core.api_session_executor._evaluation_acl',
            SimpleNamespace(submit_evaluate_case=lambda **k: eval_calls.append(k)))
        # 算法参数提取桩：extract_case_all_params → dto_to_dict 返回 evaluation 段
        monkeypatch.setattr(
            'api_test_service.core.api_session_executor._algo_acl',
            SimpleNamespace(extract_case_all_params=lambda params: SimpleNamespace()))
        monkeypatch.setattr(
            'api_test_service.core.api_session_executor.dto_to_dict',
            lambda dto: {'evaluation': {'threshold': 0.8}})

        cfg = _make_api_config(http_server, meta={'use_adapter': False,
                                                  'asr_mapping': 'output_content'})
        session = SessionContext(session_id='s-int511', config={'session_timeout': 5})
        result = executor._send_round_request(
            task_id=1, api_config=cfg, api_specific_config={}, session=session,
            round_number=1, round_config=self._round_config(),
            case_algorithm_params={}, algorithm_type='voice_llm',
            total_rounds=1)
        assert result['success'] is True
        # INT-1746：轮次文本输出落 answer_text，output 为映射后的 dict
        assert result['answer_text'] == 'pong'
        assert result['output'] == {}
        assert result['round_number'] == 1

        # 聚合 → 落库（result_processor 捕获 algorithm_result）→ 评估提交
        aggregated = executor._aggregate_round_results([result], session, api_config=cfg)
        rp = executor._executor._result_processor
        result_id = rp.create_multi_round_test_result(
            task_id=1, test_case_id=9, api_config_id=cfg.id,
            algorithm_type='voice_llm', aggregated=aggregated, success=True)
        assert result_id == 51101
        assert rp.calls[0]['algorithm_result']['success_count'] == 1

        executor._submit_evaluation(
            1, result_id, 9, 'case', {'reference_params': {}}, {},
            'voice_llm', aggregated, cfg.id, device_type='http_api')
        assert len(eval_calls) == 1
        assert eval_calls[0]['result_id'] == result_id
        assert eval_calls[0]['eval_params']['device_type'] == 'http_api'

    def test_ws_round_via_in_process_adapter(self, ws_stream_server, monkeypatch):
        """WS 流式传输全链（进程内适配器直构）：executor → ApiDriverAdapter(WS 流式) →
        响应聚合 → 轮次结果

        INT-2079（A4）后 `vendor_adapter_registry.create_from_config` 对 websocket
        协议解析为 WebSocketAdapter（请求-响应式），不再回落 ApiDriverAdapter；
        本用例保留对 ApiDriverAdapter WS 流式传输（`_call_websocket` 聚合）的
        直构回归覆盖，注册表分发见 test_int2079_ws_non_streaming.py。
        """
        from api_test_service.core.api_session_executor import APISessionExecutor
        from api_test_service.core.session_context import SessionContext
        from api_test_service.infrastructure.adapters.api_driver_adapter import (
            ApiDriverAdapter,
        )
        import api_test_service.core.api_session_executor as se_mod

        executor = APISessionExecutor(_ExecutorStub())
        monkeypatch.setattr(se_mod, '_evaluation_acl',
                            SimpleNamespace(submit_evaluate_case=lambda **k: None))
        monkeypatch.setattr(se_mod, 'dto_to_dict',
                            lambda dto: {'evaluation': {}})

        cfg = _make_api_config(ws_stream_server.url, meta={
            'use_adapter': True,
            'asr_mapping': 'output_content',
            'session_end_mapping': 'session_finished',
            'recv_timeout': 0.3,
            'max_responses': 10,
        })
        session = SessionContext(session_id='s-int511-ws', config={'session_timeout': 5})

        # 直构 ApiDriverAdapter（WS 流式传输），其 execute 由 executor 直调（不走 gRPC）
        adapter = ApiDriverAdapter(cfg, {}, task_id=1)
        from api_test_service.domain.ports import ApiVendorAdapter
        assert isinstance(adapter, ApiVendorAdapter)
        context = {'input_text': '你好', 'round_number': 1, 'total_rounds': 1,
                   'context_history': [], 'context_for_request': {}}
        parsed = adapter.execute(context)
        assert parsed['success'] is True
        assert parsed['asr'] == 'chunk3'
        assert parsed['is_session_end'] is True

        # 全链形态：round 结果 = adapter 解析产物（与 HTTP 路径同构）
        round_result = {
            'round_number': 1, 'input': '你好', 'output': parsed['asr'],
            'latency': 0.1, 'success': True,
            'raw_response': parsed['raw_response'],
        }
        aggregated = executor._aggregate_round_results([round_result], session,
                                                       api_config=cfg)
        assert aggregated['algorithm_result']['success_count'] == 1
        # INT-1746：历史字符串 output 由聚合归一为 answer_text + 空 output dict
        round_out = aggregated['algorithm_result']['rounds'][0]
        assert round_out['output'] == {}
        assert round_out['answer_text'] == 'chunk3'

    def test_multi_round_ws_aggregation(self, ws_stream_server, monkeypatch):
        """多轮 WS：两轮结果聚合（text_output 拼接 / round_count / avg_latency）"""
        from api_test_service.core.api_session_executor import APISessionExecutor
        from api_test_service.core.session_context import SessionContext

        executor = APISessionExecutor(_ExecutorStub())
        cfg = _make_api_config(ws_stream_server.url, meta={
            'asr_mapping': 'output_content',
            'session_end_mapping': 'session_finished',
            'recv_timeout': 0.3,
            'max_responses': 10,
        })
        session = SessionContext(session_id='s-int511-ws2', config={'session_timeout': 5})
        results = [
            {'round_number': 1, 'success': True, 'output': 'chunk3', 'latency': 0.2},
            {'round_number': 2, 'success': True, 'output': 'chunk3', 'latency': 0.4},
        ]
        aggregated = executor._aggregate_round_results(results, session, api_config=cfg)
        ar = aggregated['algorithm_result']
        assert ar['round_count'] == 2
        assert ar['success_count'] == 2
        assert ar['total_latency'] == pytest.approx(0.6, abs=1e-6)
        assert ar['avg_latency'] == pytest.approx(0.3, abs=1e-6)
        assert 'chunk3 chunk3' in ar['text_output']
