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
from datetime import datetime

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
    InMemoryRotationStateStore,
    RotationStateStore,
    endpoint_rotation_key,
    get_rotation_store,
    resolver_from_config,
)


@pytest.fixture(autouse=True)
def _no_openai_env(monkeypatch):
    """隔离宿主机环境变量，保证链序断言确定性"""
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('MY_PLATFORM_KEY', raising=False)


@pytest.fixture(autouse=True)
def _isolate_rotation_store():
    """隔离模块级共享轮换状态（每用例独立游标/冷却，防跨用例串扰）"""
    import shared.utils.api_key_provider as akp
    original = akp._rotation_store
    fresh = InMemoryRotationStateStore()
    akp._rotation_store = fresh
    # 既有实例引用绑定构造期单例：重建解析器以绑定新单例
    yield fresh
    akp._rotation_store = original


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


# ── 消费点：内嵌适配器密钥链（INT-1169/1176 迁移）─────────────
# api_adapter_service 的 ApiKeyProvider / Sse / Qwen / Http 适配器已随服务删除；
# 内嵌等价：resolver_from_config（ApiDriverAdapter._key_resolver 同源）逐级回退 +
# ApiDriverAdapter._merge_headers 的 Bearer 注入（HttpAdapter 等价能力）。

# ── INT-1177 密钥池：轮换解析 / 冷却 / 并发 / 同源（endpoint 级） ─────

def _ep(url='https://ep.example.com', keys=None):
    """端点 dict（endpoint 级密钥池挂在 api_endpoints[].api_keys）"""
    return {'endpoint': url, 'api_keys': list(keys or [])}


def _rk(api_id=1, url='https://ep.example.com'):
    """轮换状态 key = (api_id, endpoint base URL)，INT-1230 审计 D3'"""
    return endpoint_rotation_key(api_id, url)

def test_rotating_round_robin():
    resolver = ApiKeyChainResolver()
    ep = _ep(keys=['sk-a1', 'sk-b2', 'sk-c3'])
    assert resolver.resolve_rotating(rotation_key=_rk(), endpoint=ep) == 'sk-a1'
    assert resolver.resolve_rotating(rotation_key=_rk(), endpoint=ep) == 'sk-b2'
    assert resolver.resolve_rotating(rotation_key=_rk(), endpoint=ep) == 'sk-c3'
    assert resolver.resolve_rotating(rotation_key=_rk(), endpoint=ep) == 'sk-a1'


def test_rotating_case_level_single_wins():
    """case 层单值最高优先（现状不变）：配置密钥池也不轮换"""
    resolver = ApiKeyChainResolver()
    ep = _ep(keys=['sk-a1', 'sk-b2'])
    assert resolver.resolve_rotating(
        rotation_key=_rk(), endpoint=ep,
        case_config={'api_key': 'sk-case'}) == 'sk-case'
    assert resolver.resolve_rotating(
        rotation_key=_rk(), endpoint=ep,
        case_config={'api_key': 'sk-case'}) == 'sk-case'


def test_rotating_fallback_single_value():
    """无池回退单值链（meta.api_key → 服务配置层 → env），resolve() 行为不变"""
    resolver = ApiKeyChainResolver()
    assert resolver.resolve_rotating(
        rotation_key=_rk(), endpoint=None,
        meta={'api_key': 'sk-meta'}) == 'sk-meta'
    assert resolver.resolve_rotating(
        rotation_key=_rk(), endpoint=None,
        service_candidates=['sk-yml']) == 'sk-yml'
    assert resolver.resolve_rotating(rotation_key=_rk(), endpoint=None) == ''


def test_rotating_pool_only_from_endpoint_not_meta():
    """INT-1230 审计 D1'：轮换池只取自当前端点 api_keys，meta.api_keys 不参与
    （旧 meta 级口径已迁移；meta 仅作单值回退链）"""
    resolver = ApiKeyChainResolver()
    ep = _ep(keys=['sk-ep-a1'])
    # 端点无池 + meta 含 api_keys：不回退到 meta 池，走单值链（meta 无 api_key → 空）
    assert resolver.resolve_rotating(
        rotation_key=_rk(), endpoint=None,
        meta={'api_keys': ['sk-meta-a1']}) == ''
    # 端点有池：只用端点池轮换
    assert resolver.resolve_rotating(
        rotation_key=_rk(), endpoint=ep,
        meta={'api_keys': ['sk-meta-a1']}) == 'sk-ep-a1'


