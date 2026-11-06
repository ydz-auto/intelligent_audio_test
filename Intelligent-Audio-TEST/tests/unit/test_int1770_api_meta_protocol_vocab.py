# -*- coding: utf-8 -*-
"""协议维度推断单测 — 承接 INT-1770，契约按 INT-1799（B0 裁定 §3.4.5）收敛

背景：INT-1770 曾让 `infer_protocol` 依次读「用例级 case_config.protocol →
`apis.meta.protocol` → 端点前缀」三处来源，并对前端旧词表（https / ws / wss）
做只读归一。INT-1799 把协议唯一来源收敛到 `apis.protocol` 列，迁移
`add_api_protocol_streaming_int1798.py` 已把 `apis.meta.protocol` 整键删除，
三处旧来源一并移除（不再有双来源打架、也不再静默按前缀兜底）。

本文件保留 INT-1770 里**仍然成立**的覆盖（词表归一、dimensions_from_config
选适配器、vendor_adapter 分支），并把「旧来源已失效」写成回归断言。

旧契约里被删除的三组（保留在 git 历史，不再断言）：
- `meta.protocol` / 用例级 protocol 作为推断来源；
- 端点前缀（ws:// / http://）兜底；
- 非法值 WARNING 后回落、`infer_protocol` never_raises —— 新契约是显式
  ValueError（写侧 400），不允许「配置看似正常、执行静默跑错协议」。
"""
import os

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
                     device_type='http_api', protocol='http'):
    """最小 api_config 替身（与 test_int497 _make_api_config 同形）。

    默认形状照主库 apis.id=1：device_type=http_api（退场列，读侧不再使用）
    + protocol 列 http + meta 里可能残留别的键。
    """
    return type('Cfg', (), {
        'endpoint': endpoint, 'meta': dict(meta or {}), 'max_timeout': 5,
        'device_type': device_type, 'protocol': protocol,
        'api_endpoints': [{'endpoint': endpoint}],
    })()


# ──────────────────── 词表归一：`apis.protocol` 列 → AdapterProtocol ────────────────────

@pytest.mark.parametrize('raw,expected', [
    ('http', AdapterProtocol.HTTP),
    ('https', AdapterProtocol.HTTP),
    ('ws', AdapterProtocol.WEBSOCKET),
    ('wss', AdapterProtocol.WEBSOCKET),
    ('websocket', AdapterProtocol.WEBSOCKET),
    ('HTTPS', AdapterProtocol.HTTP),        # 大小写变体
    (' wss ', AdapterProtocol.WEBSOCKET),   # 首尾空白
])
def test_protocol_column_vocab(raw, expected):
    """protocol 列的标准值与别名都归一到 AdapterProtocol（归一表唯一）"""
    assert infer_protocol(_make_api_config(protocol=raw), {}) is expected


@pytest.mark.parametrize('raw', [None, '', '   '])
def test_missing_protocol_column_raises(raw):
    """列值缺失 → ValueError（不按端点前缀兜底，也不默认 http）"""
    with pytest.raises(ValueError, match='protocol'):
        infer_protocol(_make_api_config(protocol=raw), {})


@pytest.mark.parametrize('raw', ['ftp', 'http2', 'rtmp'])
def test_unknown_protocol_column_raises(raw):
    """列值不在词表内 → ValueError（写侧 400，不 WARNING 后静默回落）"""
    with pytest.raises(ValueError):
        infer_protocol(_make_api_config(protocol=raw), {})


@pytest.mark.parametrize('raw', ['sse'])
def test_unimplemented_protocol_raises(raw):
    """sse 列值合法但适配器未上线（A2 / INT-1790）→ 显式报错，不静默走 HTTP"""
    with pytest.raises(ValueError, match='未上线'):
        infer_protocol(_make_api_config(protocol=raw), {})


def test_grpc_protocol_maps_to_grpc():
    """grpc 列值已由 A1（INT-1789）上线 → 正向映射到 AdapterProtocol.GRPC"""
    assert infer_protocol(_make_api_config(protocol='grpc'), {}) is AdapterProtocol.GRPC


def test_none_api_config_defaults_http():
    """无 API 对象 → 注册表默认维度 HTTP（不是业务兜底）"""
    assert infer_protocol(None, {}) is AdapterProtocol.HTTP


# ──────────────────── 单来源：三处旧来源不再影响推断 ────────────────────

def test_case_level_protocol_no_longer_wins():
    """用例级 case_config.protocol 已废弃：列值说了算"""
    cfg = _make_api_config(protocol='http')
    assert infer_protocol(cfg, {'protocol': 'realtime'}) is AdapterProtocol.HTTP
    assert infer_protocol(cfg, {'protocol': 'wss'}) is AdapterProtocol.HTTP


def test_meta_protocol_no_longer_read():
    """`meta.protocol` 迁移后已从库里删除，残留键不再影响推断"""
    cfg = _make_api_config(protocol='websocket', meta={'protocol': 'https'})
    assert infer_protocol(cfg, {}) is AdapterProtocol.WEBSOCKET


def test_endpoint_prefix_no_longer_inferred():
    """端点前缀（ws://）不再推断协议：列值 http 就是 HTTP"""
    cfg = _make_api_config(endpoint='ws://h', protocol='http')
    assert infer_protocol(cfg, {}) is AdapterProtocol.HTTP


# ──────────────────── dimensions_from_config：仍成立的适配器选择 ────────────────────

def test_main_db_api_shape_resolves_http_adapter():
    """照主库 apis.id=1：device_type=http_api + meta.protocol 残留 → HTTP 适配器"""
    cfg = _make_api_config(meta={'protocol': 'https', 'environment': 'development',
                                 'version': 'v1', 'apiKey': '11'}, protocol='http')
    assert dimensions_from_config(cfg, {}) == (
        AdapterProtocol.HTTP, AdapterVendor.API_DRIVER)
    adapter = vendor_adapter_registry.create_from_config(cfg, {}, task_id=1)
    assert isinstance(adapter, ApiDriverAdapter)


@pytest.mark.parametrize('raw,expected', [
    ('http', AdapterProtocol.HTTP),
    ('websocket', AdapterProtocol.WEBSOCKET),
    ('ws', AdapterProtocol.WEBSOCKET),      # 别名归一后仍积极参与维度选择
])
def test_dimensions_from_config_follows_protocol_column(raw, expected):
    """维度 key 跟随 protocol 列（含别名），vendor 走固定 API_DRIVER"""
    protocol, vendor = dimensions_from_config(_make_api_config(protocol=raw), {})
    assert protocol is expected
    assert vendor is AdapterVendor.API_DRIVER


def test_vendor_adapter_override_unchanged():
    """vendor_adapter 分支不受影响：mock / openai 仍走各自维度（协议维度锁定）"""
    cfg = _make_api_config('ws://mock', protocol='http',
                           meta={'protocol': 'https', 'vendor_adapter': 'mock'})
    protocol, vendor = dimensions_from_config(cfg, {})
    assert protocol is AdapterProtocol.HTTP
    assert vendor is AdapterVendor.MOCK
    cfg = _make_api_config(protocol='http',
                           meta={'protocol': 'https',
                                 'vendor_adapter': 'openai_realtime'})
    protocol, vendor = dimensions_from_config(cfg, {})
    assert protocol is AdapterProtocol.REALTIME
    assert vendor is AdapterVendor.OPENAI
