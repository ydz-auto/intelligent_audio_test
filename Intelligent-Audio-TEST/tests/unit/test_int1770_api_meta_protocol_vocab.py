# -*- coding: utf-8 -*-
"""INT-1770 协议词表兼容单测 — apis.meta.protocol 与 AdapterProtocol 冲突

背景：前端（旧 Vue FormField / 新 Vue deviceFields）「协议」写 http / https /
ws / wss，运行时 AdapterProtocol 只认 http / websocket / realtime / any，
旧值在 infer_protocol 直接 ValueError，任何用前端保存过协议的 API 建任务即失败
（主库 apis.id=1：device_type=http_api、meta={"protocol": "https"}）。

覆盖（卡上验收标准 1 / 3）：
- meta.protocol ∈ {http, https, ws, wss, websocket, realtime, any, 缺失, 空串}
  全部返回合法 AdapterProtocol，均不抛异常；
- 非法值（ftp）不抛错：WARNING 后按优先级回落（用例级 → api 级 → 端点前缀）；
- 既有优先级不变：case_config.protocol > api_config.meta.protocol > 端点前缀；
- dimensions_from_config / create_from_config 对 https 端点选出 HTTP 适配器；
- 迁移脚本归一映射与运行时映射同源口径。
"""
import importlib.util
import os
import sys

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.common_enums import (
    AdapterProtocol,
    AdapterVendor,
)
from api_test_service.infrastructure.adapters import (
    dimensions_from_config,
    infer_protocol,
    vendor_adapter_registry,
)
from api_test_service.infrastructure.adapters.api_driver_adapter import (
    ApiDriverAdapter,
)


def _make_api_config(endpoint='http://100.70.20.135:5000', meta=None,
                     device_type='http_api'):
    """最小 api_config 替身（与 test_int497 _make_api_config 同形）。

    默认形状照主库 apis.id=1：device_type=http_api + http 端点。
    """
    return type('Cfg', (), {
        'endpoint': endpoint, 'meta': dict(meta or {}), 'max_timeout': 5,
        'device_type': device_type,
        'api_endpoints': [{'endpoint': endpoint}],
    })()


# ──────────────────────────── 验收 1：词表全覆盖不抛错 ────────────────────────────

@pytest.mark.parametrize('raw,expected', [
    ('http', AdapterProtocol.HTTP),
    ('https', AdapterProtocol.HTTP),
    ('ws', AdapterProtocol.WEBSOCKET),
    ('wss', AdapterProtocol.WEBSOCKET),
    ('websocket', AdapterProtocol.WEBSOCKET),
    ('realtime', AdapterProtocol.REALTIME),
    ('any', AdapterProtocol.ANY),
    ('HTTPS', AdapterProtocol.HTTP),        # 大小写变体
    (' wss ', AdapterProtocol.WEBSOCKET),   # 首尾空白
])
def test_meta_protocol_vocab_never_raises(raw, expected):
    """meta.protocol 全词表（含前端旧词表）→ 合法 AdapterProtocol，不抛异常"""
    cfg = _make_api_config(meta={'protocol': raw})
    assert infer_protocol(cfg, {}) is expected


@pytest.mark.parametrize('meta', [None, {}, {'protocol': None}, {'protocol': ''},
                                  {'protocol': '   '}])
def test_missing_protocol_falls_back_to_endpoint_prefix(meta):
    """缺失 / 空串按端点前缀推断（ws(s):// → WEBSOCKET，http(s):// → HTTP）"""
    assert infer_protocol(_make_api_config('ws://h', meta=meta), {}) is AdapterProtocol.WEBSOCKET
    assert infer_protocol(_make_api_config('wss://h', meta=meta), {}) is AdapterProtocol.WEBSOCKET
    assert infer_protocol(_make_api_config('http://h', meta=meta), {}) is AdapterProtocol.HTTP
    assert infer_protocol(_make_api_config('https://h', meta=meta), {}) is AdapterProtocol.HTTP
    assert infer_protocol(None, {}) is AdapterProtocol.HTTP


def test_unknown_protocol_warns_and_falls_back(caplog):
    """非法值（ftp）WARNING 后按端点前缀兜底，不抛错"""
    with caplog.at_level('WARNING'):
        got = infer_protocol(_make_api_config('ws://h', meta={'protocol': 'ftp'}), {})
    assert got is AdapterProtocol.WEBSOCKET
    assert any('INT-1770' in rec.getMessage() for rec in caplog.records)


def test_unknown_protocol_without_endpoint_defaults_http(caplog):
    """非法值且无端点 → 默认 HTTP，不抛错"""
    with caplog.at_level('WARNING'):
        assert infer_protocol(_make_api_config('', meta={'protocol': 'ftp'}), {}) \
            is AdapterProtocol.HTTP
    assert any('INT-1770' in rec.getMessage() for rec in caplog.records)