def test_rotating_failure_cooldown_skips_key():
    """失败降级：report_failure 置冷却后该 key 冷却期内不再选中"""
    resolver = ApiKeyChainResolver(cooldown_seconds=60)
    ep = _ep(keys=['sk-a1', 'sk-b2', 'sk-c3'])
    assert resolver.resolve_rotating(rotation_key=_rk(), endpoint=ep) == 'sk-a1'
    # sk-a1 失败置冷却：下一轮跳过，直接 sk-b2
    resolver.report_failure(_rk(), 'sk-a1')
    assert resolver.resolve_rotating(rotation_key=_rk(), endpoint=ep) == 'sk-b2'
    assert resolver.resolve_rotating(rotation_key=_rk(), endpoint=ep) == 'sk-c3'
    # sk-b2 也失败：只剩 sk-c3
    resolver.report_failure(_rk(), 'sk-b2')
    assert resolver.resolve_rotating(rotation_key=_rk(), endpoint=ep) == 'sk-c3'


def test_rotating_pool_all_cooled_returns_empty():
    """池全冷却立即失败：resolve_rotating 返回空串（调用方不注入 Authorization）"""
    resolver = ApiKeyChainResolver(cooldown_seconds=60)
    ep = _ep(keys=['sk-a1', 'sk-b2'])
    assert resolver.resolve_rotating(rotation_key=_rk(9), endpoint=ep) == 'sk-a1'
    resolver.report_failure(_rk(9), 'sk-a1')
    assert resolver.resolve_rotating(rotation_key=_rk(9), endpoint=ep) == 'sk-b2'
    resolver.report_failure(_rk(9), 'sk-b2')
    assert resolver.resolve_rotating(rotation_key=_rk(9), endpoint=ep) == ''
    assert resolver.has_available_rotating_key(_rk(9), ep) is False


def test_rotating_has_available():
    resolver = ApiKeyChainResolver()
    ep = _ep(keys=['sk-a1', 'sk-b2'])
    assert resolver.has_available_rotating_key(_rk(), ep) is True
    assert resolver.has_available_rotating_key(_rk(), _ep(keys=[])) is False
    assert resolver.has_available_rotating_key(_rk(), None) is False
    assert resolver.has_available_rotating_key(_rk(), {}) is False


def test_rotating_cooldown_expiry_restores_key():
    """冷却期过后 key 恢复可选（cooldown_seconds=0 → 立即恢复）"""
    resolver = ApiKeyChainResolver(cooldown_seconds=0)
    ep = _ep(keys=['sk-a1', 'sk-b2'])
    assert resolver.resolve_rotating(rotation_key=_rk(2), endpoint=ep) == 'sk-a1'
    resolver.report_failure(_rk(2), 'sk-a1')
    # cooldown=0：冷却立即过期，下一轮恢复可选
    assert resolver.resolve_rotating(rotation_key=_rk(2), endpoint=ep) == 'sk-b2'
    assert resolver.resolve_rotating(rotation_key=_rk(2), endpoint=ep) == 'sk-a1'


def test_rotating_shared_store_cross_resolver_same_source():
    """同一端点跨协议同源轮换：两个解析器实例（如 HTTP/Realtime 各自
    模块级 resolver）经同一共享单例，同一 (api_id, endpoint URL) 共享游标"""
    r1 = ApiKeyChainResolver()
    r2 = ApiKeyChainResolver()
    ep = _ep(keys=['sk-a1', 'sk-b2', 'sk-c3'])
    # HTTP 侧解析 → a1；Realtime 侧解析 → b2（共享游标）
    assert r1.resolve_rotating(rotation_key=_rk(5), endpoint=ep) == 'sk-a1'
    assert r2.resolve_rotating(rotation_key=_rk(5), endpoint=ep) == 'sk-b2'
    assert r1.resolve_rotating(rotation_key=_rk(5), endpoint=ep) == 'sk-c3'


