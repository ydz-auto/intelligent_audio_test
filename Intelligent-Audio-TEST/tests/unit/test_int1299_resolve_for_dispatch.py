# -*- coding: utf-8 -*-
"""INT-1299 Realtime 执行器分发表驱动化单测 — registry.resolve_for 命中/未命中

覆盖（验收标准）：
- resolve_for(REALTIME, OPENAI / OPENAI_REALTIME) → OpenAIRealtimeAdapter
- resolve_for(REALTIME, API_DRIVER / MOCK / 未配置默认) → None（默认回退
  RealtimeWSClient，向后兼容）
- 未知扁平 key → None
- 协议不匹配（HTTP 协议取 REALTIME 适配器）→ None
- 命中映射但适配器未注册 → VendorAdapterNotFoundError 上抛（fallback=False
  严格分发，防双通道语义歧义）
- 字符串扁平 key 等值映射
- _resolve_realtime_transport 纯查表：无 if/else 白名单，未配置走
  RealtimeWSClient 默认，命中经 resolve_for 构造并全参数透传
"""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.common_enums import (
    AdapterProtocol,
    AdapterVendor,
    VendorAdapterType,
)
from api_test_service.infrastructure.adapters import (
    VendorAdapterNotFoundError,
    VendorAdapterRegistry,
    vendor_adapter_registry,
)
from api_test_service.infrastructure.adapters.protocol.realtime_adapter_base import (
    RealtimeAdapterBase,
)
from api_test_service.infrastructure.adapters.vendors.openai_realtime_adapter import (
    OpenAIRealtimeAdapter,
)


def _fresh_registry():
    """独立注册表：REALTIME 协议级 base + OPENAI 品牌适配器齐备"""
    registry = VendorAdapterRegistry()
    registry.register(RealtimeAdapterBase)
    registry.register(OpenAIRealtimeAdapter)
    return registry


def _make_api_config(endpoint='ws://mock', meta=None, vendor='openai'):
    meta = dict(meta or {})
    return SimpleNamespace(
        id=7, endpoint=endpoint, api_endpoints=[], meta=meta,
        max_timeout=30, vendor=vendor)


class TestResolveForHit:
    """命中分支：扁平 key 在该协议下有映射 → 严格 resolve 返回适配器类"""

    def test_openai_flat_key(self):
        registry = _fresh_registry()
        assert registry.resolve_for(
            AdapterProtocol.REALTIME, VendorAdapterType.OPENAI) \
            is OpenAIRealtimeAdapter

    def test_openai_realtime_flat_key(self):
        registry = _fresh_registry()
        assert registry.resolve_for(
            AdapterProtocol.REALTIME, VendorAdapterType.OPENAI_REALTIME) \
            is OpenAIRealtimeAdapter

    def test_string_flat_key_coerced(self):
        registry = _fresh_registry()
        assert registry.resolve_for(
            AdapterProtocol.REALTIME, 'openai_realtime') \
            is OpenAIRealtimeAdapter

    def test_global_registry_hit(self):
        """全局注册表（内置适配器已装载）同样命中"""
        assert vendor_adapter_registry.resolve_for(
            AdapterProtocol.REALTIME, VendorAdapterType.OPENAI) \
            is OpenAIRealtimeAdapter


class TestResolveForMiss:
    """未命中分支：无映射 → None，由调用方保持默认构造"""

    def test_default_api_driver_flat_key(self):
        """默认 API_DRIVER 无协议强绑定 → REALTIME 下无映射 → None"""
        registry = _fresh_registry()
        assert registry.resolve_for(
            AdapterProtocol.REALTIME, VendorAdapterType.API_DRIVER) is None

    def test_mock_flat_key(self):
        registry = _fresh_registry()
        assert registry.resolve_for(
            AdapterProtocol.REALTIME, VendorAdapterType.MOCK) is None

    def test_unknown_flat_key(self):
        registry = _fresh_registry()
        assert registry.resolve_for(
            AdapterProtocol.REALTIME, 'no_such_vendor') is None

    def test_protocol_mismatch(self):
        """协议不匹配：HTTP 协议取 REALTIME 适配器 → None"""
        registry = _fresh_registry()
        assert registry.resolve_for(
            AdapterProtocol.HTTP, VendorAdapterType.OPENAI) is None
        assert registry.resolve_for(
            AdapterProtocol.WEBSOCKET, VendorAdapterType.OPENAI_REALTIME) is None

    def test_unconfigured_none_flat_key(self):
        """flat_key=None（未配置）→ None，不抛异常"""
        registry = _fresh_registry()
        assert registry.resolve_for(AdapterProtocol.REALTIME, None) is None


