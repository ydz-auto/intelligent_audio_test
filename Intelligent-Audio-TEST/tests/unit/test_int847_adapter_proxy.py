# -*- coding: utf-8 -*-
"""INT-847 单测 — api_adapter_service 代理透传与四 adapter（INT-839 #2）。

覆盖（验收标准 1/2/3/4/6）：
1. 透传白名单：gRPC servicer 与 REST 双胞胎收到 vendor_config 的
   proxy_type / proxy_url 后，merge 结果显式携带并下发 adapter；不含时
   merged_config 不出现代理字段（回归）。
2. adapter URL 拼接：{proxy_type}://{proxy_url} → 完整 URL；缺字段返回
   None（不用代理）。
3. requests adapter（http/sse）：requests.post 带 proxies（含认证 URL）；
   无代理字段时 proxies 为 None（行为与改动前一致）。
4. websockets adapter（qwen/volc_ast）：websockets.connect 带 proxy
   （完整 URL）；无代理字段时不显式传 proxy（保持默认自动探测语义）。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
# http/qwen/volc adapter 模块导入期经 api_key_provider / audio_input 依赖
# OSS 两键（与 tests/unit/test_int72 同款进程级兜底）
os.environ.setdefault('OSS_ACCESS_KEY', 'ut-dummy-ak')
os.environ.setdefault('OSS_SECRET_KEY', 'ut-dummy-sk')

import pytest
from fastapi.testclient import TestClient

from api_adapter_service.utils.proxy import build_proxy_url

_PROXY_HTTP = ('http', 'user:pass@10.0.0.1:8080', 'http://user:pass@10.0.0.1:8080')
_PROXY_SOCKS5 = ('socks5', 'user:pass@10.0.0.1:1080', 'socks5://user:pass@10.0.0.1:1080')


# ── adapter URL 拼接 ─────────────────────────────────────────────

class TestBuildProxyUrl:
    def test_http_full_url(self):
        assert build_proxy_url('http', 'user:pass@10.0.0.1:8080') == \
            'http://user:pass@10.0.0.1:8080'

    def test_socks5_full_url(self):
        assert build_proxy_url('socks5', 'user:pass@10.0.0.1:1080') == \
            'socks5://user:pass@10.0.0.1:1080'

    def test_socks5h_full_url(self):
        assert build_proxy_url('socks5h', 'user:pass@10.0.0.1:1080') == \
            'socks5h://user:pass@10.0.0.1:1080'

    def test_missing_either_returns_none(self):
        assert build_proxy_url('http', '') is None
        assert build_proxy_url('', 'user:pass@h:1') is None
        assert build_proxy_url(None, 'user:pass@h:1') is None
        assert build_proxy_url('http', None) is None
        assert build_proxy_url(None, None) is None

    def test_adapters_expose_proxy_url(self):
        """四个 adapter 均从 vendor_config 拼出 self.proxy_url（基类统一）。"""
        from api_adapter_service.adapters.http_adapter import HttpAdapter
        from api_adapter_service.adapters.sse_adapter import SseAdapter
        from api_adapter_service.adapters.qwen_adapter import QwenAdapter
        from api_adapter_service.adapters.volc_ast_adapter import VolcAstAdapter

        for cls in (HttpAdapter, SseAdapter, QwenAdapter, VolcAstAdapter):
            adapter = cls({
                'base_url': 'http://api.example.com',
                'ws_url': 'wss://ast.example.com',
                'proxy_type': 'http',
                'proxy_url': 'user:pass@10.0.0.1:8080',
            })
            assert adapter.proxy_url == 'http://user:pass@10.0.0.1:8080'
        # 无代理字段 → None（不用代理）
        assert HttpAdapter({'base_url': 'http://x'}).proxy_url is None
        assert QwenAdapter({'api_url': 'wss://x'}).proxy_url is None


# ── 透传白名单 merge ─────────────────────────────────────────────

class _FakeAdapter:
    """记录构造期 vendor_config 的假 adapter，返回固定成功结果。"""

    def __init__(self, vendor_config: dict):
        self.vendor_config = vendor_config

    def send_request(self, **kwargs):
        return {
            'asr_text': 'ok',
            'trans_text': 'ok',
            'output': 'ok',
            'raw_response': {},
            'latency': 0.1,
        }


class _CaptureFactory:
    """假工厂：捕获 get_adapter 收到的 merged_config。"""

    def __init__(self, captured: dict):
        self._captured = captured

    def get_adapter(self, vendor, merged_config, is_dialog=False):
        self._captured['config'] = merged_config
        return _FakeAdapter(merged_config)


def _rest_client():
    from api_adapter_service.app import create_app
    return TestClient(create_app())


class TestWhitelistMergeRest:
    def test_rest_forwards_proxy_fields(self, monkeypatch):
        from api_adapter_service.app import create_app
        from api_adapter_service.routes import api as routes_api

        captured = {}
        monkeypatch.setattr(routes_api, 'api_adapter_factory',
                            _CaptureFactory(captured))
        resp = _rest_client().post('/api/v1/tasks', json={
            'session_id': 'int847-rest-proxy',
            'round': 0,
            'total_rounds': 1,
            'task_type': 'voice_llm',
            'vendor': 'mock',
            'input': {'type': 'text', 'text': 'hi'},
            'vendor_config': {
                'api_url': 'http://api.example.com',
                'proxy_type': _PROXY_HTTP[0],
                'proxy_url': _PROXY_HTTP[1],
            },
        })
        assert resp.status_code == 200
        assert resp.json()['code'] == 0
        merged = captured['config']
        assert merged['proxy_type'] == 'http'
        assert merged['proxy_url'] == 'user:pass@10.0.0.1:8080'
        assert merged['base_url'] == 'http://api.example.com'

    def test_rest_no_proxy_regression(self, monkeypatch):
        from api_adapter_service.app import create_app
        from api_adapter_service.routes import api as routes_api

        captured = {}
        monkeypatch.setattr(routes_api, 'api_adapter_factory',
                            _CaptureFactory(captured))
        resp = _rest_client().post('/api/v1/tasks', json={
            'session_id': 'int847-rest-noproxy',
            'round': 0,
            'total_rounds': 1,
            'task_type': 'voice_llm',
            'vendor': 'mock',
            'input': {'type': 'text', 'text': 'hi'},
            'vendor_config': {'api_url': 'http://api.example.com'},
        })
        assert resp.status_code == 200
        merged = captured['config']
        assert 'proxy_type' not in merged
        assert 'proxy_url' not in merged


class TestWhitelistMergeGrpc:
    def _send_round(self, monkeypatch, vendor_config: dict):
        from api_adapter_service.interfaces.grpc.servicers import (
            AdapterServiceServicer)
        from shared.proto import adapter_service_pb2 as adapter_pb

        captured = {}
        monkeypatch.setattr(
            'api_adapter_service.interfaces.grpc.servicers.api_adapter_factory',
            _CaptureFactory(captured))
        servicer = AdapterServiceServicer()
        resp = servicer.SendRound(adapter_pb.SendRoundRequest(
            session_id='int847-grpc-proxy',
            round=0,
            total_rounds=1,
            task_type='voice_llm',
            vendor='mock',
            input_type='text',
            input_data='hi',
            context='[]',
            context_for_request='[]',
            algorithm_params='[]',
            case_algorithm_params='{}',
            vendor_config=json.dumps(vendor_config),
        ))
        return resp, captured

    def test_grpc_forwards_proxy_fields(self, monkeypatch):
        resp, captured = self._send_round(monkeypatch, {
            'api_url': 'http://api.example.com',
            'proxy_type': _PROXY_SOCKS5[0],
            'proxy_url': _PROXY_SOCKS5[1],
        })
        assert resp.success is True, resp.message
        merged = captured['config']
        assert merged['proxy_type'] == 'socks5'
        assert merged['proxy_url'] == 'user:pass@10.0.0.1:1080'
        assert merged['base_url'] == 'http://api.example.com'

    def test_grpc_no_proxy_regression(self, monkeypatch):
        resp, captured = self._send_round(monkeypatch, {
            'api_url': 'http://api.example.com',
        })
        assert resp.success is True, resp.message
        merged = captured['config']
        assert 'proxy_type' not in merged
        assert 'proxy_url' not in merged


class TestWhitelistMergeDddHandler:
    """DDD 双胞胎（/api/adapter/tasks → CreateDialogTaskHandler）同款白名单。"""

    def _handle(self, monkeypatch, vendor_config: dict):
        from api_adapter_service.application.commands.dialog_commands import (
            CreateDialogTaskCommand)
        from api_adapter_service.application.commands.handlers import (
            CreateDialogTaskHandler)

        captured = {}
        monkeypatch.setattr(
            'api_adapter_service.application.commands.handlers.api_adapter_factory',
            _CaptureFactory(captured))
        cmd = CreateDialogTaskCommand.from_request({
            'session_id': 'int847-ddd-proxy',
            'round': 0,
            'total_rounds': 1,
            'task_type': 'voice_llm',
            'vendor': 'mock',
            'input': {'type': 'text', 'text': 'hi'},
            'vendor_config': vendor_config,
        })
        result = CreateDialogTaskHandler().handle(cmd)
        return result, captured

    def test_ddd_handler_forwards_proxy_fields(self, monkeypatch):
        result, captured = self._handle(monkeypatch, {
            'api_url': 'http://api.example.com',
            'proxy_type': _PROXY_HTTP[0],
            'proxy_url': _PROXY_HTTP[1],
        })
        assert result['code'] == 0
        merged = captured['config']
        assert merged['proxy_type'] == 'http'
        assert merged['proxy_url'] == 'user:pass@10.0.0.1:8080'

    def test_ddd_handler_no_proxy_regression(self, monkeypatch):
        result, captured = self._handle(monkeypatch, {
            'api_url': 'http://api.example.com',
        })
        assert result['code'] == 0
        merged = captured['config']
        assert 'proxy_type' not in merged
        assert 'proxy_url' not in merged


# ── requests adapter proxies 注入 ─────────────────────────────────

class _FakeJsonResp:
    def raise_for_status(self):
        pass

    def json(self):
        return {'asr_text': 'hello', 'trans_text': 'hi'}


class _FakeSseResp:
    def raise_for_status(self):
        pass

    def iter_lines(self):
        return [
            b'data: {"choices": [{"delta": {"content": "hi"}}]}',
            b'data: [DONE]',
        ]


class TestRequestsProxyInjection:
    def test_http_adapter_post_uses_proxy(self, monkeypatch):
        import api_adapter_service.adapters.http_adapter as http_mod

        captured = {}

        def _fake_post(*args, **kwargs):
            captured['kwargs'] = kwargs
            return _FakeJsonResp()

        monkeypatch.setattr(http_mod.requests, 'post', _fake_post)
        adapter = http_mod.HttpAdapter({
            'base_url': 'http://api.example.com',
            'timeout': 5,
            'proxy_type': _PROXY_HTTP[0],
            'proxy_url': _PROXY_HTTP[1],
        })
        result = adapter.send_request(
            task_id='t1', session_id='s1', input_type='text', input_data='hi')
        assert result['asr_text'] == 'hello'
        assert captured['kwargs']['proxies'] == {
            'http': 'http://user:pass@10.0.0.1:8080',
            'https': 'http://user:pass@10.0.0.1:8080',
        }

    def test_http_adapter_no_proxy_regression(self, monkeypatch):
        import api_adapter_service.adapters.http_adapter as http_mod

        captured = {}

        def _fake_post(*args, **kwargs):
            captured['kwargs'] = kwargs
            return _FakeJsonResp()

        monkeypatch.setattr(http_mod.requests, 'post', _fake_post)
        adapter = http_mod.HttpAdapter({
            'base_url': 'http://api.example.com', 'timeout': 5})
        adapter.send_request(
            task_id='t1', session_id='s1', input_type='text', input_data='hi')
        # 无代理字段 → proxies=None（requests 语义等同未传，行为回归）
        assert captured['kwargs']['proxies'] is None

    def test_sse_adapter_post_uses_proxy(self, monkeypatch):
        import api_adapter_service.adapters.sse_adapter as sse_mod

        captured = {}

        def _fake_post(*args, **kwargs):
            captured['kwargs'] = kwargs
            return _FakeSseResp()

        monkeypatch.setattr(sse_mod.requests, 'post', _fake_post)
        adapter = sse_mod.SseAdapter({
            'base_url': 'http://api.example.com',
            'api_key': 'test-key',
            'proxy_type': _PROXY_HTTP[0],
            'proxy_url': _PROXY_HTTP[1],
        })
        result = adapter.send_request(
            task_id='t1', session_id='s1', input_type='text', input_data='hi')
        assert result['asr_text'] == 'hi'
        assert captured['kwargs']['proxies'] == {
            'http': 'http://user:pass@10.0.0.1:8080',
            'https': 'http://user:pass@10.0.0.1:8080',
        }

    def test_sse_adapter_no_proxy_regression(self, monkeypatch):
        import api_adapter_service.adapters.sse_adapter as sse_mod

        captured = {}

        def _fake_post(*args, **kwargs):
            captured['kwargs'] = kwargs
            return _FakeSseResp()

        monkeypatch.setattr(sse_mod.requests, 'post', _fake_post)
        adapter = sse_mod.SseAdapter({
            'base_url': 'http://api.example.com', 'api_key': 'test-key'})
        adapter.send_request(
            task_id='t1', session_id='s1', input_type='text', input_data='hi')
        assert captured['kwargs']['proxies'] is None


# ── websockets adapter proxy 注入 ─────────────────────────────────

def _raise_connect(captured):
    def _fake_connect(*args, **kwargs):
        captured['kwargs'] = kwargs
        raise RuntimeError('proxy connect boom')
    return _fake_connect


class TestWebsocketsProxyInjection:
    def test_qwen_adapter_connect_uses_proxy(self, monkeypatch):
        import api_adapter_service.adapters.qwen_adapter as qwen_mod
        import websockets

        captured = {}
        monkeypatch.setattr(qwen_mod.websockets, 'connect',
                            _raise_connect(captured))
        monkeypatch.setattr(qwen_mod, 'resolve_audio_bytes',
                            lambda src: b'\x00' * 3200)
        adapter = qwen_mod.QwenAdapter({
            'timeout': 5,
            'proxy_type': _PROXY_SOCKS5[0],
            'proxy_url': _PROXY_SOCKS5[1],
        })
        result = adapter.send_request(
            task_id='t1', session_id='s1', input_type='audio',
            input_data='local://x.wav')
        # 连接失败收敛为 error 结果，且 connect 收到完整代理 URL
        assert 'error' in result['raw_response']
        assert captured['kwargs']['proxy'] == 'socks5://user:pass@10.0.0.1:1080'

    def test_qwen_adapter_no_proxy_regression(self, monkeypatch):
        import api_adapter_service.adapters.qwen_adapter as qwen_mod

        captured = {}
        monkeypatch.setattr(qwen_mod.websockets, 'connect',
                            _raise_connect(captured))
        monkeypatch.setattr(qwen_mod, 'resolve_audio_bytes',
                            lambda src: b'\x00' * 3200)
        adapter = qwen_mod.QwenAdapter({'timeout': 5})
        adapter.send_request(
            task_id='t1', session_id='s1', input_type='audio',
            input_data='local://x.wav')
        # 未配置代理 → 不显式传 proxy（保持 websockets 默认自动探测语义）
        assert 'proxy' not in captured['kwargs']

    def test_volc_adapter_connect_uses_proxy(self, monkeypatch):
        import api_adapter_service.adapters.volc_ast_adapter as volc_mod

        captured = {}
        monkeypatch.setattr(volc_mod.websockets, 'connect',
                            _raise_connect(captured))
        monkeypatch.setattr(volc_mod, 'resolve_audio_bytes',
                            lambda src: b'\x00' * 6400)
        adapter = volc_mod.VolcAstAdapter({
            'ws_url': 'wss://ast.example.com',
            'timeout': 5,
            'proxy_type': _PROXY_HTTP[0],
            'proxy_url': _PROXY_HTTP[1],
        })
        result = adapter.send_request(
            task_id='t1', session_id='s1', input_type='audio',
            input_data='local://x.wav', source_lang='zh', target_lang='en')
        assert 'error' in result['raw_response']
        assert captured['kwargs']['proxy'] == 'http://user:pass@10.0.0.1:8080'

    def test_volc_adapter_no_proxy_regression(self, monkeypatch):
        import api_adapter_service.adapters.volc_ast_adapter as volc_mod

        captured = {}
        monkeypatch.setattr(volc_mod.websockets, 'connect',
                            _raise_connect(captured))
        monkeypatch.setattr(volc_mod, 'resolve_audio_bytes',
                            lambda src: b'\x00' * 6400)
        adapter = volc_mod.VolcAstAdapter({
            'ws_url': 'wss://ast.example.com', 'timeout': 5})
        adapter.send_request(
            task_id='t1', session_id='s1', input_type='audio',
            input_data='local://x.wav', source_lang='zh', target_lang='en')
        assert 'proxy' not in captured['kwargs']