def test_rotating_endpoint_independent_cursor():
    """INT-1230 审计 D3'：轮换状态按 (api_id, endpoint URL) 维度，多端点
    各用各池互不串扰；同 API 不同端点游标独立"""
    resolver = ApiKeyChainResolver()
    ep1 = _ep(url='https://ep1.example.com', keys=['sk-a1', 'sk-a2'])
    ep2 = _ep(url='https://ep2.example.com', keys=['sk-b1', 'sk-b2'])
    # 同 API 两个端点：各自独立游标
    assert resolver.resolve_rotating(rotation_key=_rk(11, 'https://ep1.example.com'), endpoint=ep1) == 'sk-a1'
    assert resolver.resolve_rotating(rotation_key=_rk(11, 'https://ep2.example.com'), endpoint=ep2) == 'sk-b1'
    assert resolver.resolve_rotating(rotation_key=_rk(11, 'https://ep1.example.com'), endpoint=ep1) == 'sk-a2'
    assert resolver.resolve_rotating(rotation_key=_rk(11, 'https://ep2.example.com'), endpoint=ep2) == 'sk-b2'
    # 不同 API 同一 URL 也独立
    assert resolver.resolve_rotating(rotation_key=_rk(12, 'https://ep1.example.com'), endpoint=ep1) == 'sk-a1'