def test_legacy_alias_logs_warning(caplog):
    """前端旧词表命中映射时留 WARNING（存量数据待迁移脚本回写）"""
    with caplog.at_level('WARNING'):
        assert infer_protocol(_make_api_config(meta={'protocol': 'https'}), {}) \
            is AdapterProtocol.HTTP
    assert any('归一化' in rec.getMessage() for rec in caplog.records)


# ──────────────────────────── 验收 3：既有优先级不变 ────────────────────────────

def test_case_level_protocol_still_wins():
    """用例级显式协议优先于 api 级（词表归一不改变优先级）"""
    cfg = _make_api_config('http://h', meta={'protocol': 'https'})
    assert infer_protocol(cfg, {'protocol': 'realtime'}) is AdapterProtocol.REALTIME
    assert infer_protocol(cfg, {'protocol': 'wss'}) is AdapterProtocol.WEBSOCKET
    assert infer_protocol(cfg, {'protocol': 'ws'}) is AdapterProtocol.WEBSOCKET
    # 用例级未配置时才取 api 级
    assert infer_protocol(cfg, {}) is AdapterProtocol.HTTP
    assert infer_protocol(cfg, None) is AdapterProtocol.HTTP


def test_case_level_unknown_falls_through_to_api_level(caplog):
    """用例级非法值视为未配置 → 回落 api 级（再不行才回落端点前缀）"""
    cfg = _make_api_config('ws://h', meta={'protocol': 'https'})
    with caplog.at_level('WARNING'):
        assert infer_protocol(cfg, {'protocol': 'ftp'}) is AdapterProtocol.HTTP
    assert any('INT-1770' in rec.getMessage() for rec in caplog.records)


# ──────────────────────────── 验收 2：主库 id=1 形状可选出适配器 ────────────────────────────

def test_main_db_api_shape_resolves_http_adapter():
    """照主库 apis.id=1：device_type=http_api + meta.protocol=https → HTTP 适配器"""
    cfg = _make_api_config(meta={'protocol': 'https', 'environment': 'development',
                                 'version': 'v1', 'apiKey': '11'})
    assert dimensions_from_config(cfg, {}) == (
        AdapterProtocol.HTTP, AdapterVendor.API_DRIVER)
    adapter = vendor_adapter_registry.create_from_config(cfg, {}, task_id=1)
    assert isinstance(adapter, ApiDriverAdapter)


@pytest.mark.parametrize('raw', ['https', 'ws', 'wss', 'http', 'websocket',
                                 'realtime', 'any', 'ftp', '', None])
def test_dimensions_from_config_never_raises(raw):
    """dimensions_from_config 对全词表（含非法值）均返回合法多维 key"""
    for endpoint in ('http://h', 'ws://h', ''):
        cfg = _make_api_config(endpoint, meta={'protocol': raw})
        protocol, vendor = dimensions_from_config(cfg, {})
        assert isinstance(protocol, AdapterProtocol)
        assert isinstance(vendor, AdapterVendor)


def test_vendor_adapter_override_unchanged():
    """vendor_adapter 分支不受影响：mock / openai 仍走各自维度"""
    # api 级显式协议（即便旧词表）仍优先于 ws:// 端点前缀（既有优先级不变）
    cfg = _make_api_config('ws://mock', meta={'protocol': 'https', 'vendor_adapter': 'mock'})
    protocol, vendor = dimensions_from_config(cfg, {})
    assert protocol is AdapterProtocol.HTTP
    assert vendor is AdapterVendor.MOCK
    cfg = _make_api_config(meta={'protocol': 'https', 'vendor_adapter': 'openai_realtime'})
    protocol, vendor = dimensions_from_config(cfg, {})
    assert protocol is AdapterProtocol.REALTIME
    assert vendor is AdapterVendor.OPENAI


# ──────────────────────────── 验收 4：迁移脚本文本归一映射 ────────────────────────────

def _load_migration_module():
    path = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts',
                        'migrations', '202610',
                        'normalize_api_meta_protocol_int1770.py')
    spec = importlib.util.spec_from_file_location('int1770_migration', os.path.abspath(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_mapping_matches_runtime_aliases():
    """迁移脚本归一映射与运行时映射同源口径，且只映射前端旧词表"""
    from api_test_service.infrastructure.adapters import registry as reg
    module = _load_migration_module()
    assert module.LEGACY_PROTOCOL_ALIASES == {
        value: alias.value for value, alias in reg._LEGACY_PROTOCOL_ALIASES.items()}
    assert module.normalize_protocol_value('HTTPS') == 'http'
    assert module.normalize_protocol_value(' wss ') == 'websocket'
    # 已标准 / 无法识别的取值不回写（幂等：归一后再次执行命中 0 行）
    for untouched in ('http', 'websocket', 'realtime', 'any', 'ftp', '', None):
        assert module.normalize_protocol_value(untouched) is None
