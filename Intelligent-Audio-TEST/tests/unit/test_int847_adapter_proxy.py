# -*- coding: utf-8 -*-
"""INT-847 单测（INT-1169/1176 改写）— api_test_service 内嵌代理工具与 ApiDriverAdapter 代理透传。

api_adapter_service 删除后，原四个 adapter（HttpAdapter/SseAdapter/QwenAdapter/
VolcAstAdapter）的代理注入测试随服务删除；本文件改写指向内嵌等价能力：
1. 内嵌 proxy_utils（build_proxy_url / split_proxy_url / validate_proxy，
   INT-839 契约唯一落位）；
2. ApiDriverAdapter.execute_voice_llm_chat 把 api_config.proxy_type /
   proxy_url 透传给 api_client.call（INT-839 被测 API 网络代理透传）。

覆盖（INT-839 #2 保留口径）：
- adapter URL 拼接：{proxy_type}://{proxy_url} → 完整 URL；缺字段返回 None。
- 透传：execute_voice_llm_chat 收到 proxy_type / proxy_url 后转发 api_client。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'ut-dummy-ak')
os.environ.setdefault('OSS_SECRET_KEY', 'ut-dummy-sk')

from types import SimpleNamespace
from unittest import mock

from api_test_service.infrastructure.adapters.proxy_utils import (
    build_proxy_url, split_proxy_url, validate_proxy)
from api_test_service.infrastructure.adapters import api_driver_adapter as ada

_PROXY_HTTP = ('http', 'user:pass@10.0.0.1:8080', 'http://user:pass@10.0.0.1:8080')
_PROXY_SOCKS5 = ('socks5', 'user:pass@10.0.0.1:1080', 'socks5://user:pass@10.0.0.1:1080')


# ── adapter URL 拼接（内嵌 proxy_utils，INT-839 #2）────────────────

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

    def test_scheme_prefix_stripped(self):
        # INT-846：proxy_url 误带 scheme 前缀时剥去，不拼双重 scheme
        assert build_proxy_url('http', 'http://user:pass@10.0.0.1:8080') == \
            'http://user:pass@10.0.0.1:8080'


class TestSplitProxyUrl:
    def test_full_userinfo(self):
        assert split_proxy_url('user:pass@10.0.0.1:8080') == (
            '10.0.0.1', 8080, 'user', 'pass')

    def test_scheme_prefix_stripped(self):
        assert split_proxy_url('http://u:p@h:1') == ('h', 1, 'u', 'p')

    def test_empty(self):
        assert split_proxy_url('') == (None, None, None, None)
        assert split_proxy_url(None) == (None, None, None, None)

    def test_invalid_port_raises(self):
        try:
            split_proxy_url('u:p@h:abc')
            assert False, 'should raise'
        except ValueError:
            pass


class TestValidateProxy:
    def test_empty_ok(self):
        assert validate_proxy(None, None) is None
        assert validate_proxy('', '') is None

    def test_type_without_url_rejected(self):
        assert validate_proxy('http', '') is not None

    def test_unsupported_scheme_rejected(self):
        assert validate_proxy('ftp', 'u:p@10.0.0.1:9') is not None

    def test_missing_auth_rejected(self):
        assert validate_proxy('http', '10.0.0.1:8080') is not None

    def test_valid_ok(self):
        assert validate_proxy('http', 'user:pass@10.0.0.1:8080') is None


# ── ApiDriverAdapter.execute_voice_llm_chat 代理透传 ─────────────────

class TestEmbeddedAdapterProxyPassthrough:
    """execute_voice_llm_chat 把 api_config.proxy_type/proxy_url 转发 api_client.call。

    对应旧「HttpAdapter requests.post 带 proxies」契约：内嵌执行路径（voice_llm
    chat）经 api_client 统一代理注入，api_test_service 侧零丢字段。
    """

    def _run_chat(self, proxy_type=None, proxy_url=None):
        cfg = SimpleNamespace(
            meta={}, api_endpoints=[], api_url='http://api.example.com',
            proxy_type=proxy_type, proxy_url=proxy_url, max_timeout=30)
        adapter = ada.ApiDriverAdapter(cfg, case_config={})
        captured = {}

        def _fake_call(**kwargs):
            captured.update(kwargs)
            return {'status_code': 200, 'latency': 10, 'raw_response': '',
                    'json': {'asr_text': 'ok'}, 'error': None}

        with mock.patch.object(ada.api_client, 'call', _fake_call):
            adapter.execute_voice_llm_chat(
                session_id='s-1', input_type='text', input_data='hi',
                round_number=1, total_rounds=1, timeout=5)
        return captured

    def test_forwards_proxy_fields(self):
        captured = self._run_chat(_PROXY_HTTP[0], _PROXY_HTTP[1])
        assert captured['proxy_type'] == 'http'
        assert captured['proxy_url'] == 'user:pass@10.0.0.1:8080'

    def test_no_proxy_fields_when_unset(self):
        captured = self._run_chat()
        assert captured['proxy_type'] is None
        assert captured['proxy_url'] is None
