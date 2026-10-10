# -*- coding: utf-8 -*-
"""INT-70 OpenAI 密钥链与日志脱敏单测。

设计依据：API测试功能设计文档 §3.7/§8.1、04_类设计 §3.2.2、
01_UseCase总览 UC-0901 扩展流程 3a。

覆盖：
- 密钥链逐级回退顺序 case_config → meta → 服务配置层 → env OPENAI_API_KEY
  （各级键名/环境变量名可配置）
- 消费点解析：adapter 服务密钥提供者、Sse/Qwen/Http 适配器、
  ApiDriverAdapter Bearer 注入、RealtimeSessionExecutor WS 握手头
- 日志统一脱敏：mask_text / mask_mapping / log_and_emit 控制台出口
"""
import logging
import os
import tempfile

import pytest

# 共享配置在导入期校验必填环境变量（adapter 模块导入即触发 logger →
# DatabaseLogHandler → BaseConfig）；本文件不触库，仅满足导入校验
os.environ.setdefault(
    'DATABASE_URL',
    'sqlite:///' + tempfile.mkdtemp(prefix='int70_chain_') + '/chain.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')


# ── 密钥链解析顺序 ────────────────────────────────────────────

from shared.utils.api_key_provider import (
    ApiKeyChainResolver,
    resolver_from_config,
)


@pytest.fixture(autouse=True)
def _no_openai_env(monkeypatch):
    """隔离宿主机环境变量，保证链序断言确定性"""
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('MY_PLATFORM_KEY', raising=False)


def test_chain_case_config_wins():
    resolver = ApiKeyChainResolver()
    assert resolver.resolve(
        case_config={'api_key': 'sk-case'},
        meta={'api_key': 'sk-meta'},
        service_candidates=['sk-yml']) == 'sk-case'


def test_chain_fallback_meta():
    resolver = ApiKeyChainResolver()
    assert resolver.resolve(
        case_config={'api_key': ''},
        meta={'api_key': 'sk-meta'},
        service_candidates=['sk-yml']) == 'sk-meta'


def test_chain_fallback_service_config():
    resolver = ApiKeyChainResolver()
    assert resolver.resolve(
        case_config=None, meta={},
        service_candidates=['sk-yml']) == 'sk-yml'