def test_rotating_concurrency_stress():
    """并发压力：3 key × 多线程 resolve，计数均衡、无死锁、无重复分配"""
    resolver = ApiKeyChainResolver(cooldown_seconds=60)
    ep = _ep(keys=['sk-a1', 'sk-b2', 'sk-c3'])
    total = 300
    results = []
    errors = []

    def worker():
        try:
            for _ in range(total):
                results.append(resolver.resolve_rotating(
                    rotation_key=_rk(77), endpoint=ep))
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [__import__('threading').Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f'并发解析抛异常: {errors}'
    assert len(results) == total * 8, '存在死锁/丢失'
    counts = {k: results.count(k) for k in ep['api_keys']}
    # round-robin 均衡：每 key 计数偏差 ≤1
    assert max(counts.values()) - min(counts.values()) <= 1, counts
    assert len(set(results)) == 3


def test_rotating_concurrency_multi_endpoint_no_cross():
    """INT-1230 审计 D4'：多端点并发计数不错乱——两个端点各 2 key × 多线程，
    每个端点的计数独立均衡（端点间不串）"""
    resolver = ApiKeyChainResolver(cooldown_seconds=60)
    ep_a = _ep(url='https://ep-a.example.com', keys=['sk-a1', 'sk-a2'])
    ep_b = _ep(url='https://ep-b.example.com', keys=['sk-b1', 'sk-b2'])
    results_a = []
    results_b = []
    errors = []
    total = 200

    def worker_a():
        try:
            for _ in range(total):
                results_a.append(resolver.resolve_rotating(
                    rotation_key=_rk(88, 'https://ep-a.example.com'), endpoint=ep_a))
        except Exception as e:  # pragma: no cover
            errors.append(e)

    def worker_b():
        try:
            for _ in range(total):
                results_b.append(resolver.resolve_rotating(
                    rotation_key=_rk(88, 'https://ep-b.example.com'), endpoint=ep_b))
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [__import__('threading').Thread(target=worker_a)
               for _ in range(4)] + [__import__('threading').Thread(target=worker_b)
                                     for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f'并发解析抛异常: {errors}'
    assert len(results_a) == total * 4 and len(results_b) == total * 4
    counts_a = {k: results_a.count(k) for k in ep_a['api_keys']}
    counts_b = {k: results_b.count(k) for k in ep_b['api_keys']}
    assert max(counts_a.values()) - min(counts_a.values()) <= 1, counts_a
    assert max(counts_b.values()) - min(counts_b.values()) <= 1, counts_b
    assert all(k not in results_a for k in ep_b['api_keys']), '端点间串池'
    assert all(k not in results_b for k in ep_a['api_keys']), '端点间串池'


def test_rotating_store_port_injectable():
    """RotationStateStore 端口抽象：消费面经端口引用，可换实现（Redis 后续）"""
    from shared.utils import api_key_provider as akp

    class _FixedStore(RotationStateStore):
        def __init__(self):
            self.lock = __import__('threading').Lock()

        def next_index(self, key, pool, cooldown_seconds):
            with self.lock:
                return 0

        def has_available(self, key, pool, cooldown_seconds):
            return True

        def mark_failure(self, key, value, cooldown_seconds):
            pass

    original = akp._rotation_store
    akp._rotation_store = _FixedStore()
    try:
        resolver = ApiKeyChainResolver()
        ep = _ep(keys=['sk-a1', 'sk-b2'])
        # 固定实现恒返回下标 0
        assert resolver.resolve_rotating(rotation_key=_rk(), endpoint=ep) == 'sk-a1'
        assert resolver.resolve_rotating(rotation_key=_rk(), endpoint=ep) == 'sk-a1'
    finally:
        akp._rotation_store = original


# ── adapter 服务密钥提供者（Infrastructure 层）────────────────

def test_resolver_from_config_chain_order():
    """resolver_from_config 键名配置 + 链序（case > meta > env）。"""
    resolver = resolver_from_config(
        lambda section, key, default=None: {
            'case_config_key': 'k1', 'meta_key': 'k2',
            'env_key': 'MY_PLATFORM_KEY'}.get(key, default))
    assert resolver.case_key == 'k1'
    assert resolver.meta_key == 'k2'
    assert resolver.env_key == 'MY_PLATFORM_KEY'


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


def test_voice_llm_chat_headers_carry_bearer():
    """execute_voice_llm_chat 合入 rendered_headers + X-Session-Id（Bearer 保留）。"""
    from unittest import mock

    driver = _driver({'api_key': 'sk-meta'}, {})
    captured = {}

    def _fake_call(**kwargs):
        captured['headers'] = kwargs['headers']
        return {'status_code': 200, 'latency': 10, 'raw_response': '',
                'json': {}, 'error': None}

    with mock.patch('api_test_service.infrastructure.adapters.'
                    'api_driver_adapter.api_client.call', _fake_call):
        driver.execute_voice_llm_chat(
            session_id='s-1', input_type='text', input_data='hi',
            round_number=1, total_rounds=1, timeout=5)
    assert captured['headers']['Authorization'] == 'Bearer sk-meta'
    assert captured['headers']['X-Session-Id'] == 's-1'


def test_driver_endpoint_pool_rotating_injected():
    """INT-1230 审计 D5'：ApiDriverAdapter._merge_headers 消费**当前端点**池
    （self.endpoint 含 path，base 前缀匹配回 api_endpoints 取池）轮换注入
    Bearer；同一端点连续解析命中各 key"""
    api_config = SimpleNamespace(
        id=31, meta={}, max_timeout=30,
        endpoint='https://ep.example.com/api/create_task',
        api_endpoints=[
            {'endpoint': 'https://ep.example.com',
             'api_keys': ['sk-a1', 'sk-b2']},
            {'endpoint': 'https://ep2.example.com',
             'api_keys': ['sk-x1', 'sk-x2']},
        ],
    )
    driver = ApiDriverAdapter(api_config, case_config={})
    h1, _ = driver.render_request_parts({})
    h2, _ = driver.render_request_parts({})
    assert h1['Authorization'] == 'Bearer sk-a1'
    assert h2['Authorization'] == 'Bearer sk-b2'


def test_driver_endpoint_pool_not_crossed():
    """多端点各用各池：按 self.endpoint 匹配的端点池轮换，另一端点池不串"""
    api_config = SimpleNamespace(
        id=32, meta={}, max_timeout=30,
        endpoint='https://ep2.example.com/api/create_task',
        api_endpoints=[
            {'endpoint': 'https://ep.example.com',
             'api_keys': ['sk-a1', 'sk-a2']},
            {'endpoint': 'https://ep2.example.com',
             'api_keys': ['sk-b1', 'sk-b2']},
        ],
    )
    driver = ApiDriverAdapter(api_config, case_config={})
    h1, _ = driver.render_request_parts({})
    h2, _ = driver.render_request_parts({})
    # 命中 ep2 池（不是 ep 池）：端点间不串
    assert h1['Authorization'] == 'Bearer sk-b1'
    assert h2['Authorization'] == 'Bearer sk-b2'


def test_driver_no_endpoint_match_fallback_single():
    """self.endpoint 未匹配任何 api_endpoints（main url 单端点）→ 回退单值链"""
    api_config = SimpleNamespace(
        id=33, meta={'api_key': 'sk-meta'}, max_timeout=30,
        endpoint='https://main.example.com',
        api_endpoints=[
            {'endpoint': 'https://ep.example.com',
             'api_keys': ['sk-a1', 'sk-a2']},
        ],
    )
    driver = ApiDriverAdapter(api_config, case_config={})
    h, _ = driver.render_request_parts({})
    assert h['Authorization'] == 'Bearer sk-meta'


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


def test_realtime_ws_headers_rotating_pool():
    """INT-1177：Realtime 静态 _resolve_ws_headers 消费 resolve_rotating
    （传 (api_id, ws endpoint URL)，同一端点同源轮换）；连续解析命中各 key"""
    api_config = SimpleNamespace(
        id=101, endpoint='wss://rt.example.com',
        api_endpoints=[{'endpoint': 'wss://rt.example.com',
                        'api_keys': ['sk-a1', 'sk-b2', 'sk-c3']}],
        meta={})
    h1 = RealtimeSessionExecutor._resolve_ws_headers(api_config)
    h2 = RealtimeSessionExecutor._resolve_ws_headers(api_config)
    h3 = RealtimeSessionExecutor._resolve_ws_headers(api_config)
    assert h1['Authorization'] == 'Bearer sk-a1'
    assert h2['Authorization'] == 'Bearer sk-b2'
    assert h3['Authorization'] == 'Bearer sk-c3'


def test_realtime_ws_headers_pool_all_cooled_no_auth(monkeypatch):
    """INT-1177：池全冷却 → resolve_rotating 返回空 → 不注入 Authorization"""
    from shared.utils.api_key_provider import (
        ApiKeyChainResolver,
        InMemoryRotationStateStore,
    )
    from api_test_service.core import realtime_session_executor as rse

    fresh = InMemoryRotationStateStore()
    resolver = ApiKeyChainResolver(cooldown_seconds=60)
    resolver.rotation_store = fresh
    monkeypatch.setattr(rse, '_key_resolver', resolver)
    ws_url = 'wss://rt.example.com'
    fresh.mark_failure((202, ws_url), 'sk-a1', 60)
    fresh.mark_failure((202, ws_url), 'sk-b2', 60)
    api_config = SimpleNamespace(
        id=202, endpoint=ws_url,
        api_endpoints=[{'endpoint': ws_url, 'api_keys': ['sk-a1', 'sk-b2']}],
        meta={})
    headers = RealtimeSessionExecutor._resolve_ws_headers(api_config)
    assert 'Authorization' not in headers
    assert headers == {}


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


# ── INT-1177 密钥池脱敏：api_keys 数组（mask_text + mask_mapping 双路径）──

def test_mask_text_api_keys_json_array_sk():
    """sk- 前缀数组：整数组掩 ****（结构不被拆坏、元素零明文）"""
    masked = mask_text('payload {"api_keys":["sk-abcdef1234567890","sk-xyz987654321"]} sent')
    assert 'sk-abcdef1234567890' not in masked
    assert 'sk-xyz987654321' not in masked
    assert '"api_keys":****' in masked


def test_mask_text_api_keys_json_array_non_sk():
    """非 sk- 前缀数组：现状键名不匹配整段泄漏，修复后整数组掩"""
    masked = mask_text('{"api_keys":["abc123456789","xyz987654321"]}')
    assert 'abc123456789' not in masked
    assert 'xyz987654321' not in masked
    assert 'api_keys":****' in masked


def test_mask_text_api_keys_kv_form():
    masked = mask_text('api_keys=[sk-abcdef1234567890,sk-xyz987654321]')
    assert 'sk-abcdef1234567890' not in masked
    assert 'sk-xyz987654321' not in masked
    assert 'api_keys=****' in masked


def test_mask_text_api_keys_idempotent():
    once = mask_text('{"api_keys":["sk-abcdef1234567890","sk-xyz987654321"]}')
    assert mask_text(once) == once


def test_mask_mapping_api_keys_array():
    """结构化 payload：api_keys 键命中后整数组掩 ****（sk- 与非 sk-）"""
    payload = {
        'api_keys': ['sk-abcdef1234567890', 'abc123456'],
        'nested': {'api_keys': ['sk-xyz987654321']},
        'plain': 'keep',
    }
    masked = mask_mapping(payload)
    assert masked['api_keys'] == '****'
    assert masked['nested']['api_keys'] == '****'
    assert masked['plain'] == 'keep'


def test_mask_mapping_suffix_api_keys_sensitive():
    """_is_sensitive_key 补 endswith('_api_keys')：xxx_api_keys 键同样脱敏"""
    from shared.utils.secret_mask import _is_sensitive_key
    assert _is_sensitive_key('api_keys') is True
    assert _is_sensitive_key('openai_api_keys') is True
    assert _is_sensitive_key('Api_Keys') is True
    assert _is_sensitive_key('API-KEYS') is True


def test_mask_mapping_endpoint_nested_api_keys():
    """INT-1230 审计 D7'（endpoint 级返工）：api_endpoints[].api_keys 嵌套
    数组（sk- 与非 sk-）经 mask_mapping 递归命中整组掩码，零明文"""
    payload = {
        'name': 'A',
        'api_endpoints': [
            {'endpoint': 'https://ep1.example.com',
             'api_keys': ['sk-abcdef1234567890', 'plain-abc123']},
            {'endpoint': 'https://ep2.example.com',
             'api_keys': ['sk-xyz987654321']},
        ],
    }
    masked = mask_mapping(payload)
    eps = masked['api_endpoints']
    assert eps[0]['api_keys'] == '****'
    assert eps[1]['api_keys'] == '****'
    assert 'sk-abcdef1234567890' not in str(masked)
    assert 'sk-xyz987654321' not in str(masked)
    assert 'plain-abc123' not in str(masked)


def test_mask_text_endpoint_nested_api_keys():
    """INT-1230 审计 D7'：端点 JSON 文本内 api_keys 数组形态（sk- 与非 sk-）
    经 mask_text 整数组掩码"""
    masked = mask_text(
        '{"api_endpoints":[{"endpoint":"https://ep.example.com",'
        '"api_keys":["sk-abcdef1234567890","plain-abc123"]}]}')
    assert 'sk-abcdef1234567890' not in masked
    assert 'plain-abc123' not in masked
    assert 'api_keys":****' in masked


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


# ── 无任务上下文的文件出口（服务文件）——INT-70 打回 P1 回归 ──

from shared.logging.service_handler import ServiceRotatingFileHandler


def test_service_file_handler_outlet_masked(tmp_path):
    """ServiceRotatingFileHandler 出口级掩码：原始 record 直发也零明文"""
    handler = ServiceRotatingFileHandler(
        str(tmp_path), base_name='app-test.log')
    handler.setFormatter(logging.Formatter(
        '[%(asctime)s] %(levelname)-8s %(module)s - %(message)s'))

    record = logging.LogRecord(
        name='x', level=logging.INFO, pathname='', lineno=0,
        msg='config dump api_key=sk-SECRETVALUE1234567890', args=(),
        exc_info=None)
    record.module = 'x'
    handler.emit(record)
    handler.close()

    content = (tmp_path / datetime.now().strftime('%Y-%m-%d') / 'app-test.log').read_text(encoding='utf-8')
    assert 'sk-SECRETVALUE1234567890' not in content
    assert 'api_key=****' in content


def test_emit_no_task_file_outlet_masked(monkeypatch, tmp_path):
    """端到端（打回复现）：无 task_id 系统日志/审计日志经 DatabaseLogHandler
    emit → _file_handler 分支，文件出口不落明文（含 Bearer/裸密钥形态）"""
    from shared.utils.log_handler import DatabaseLogHandler

    handler = DatabaseLogHandler()
    handler.set_console_log(False)
    try:
        file_handler = ServiceRotatingFileHandler(
            str(tmp_path), base_name='app-test.log')
        file_handler.setFormatter(logging.Formatter(
            '[%(asctime)s] %(levelname)-8s %(module)s - %(message)s'))
        monkeypatch.setattr(handler, '_file_handler', file_handler)

        system_record = logging.LogRecord(
            name='x', level=logging.INFO, pathname='', lineno=0,
            msg='config dump api_key=sk-SECRETVALUE1234567890', args=(),
            exc_info=None)
        system_record.module = 'x'
        system_record.category = 'system'
        system_record.task_id = None
        handler.emit(system_record)

        audit_record = logging.LogRecord(
            name='x', level=logging.INFO, pathname='', lineno=0,
            msg="auth handshake headers={\"Authorization\": "
                "\"Bearer sk-AUDITTOKEN123456789\"}", args=(), exc_info=None)
        audit_record.module = 'x'
        audit_record.category = 'auth'
        audit_record.task_id = None
        handler.emit(audit_record)
    finally:
        handler.queue.put(None)
        handler.worker_thread.join(timeout=1.0)
        file_handler.close()

    content = (tmp_path / datetime.now().strftime('%Y-%m-%d') / 'app-test.log').read_text(encoding='utf-8')
    assert 'sk-SECRETVALUE1234567890' not in content
    assert 'sk-AUDITTOKEN123456789' not in content
    assert '****' in content