class TestResolveForStrict:
    """命中映射但适配器未注册 → 严格抛错（防双通道语义歧义）"""

    def test_hit_unregistered_raises(self):
        registry = VendorAdapterRegistry()  # 空表：映射命中但无实现
        with pytest.raises(VendorAdapterNotFoundError, match='未注册的厂商适配器'):
            registry.resolve_for(
                AdapterProtocol.REALTIME, VendorAdapterType.OPENAI)


class TestExecutorTableDrivenDispatch:
    """_resolve_realtime_transport 纯查表：resolve_for 是唯一分发入口"""

    @staticmethod
    def _executor():
        from api_test_service.core.realtime_session_executor import RealtimeSessionExecutor
        ex = RealtimeSessionExecutor.__new__(RealtimeSessionExecutor)
        ex._executor = SimpleNamespace(_log=lambda *a, **k: None)
        ex._on_frame = lambda *a, **k: None
        return ex

    def test_unset_keeps_realtime_ws_client(self):
        """未配置 / api_driver / mock → resolve_for=None → RealtimeWSClient 默认"""
        from api_test_service.infrastructure.adapters.transport import RealtimeWSClient
        ex = self._executor()
        for vendor_adapter in (None, 'api_driver', 'mock'):
            case_cfg = ({'vendor_adapter': vendor_adapter}
                        if vendor_adapter else {})
            transport = ex._resolve_realtime_transport(
                _make_api_config(), case_cfg, {}, 'ws://mock', {}, 20, 1, 'c1', 'rt-1')
            assert isinstance(transport, RealtimeWSClient), vendor_adapter

    def test_openai_selects_adapter(self):
        from api_test_service.infrastructure.adapters.vendors.openai_realtime_adapter import (
            OpenAIRealtimeAdapter,
        )
        ex = self._executor()
        transport = ex._resolve_realtime_transport(
            _make_api_config(), {'vendor_adapter': 'openai_realtime'}, {},
            'ws://mock', {}, 20, 1, 'c1', 'rt-1')
        assert isinstance(transport, OpenAIRealtimeAdapter)

    def test_dispatch_uses_resolve_for_with_full_kwargs_passthrough(self, monkeypatch):
        """resolve_for 命中 → adapter_cls 构造，executor 全参数透传

        验证新代码路径（表驱动入口）而非旧 if/else 白名单：resolve_for
        返回探测类时被构造，且构造 kwargs 含
        api_config/case_config/endpoint/headers/event_listener/chunk_duration_ms/
        test_case_id/task_id/proxy_type/proxy_url 全部字段。
        """
        import api_test_service.core.realtime_session_executor as rt_mod
        captured = {}

        class RecordingAdapter:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(rt_mod.vendor_adapter_registry, 'resolve_for',
                            lambda protocol, a_type: RecordingAdapter)
        ex = self._executor()
        cfg = _make_api_config(meta={'vendor_adapter': 'openai_realtime'})
        transport = ex._resolve_realtime_transport(
            cfg, {}, {}, 'ws://mock', {'X-H': '1'}, 20, 1, 'c1', 'rt-1',
            proxy_type='http', proxy_url='http://proxy:8080')

        assert isinstance(transport, RecordingAdapter)
        assert captured['api_config'] is cfg
        assert captured['case_config'] == {}
        assert captured['endpoint'] == 'ws://mock'
        assert captured['headers'] == {'X-H': '1'}
        assert captured['chunk_duration_ms'] == 20
        assert captured['test_case_id'] == 'c1'
        assert captured['task_id'] == 1
        assert captured['proxy_type'] == 'http'
        assert captured['proxy_url'] == 'http://proxy:8080'
        assert callable(captured['event_listener'])