def test_chain_fallback_env(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-env-0001')
    resolver = ApiKeyChainResolver()
    assert resolver.resolve() == 'sk-env-0001'


def test_chain_all_empty_returns_empty():
    assert ApiKeyChainResolver().resolve() == ''


def test_chain_env_key_configurable(monkeypatch):
    monkeypatch.setenv('MY_PLATFORM_KEY', 'sk-alt-0002')
    resolver = ApiKeyChainResolver(env_key='MY_PLATFORM_KEY')
    assert resolver.resolve() == 'sk-alt-0002'


def test_chain_level_keys_configurable():
    resolver = ApiKeyChainResolver(case_key='secret', meta_key='token')
    assert resolver.resolve(
        case_config={'secret': 'sk-c'},
        meta={'token': 'sk-m'}) == 'sk-c'
    assert resolver.resolve(meta={'token': 'sk-m'}) == 'sk-m'


def test_resolver_from_config():
    resolver = resolver_from_config(
        lambda section, key, default=None: {
            'case_config_key': 'k1', 'meta_key': 'k2',
            'env_key': 'MY_PLATFORM_KEY'}.get(key, default))
    assert resolver.case_key == 'k1'
    assert resolver.meta_key == 'k2'
    assert resolver.env_key == 'MY_PLATFORM_KEY'


# ── adapter 服务密钥提供者（Infrastructure 层）────────────────

from api_adapter_service.infrastructure.secrets.api_key_provider import (
    ApiKeyProvider,
)


class _FakeConfig:
    def __init__(self, data=None):
        self._data = data or {}

    def get(self, path, default=None):
        node = self._data
        for part in path.split('.'):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node


def test_provider_case_candidate_wins():
    provider = ApiKeyProvider(config=_FakeConfig())
    vendor_config = {
        'api_key': 'sk-yml',
        'api_key_candidates': {'case_config': 'sk-case', 'meta': 'sk-meta'},
    }
    assert provider.resolve(vendor_config) == 'sk-case'


def test_provider_meta_candidate():
    provider = ApiKeyProvider(config=_FakeConfig())
    vendor_config = {
        'api_key': 'sk-yml',
        'api_key_candidates': {'meta': 'sk-meta'},
    }
    assert provider.resolve(vendor_config) == 'sk-meta'


def test_provider_service_config_layer():
    provider = ApiKeyProvider(config=_FakeConfig())
    assert provider.resolve({'api_key': 'sk-yml'}) == 'sk-yml'


def test_provider_env_fallback(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-env-0003')
    provider = ApiKeyProvider(config=_FakeConfig())
    assert provider.resolve({}) == 'sk-env-0003'


def test_provider_env_key_via_chain_config(monkeypatch):
    monkeypatch.setenv('MY_PLATFORM_KEY', 'sk-env-0004')
    provider = ApiKeyProvider(config=_FakeConfig({
        'secrets': {'api_key_chain': {'env_key': 'MY_PLATFORM_KEY'}}}))
    assert provider.resolve({}) == 'sk-env-0004'


# ── 消费点：Sse / Qwen / Http 适配器 ──────────────────────────

from api_adapter_service.adapters.sse_adapter import SseAdapter
from api_adapter_service.adapters.qwen_adapter import QwenAdapter
from api_adapter_service.adapters.http_adapter import HttpAdapter


def test_sse_adapter_resolves_chain():
    adapter = SseAdapter({'api_key_candidates': {'case_config': 'sk-case'}})
    assert adapter.api_key == 'sk-case'


def test_sse_adapter_yml_layer_fallback():
    adapter = SseAdapter({'api_key': 'sk-yml'})
    assert adapter.api_key == 'sk-yml'


def test_qwen_adapter_resolves_chain():
    adapter = QwenAdapter({'api_key_candidates': {'meta': 'sk-meta'}})
    assert adapter.api_key == 'sk-meta'


def test_http_adapter_injects_bearer_from_chain():
    adapter = HttpAdapter({
        'api_key_candidates': {'case_config': 'sk-case'},
        'headers': {'Content-Type': 'application/json'},
    })
    assert adapter.headers['Authorization'] == 'Bearer sk-case'
    assert adapter.headers['Content-Type'] == 'application/json'


def test_http_adapter_explicit_authorization_wins():
    adapter = HttpAdapter({
        'api_key_candidates': {'case_config': 'sk-case'},
        'headers': {'Authorization': 'Bearer explicit'},
    })
    assert adapter.headers['Authorization'] == 'Bearer explicit'


# ── 消费点：ApiDriverAdapter（api_test_service 内置驱动）──────

from api_test_service.infrastructure.adapters.api_driver_adapter import (
    ApiDriverAdapter,
)
from types import SimpleNamespace


def _driver(api_meta, case_cfg):
    api_config = SimpleNamespace(meta=api_meta, max_timeout=30, endpoint='http://x')
    return ApiDriverAdapter(api_config, case_config=case_cfg)


def test_driver_case_level_key_injected():
    driver = _driver({}, {'api_key': 'sk-case'})
    headers, _ = driver.render_request_parts({})
    assert headers['Authorization'] == 'Bearer sk-case'


def test_driver_meta_level_key_injected():
    driver = _driver({'api_key': 'sk-meta'}, {})
    headers, _ = driver.render_request_parts({})
    assert headers['Authorization'] == 'Bearer sk-meta'


def test_driver_explicit_authorization_wins():
    driver = _driver(
        {'api_key': 'sk-meta', 'headers': {'Authorization': 'Bearer explicit'}},
        {'api_key': 'sk-case'})
    headers, _ = driver.render_request_parts({})
    assert headers['Authorization'] == 'Bearer explicit'


def test_driver_no_key_no_injection():
    driver = _driver({}, {})
    headers, _ = driver.render_request_parts({})
    assert 'Authorization' not in headers


# ── 消费点：RealtimeSessionExecutor WS 握手头 ─────────────────

from api_test_service.core.realtime_session_executor import (
    RealtimeSessionExecutor,
)


def test_realtime_ws_headers_case_level_wins():
    api_config = SimpleNamespace(meta={'api_key': 'sk-meta'})
    headers = RealtimeSessionExecutor._resolve_ws_headers(
        api_config, case_api_key='sk-case')
    assert headers['Authorization'] == 'Bearer sk-case'


def test_realtime_ws_headers_meta_fallback():
    api_config = SimpleNamespace(meta={'api_key': 'sk-meta'})
    headers = RealtimeSessionExecutor._resolve_ws_headers(api_config)
    assert headers['Authorization'] == 'Bearer sk-meta'


def test_realtime_ws_headers_env_fallback(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-env-0005')
    api_config = SimpleNamespace(meta={})
    headers = RealtimeSessionExecutor._resolve_ws_headers(api_config)
    assert headers['Authorization'] == 'Bearer sk-env-0005'


def test_realtime_ws_headers_explicit_authorization_wins():
    api_config = SimpleNamespace(meta={
        'api_key': 'sk-meta',
        'ws_headers': {'Authorization': 'Bearer explicit'},
    })
    headers = RealtimeSessionExecutor._resolve_ws_headers(api_config)
    assert headers['Authorization'] == 'Bearer explicit'


def test_realtime_ws_headers_no_key_passthrough():
    api_config = SimpleNamespace(meta={'ws_headers': {'X-Custom': 'v'}})
    headers = RealtimeSessionExecutor._resolve_ws_headers(api_config)
    assert headers == {'X-Custom': 'v'}


# ── 日志统一脱敏 ──────────────────────────────────────────────

from shared.utils.secret_mask import mask_mapping, mask_text


def test_mask_text_kv_bare_value():
    masked = mask_text('using api_key=sk-abcdef1234567890 today')
    assert 'sk-abcdef1234567890' not in masked
    assert 'api_key=****' in masked


def test_mask_text_kv_json_value():
    masked = mask_text('payload {"api_key": "sk-abcdef1234567890"} sent')
    assert 'sk-abcdef1234567890' not in masked
    assert '"api_key": "****"' in masked


def test_mask_text_bearer_token():
    # Bearer <token> 整体作为 Authorization 的值一并掩码
    masked = mask_text('Authorization: Bearer abcdef123456 accepted')
    assert 'abcdef123456' not in masked
    assert masked == 'Authorization: **** accepted'
    # 无键名上下文的游离 Bearer token 由独立规则兜底
    masked2 = mask_text('handshake uses Bearer abcdef123456 for auth')
    assert 'abcdef123456' not in masked2
    assert 'Bearer ****' in masked2


def test_mask_text_bare_openai_key():
    masked = mask_text('configured sk-abcdefghijklmnop1234 manually')
    assert 'sk-abcdefghijklmnop1234' not in masked


def test_mask_text_keeps_non_sensitive_content():
    line = 'task=t1, session=s2, latency=0.3s, model=gpt-4o'
    assert mask_text(line) == line


def test_mask_text_pure_numeric_value_kept():
    # 纯数字值视为用量统计（如 token 计数），不脱敏
    assert mask_text('api_key=12345678') == 'api_key=12345678'


def test_mask_text_idempotent():
    once = mask_text('api_key=sk-abcdef1234567890')
    assert mask_text(once) == once


def test_mask_text_non_string_passthrough():
    assert mask_text(None) is None
    assert mask_text(123) == 123
    assert mask_text('') == ''


def test_mask_mapping_recursive():
    payload = {
        'api_key': 'sk-abcdef1234567890',
        'nested': {'Authorization': 'Bearer abcdef123456', 'plain': 'v'},
        'items': [{'token': 'tok-abcdef123456'}, 'kept'],
    }
    masked = mask_mapping(payload)
    assert masked['api_key'] == '****'
    assert masked['nested']['Authorization'] == '****'
    assert masked['nested']['plain'] == 'v'
    assert masked['items'][0]['token'] == '****'
    assert masked['items'][1] == 'kept'


def test_log_and_emit_console_masked(capsys):
    from shared.utils.log_handler import log_and_emit
    log_and_emit('INFO', 'Int70Test', 'api_key=sk-abcdef1234567890',
                 enable_console_log=True)
    out = capsys.readouterr().out
    assert 'sk-abcdef1234567890' not in out
    assert '****' in out


def test_emit_business_entry_masked(monkeypatch):
    """handler.emit 分流后的落盘/推送内容同样脱敏：
    _enqueue_business_log 收到的 log_message 已掩码（业务文件/WS/DB 前置）"""
    from shared.utils.log_handler import get_db_handler

    handler = get_db_handler()
    captured = {}
    monkeypatch.setattr(
        handler, '_enqueue_business_log',
        lambda record, task_id, test_case_id, category, log_message:
        captured.update(content=log_message))

    record = logging.LogRecord(
        name='Int70Test', level=logging.INFO, pathname='', lineno=0,
        msg='api_key=sk-abcdef1234567890', args=(), exc_info=None)
    record.module = 'Int70Test'
    record.category = 'execution'
    record.task_id = 'task-int70'
    handler.emit(record)

    assert captured, 'emit 未到达业务日志入队点'
    assert 'sk-abcdef1234567890' not in captured['content']
    assert '****' in captured['content']
