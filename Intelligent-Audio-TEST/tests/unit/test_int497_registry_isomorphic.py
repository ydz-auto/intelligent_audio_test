# -*- coding: utf-8 -*-
"""INT-497 注册表同构单测 — 与设备驱动注册表（device_service/infrastructure/drivers/registry.py）对齐

覆盖（验收标准 1）：
- @register_vendor_adapter 装饰器注册多维 key (protocol, vendor)
- resolve 精确 → 同协议基线兜底 → 遗留通配协议 → 全局默认 → 抛错；fallback=False 仅精确
- 依赖检测：dependencies 缺失 → MISSING_DEPENDENCY，resolve 报依赖缺失真因
- 热更新：unregister_module / reload_module（对齐驱动 registry 断言风格）
- list_adapters 自描述（protocol / vendor / status / module）
- create_from_config 向后兼容：api_driver / mock 行为不变，openai_realtime → 品牌适配器；
  协议维度由显式 protocol 配置 > endpoint 前缀推断
- VendorAdapterType 扁平 key 兼容层映射
"""
import importlib
import os
import sys
import textwrap

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.common_enums import (
    AdapterProtocol,
    AdapterVendor,
    VendorAdapterType,
)
from api_test_service.domain.ports import ApiVendorAdapter
from api_test_service.infrastructure.adapters import (
    VendorAdapterNotFoundError,
    VendorAdapterRegistry,
    VendorAdapterStatus,
    adapter_type_from_config,
    dimensions_from_config,
    infer_protocol,
    register_vendor_adapter,
    vendor_adapter_registry,
)
from api_test_service.infrastructure.adapters.api_driver_adapter import (
    ApiDriverAdapter,
)
from api_test_service.infrastructure.adapters.mock_vendor_adapter import (
    MockVendorAdapter,
)
from api_test_service.infrastructure.adapters.protocol.realtime_adapter_base import (
    RealtimeAdapterBase,
)
from api_test_service.infrastructure.adapters.vendors.openai_realtime_adapter import (
    OpenAIRealtimeAdapter,
)


def _make_api_config(endpoint, meta=None, max_timeout=5, vendor_adapter=None):
    """最小 api_config 替身（与 test_int62 _make_api_config 同形）"""
    meta = dict(meta or {})
    if vendor_adapter:
        meta['vendor_adapter'] = vendor_adapter
    return type('Cfg', (), {
        'endpoint': endpoint, 'meta': meta, 'max_timeout': max_timeout,
        'api_endpoints': [{'endpoint': endpoint}],
    })()


# ──────────────────────────── 多维注册与 resolve 级联 ────────────────────────────

class TestMultiDimRegistration:
    def test_new_style_protocol_vendor_register(self):
        registry = VendorAdapterRegistry()

        @register_vendor_adapter(registry=registry)
        class Probe(ApiVendorAdapter):
            protocol = AdapterProtocol.WEBSOCKET
            vendor = AdapterVendor.MOCK

            def render_request_parts(self, context_data):
                return {}, {}

            def execute(self, context_data, files=None, method=None):
                return {'success': True, 'probe': True}

        entry = registry.get_by_key(AdapterProtocol.WEBSOCKET, AdapterVendor.MOCK)
        assert entry is not None and entry.adapter_cls is Probe
        assert entry.status == VendorAdapterStatus.AVAILABLE

    def test_legacy_adapter_type_registers_wildcard_protocol(self):
        """遗留适配器（仅 adapter_type）协议维度取通配 ANY"""
        registry = VendorAdapterRegistry()
        registry.register(ApiDriverAdapter)
        registry.register(MockVendorAdapter)
        assert registry.get_by_key(AdapterProtocol.ANY, AdapterVendor.API_DRIVER) \
            .adapter_cls is ApiDriverAdapter
        assert registry.get_by_key(AdapterProtocol.ANY, AdapterVendor.MOCK) \
            .adapter_cls is MockVendorAdapter

    def test_protocol_base_registers_any_vendor(self):
        registry = VendorAdapterRegistry()
        registry.register(RealtimeAdapterBase)
        entry = registry.get_by_key(AdapterProtocol.REALTIME, AdapterVendor.ANY)
        assert entry is not None and entry.adapter_cls is RealtimeAdapterBase

    def test_brand_adapter_registers_full_key(self):
        registry = VendorAdapterRegistry()
        registry.register(OpenAIRealtimeAdapter)
        assert registry.get_by_key(
            AdapterProtocol.REALTIME, AdapterVendor.OPENAI).adapter_cls \
            is OpenAIRealtimeAdapter


class TestResolveCascade:
    def test_exact_match(self):
        assert vendor_adapter_registry.resolve(
            AdapterProtocol.REALTIME, AdapterVendor.OPENAI) is OpenAIRealtimeAdapter

    def test_fallback_false_strict_exact_only(self):
        """fallback=False 仅精确匹配：协议基线/遗留通配不得静默回落"""
        registry = VendorAdapterRegistry()
        registry.register(RealtimeAdapterBase)
        registry.register(MockVendorAdapter)
        # REALTIME 品牌显式配置路径：REALTIME 基线已注册也不回退（防双通道歧义）
        with pytest.raises(VendorAdapterNotFoundError):
            registry.resolve(AdapterProtocol.REALTIME, AdapterVendor.OPENAI,
                             fallback=False)
        # 精确命中不受影响
        assert registry.resolve(AdapterProtocol.REALTIME, AdapterVendor.ANY,
                                fallback=False) is RealtimeAdapterBase

    def test_same_protocol_baseline_fallback(self):
        """同协议基线兜底：REALTIME 品牌未注册 → 协议级 base（(REALTIME, ANY)）"""
        registry = VendorAdapterRegistry()
        registry.register(RealtimeAdapterBase)
        assert registry.resolve(
            AdapterProtocol.REALTIME, AdapterVendor.OPENAI) is RealtimeAdapterBase

    def test_legacy_wildcard_protocol_fallback(self):
        """遗留通配协议兜底：HTTP+API_DRIVER / WEBSOCKET+MOCK 回落 (ANY, vendor)"""
        registry = VendorAdapterRegistry()
        registry.register(ApiDriverAdapter)
        registry.register(MockVendorAdapter)
        assert registry.resolve(
            AdapterProtocol.HTTP, AdapterVendor.API_DRIVER) is ApiDriverAdapter
        assert registry.resolve(
            AdapterProtocol.WEBSOCKET, AdapterVendor.MOCK) is MockVendorAdapter

    def test_flat_key_compat_resolve(self):
        """VendorAdapterType 扁平 key 单参 resolve（遗留调用兼容）"""
        assert vendor_adapter_registry.resolve(VendorAdapterType.API_DRIVER) \
            is ApiDriverAdapter
        assert vendor_adapter_registry.resolve(VendorAdapterType.MOCK) \
            is MockVendorAdapter
        assert vendor_adapter_registry.resolve(VendorAdapterType.OPENAI_REALTIME) \
            is OpenAIRealtimeAdapter

    def test_unresolvable_raises_with_reason(self):
        registry = VendorAdapterRegistry()
        registry.register(RealtimeAdapterBase)
        with pytest.raises(VendorAdapterNotFoundError, match='未注册的厂商适配器'):
            registry.resolve(AdapterProtocol.HTTP, AdapterVendor.OPENAI)

    def test_register_rejects_non_port_subclass(self):
        registry = VendorAdapterRegistry()
        with pytest.raises(TypeError, match='ApiVendorAdapter'):
            registry.register(type('Bad', (), {'adapter_type': VendorAdapterType.MOCK}))

    def test_register_rejects_missing_dimensions(self):
        registry = VendorAdapterRegistry()

        class Bad(ApiVendorAdapter):
            def execute(self, *a, **k):
                return {}

            def render_request_parts(self, context_data):
                return {}, {}

        with pytest.raises(TypeError, match='adapter_type'):
            registry.register(Bad)


# ──────────────────────────── 依赖检测 ────────────────────────────

class TestDependencyDetection:
    def test_missing_dependency_marks_status(self):
        registry = VendorAdapterRegistry()

        @register_vendor_adapter(registry=registry)
        class DepBroken(ApiVendorAdapter):
            protocol = AdapterProtocol.HTTP
            vendor = AdapterVendor.MOCK
            dependencies = ['no_such_package_xyz_497']

            def render_request_parts(self, context_data):
                return {}, {}

            def execute(self, context_data, files=None, method=None):
                return {}

        entry = registry.get_by_key(AdapterProtocol.HTTP, AdapterVendor.MOCK)
        assert entry.status == VendorAdapterStatus.MISSING_DEPENDENCY
        assert entry.missing_dep == 'no_such_package_xyz_497'
        assert entry.is_available is False
        assert registry.is_available(AdapterProtocol.HTTP, AdapterVendor.MOCK) is False
        # 依赖缺失仍注册（list 自描述可见），resolve 报依赖缺失真因
        listed = {a['display_name']: a for a in registry.list_adapters()}
        assert listed['DepBroken']['status'] == 'missing_dependency'
        with pytest.raises(VendorAdapterNotFoundError, match='依赖缺失'):
            registry.resolve(AdapterProtocol.HTTP, AdapterVendor.MOCK)

    def test_available_when_dependency_present(self):
        registry = VendorAdapterRegistry()
        registry.register(OpenAIRealtimeAdapter)
        assert registry.is_available(
            AdapterProtocol.REALTIME, AdapterVendor.OPENAI) is True


# ──────────────────────────── 热更新 ────────────────────────────

@pytest.fixture()
def hot_module(tmp_path, monkeypatch):
    """临时模块包：@register_vendor_adapter 注册一个 Probe 适配器，供 reload 演练。

    模块内装饰器注册到全局 vendor_adapter_registry；用例结束按模块注销清理，
    避免残留 (websocket, mock) 热探针条目污染后续用例。
    """
    module_name = 'hotmod_pkg.probe_adapters'
    pkg_dir = tmp_path / 'hotmod_pkg'
    pkg_dir.mkdir()
    (pkg_dir / '__init__.py').write_text('', encoding='utf-8')
    mod_path = pkg_dir / 'probe_adapters.py'
    mod_path.write_text(textwrap.dedent('''\
        from shared.models.common_enums import AdapterProtocol, AdapterVendor
        from api_test_service.domain.ports import ApiVendorAdapter
        from api_test_service.infrastructure.adapters.registry import register_vendor_adapter

        @register_vendor_adapter
        class HotProbeAdapter(ApiVendorAdapter):
            protocol = AdapterProtocol.WEBSOCKET
            vendor = AdapterVendor.MOCK
            display_name = 'hot-v1'

            def render_request_parts(self, context_data):
                return {}, {}

            def execute(self, context_data, files=None, method=None):
                return {'version': 'v1'}
    '''), encoding='utf-8')
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.import_module(module_name)
    yield {'pkg_dir': pkg_dir, 'mod_path': mod_path,
           'module_name': module_name}
    vendor_adapter_registry.unregister_module(module_name)
    sys.modules.pop(module_name, None)
    sys.modules.pop('hotmod_pkg', None)


class TestHotUpdate:
    def test_unregister_module(self, hot_module):
        module_name = hot_module['module_name']
        assert vendor_adapter_registry.get_by_key(
            AdapterProtocol.WEBSOCKET, AdapterVendor.MOCK) is not None
        removed = vendor_adapter_registry.unregister_module(module_name)
        assert len(removed) == 1
        assert vendor_adapter_registry.get_by_key(
            AdapterProtocol.WEBSOCKET, AdapterVendor.MOCK) is None

    def test_reload_module_replaces_entry(self, hot_module):
        module_name = hot_module['module_name']
        old = vendor_adapter_registry.get_by_key(
            AdapterProtocol.WEBSOCKET, AdapterVendor.MOCK)
        assert old is not None and old.display_name == 'hot-v1'

        # 改模块源码 → reload → 新注册条目替换旧条目。
        # 注意 v2 源码必须与 v1 长度不同：Windows 粗粒度 mtime（2s）+ 等长文件
        # 会命中 __pycache__ 时间戳校验复用旧字节码，reload 读到旧类。
        hot_module['mod_path'].write_text(textwrap.dedent('''\
            from shared.models.common_enums import AdapterProtocol, AdapterVendor
            from api_test_service.domain.ports import ApiVendorAdapter
            from api_test_service.infrastructure.adapters.registry import register_vendor_adapter

            @register_vendor_adapter
            class HotProbeAdapter(ApiVendorAdapter):
                protocol = AdapterProtocol.WEBSOCKET
                vendor = AdapterVendor.MOCK
                display_name = 'hot-v2-reloaded'

                def render_request_parts(self, context_data):
                    return {}, {}

                def execute(self, context_data, files=None, method=None):
                    return {'version': 'v2'}
        '''), encoding='utf-8')
        new_entries = vendor_adapter_registry.reload_module(module_name)
        assert len(new_entries) == 1
        new = vendor_adapter_registry.get_by_key(
            AdapterProtocol.WEBSOCKET, AdapterVendor.MOCK)
        assert new is not None and new.display_name == 'hot-v2-reloaded'

    def test_reload_failure_restores_old(self, hot_module):
        module_name = hot_module['module_name']
        old = vendor_adapter_registry.get_by_key(
            AdapterProtocol.WEBSOCKET, AdapterVendor.MOCK)
        assert old is not None

        # 写入语法错误 → reload 失败 → 旧条目恢复
        hot_module['mod_path'].write_text('this is not python !!!', encoding='utf-8')
        with pytest.raises(SyntaxError):
            vendor_adapter_registry.reload_module(module_name)
        restored = vendor_adapter_registry.get_by_key(
            AdapterProtocol.WEBSOCKET, AdapterVendor.MOCK)
        assert restored is not None and restored.adapter_cls is old.adapter_cls


# ──────────────────────────── list 自描述 ────────────────────────────

class TestListSelfDescription:
    def test_global_registry_self_describes(self):
        listed = vendor_adapter_registry.list_adapters()
        keys = {(a['protocol'], a['vendor']) for a in listed}
        assert ('any', 'api_driver') in keys
        assert ('any', 'mock') in keys
        assert ('realtime', 'any') in keys
        assert ('realtime', 'openai') in keys
        for a in listed:
            assert a['status'] in ('available', 'missing_dependency')
            assert a['module'] and a['class']


# ──────────────────────────── create_from_config 兼容 ────────────────────────────

class TestCreateFromConfigCompat:
    def test_default_resolves_api_driver(self):
        cfg = _make_api_config('http://x')
        adapter = vendor_adapter_registry.create_from_config(cfg)
        assert isinstance(adapter, ApiDriverAdapter)

    def test_flat_key_mock_unchanged(self):
        cfg = _make_api_config('http://x', vendor_adapter='mock')
        adapter = vendor_adapter_registry.create_from_config(cfg)
        assert isinstance(adapter, MockVendorAdapter)

    def test_flat_key_api_driver_unchanged(self):
        cfg = _make_api_config('http://x', vendor_adapter='api_driver')
        adapter = vendor_adapter_registry.create_from_config(cfg)
        assert isinstance(adapter, ApiDriverAdapter)

    def test_flat_key_openai_realtime(self):
        cfg = _make_api_config('ws://mock', vendor_adapter='openai_realtime')
        adapter = vendor_adapter_registry.create_from_config(cfg)
        assert isinstance(adapter, OpenAIRealtimeAdapter)

    def test_flat_key_openai_forced_realtime(self):
        """品牌扁平 key openai 首期协议维度固定 REALTIME（方案审计拍板第 5 项）"""
        cfg = _make_api_config('http://x', vendor_adapter='openai')
        adapter = vendor_adapter_registry.create_from_config(cfg)
        assert isinstance(adapter, OpenAIRealtimeAdapter)

    def test_unknown_value_rejected(self):
        cfg = _make_api_config('http://x', vendor_adapter='no_such_vendor')
        with pytest.raises(ValueError, match='未知的 vendor_adapter 配置'):
            adapter_type_from_config(cfg)

    def test_endpoint_prefix_protocol_inference(self):
        """协议维度推断：endpoint 前缀 ws:// → WEBSOCKET，http(s):// → HTTP"""
        assert infer_protocol(_make_api_config('ws://h')) is AdapterProtocol.WEBSOCKET
        assert infer_protocol(_make_api_config('wss://h')) is AdapterProtocol.WEBSOCKET
        assert infer_protocol(_make_api_config('http://h')) is AdapterProtocol.HTTP
        assert infer_protocol(_make_api_config('https://h')) is AdapterProtocol.HTTP
        assert infer_protocol(None, {}) is AdapterProtocol.HTTP

    def test_explicit_protocol_overrides_prefix(self):
        """显式 protocol 配置优先于 endpoint 前缀推断"""
        cfg = _make_api_config('http://h', meta={'protocol': 'realtime'})
        assert infer_protocol(cfg, {}) is AdapterProtocol.REALTIME

    def test_dimensions_from_config(self):
        cfg = _make_api_config('ws://mock', vendor_adapter='mock')
        protocol, vendor = dimensions_from_config(cfg, {})
        assert protocol is AdapterProtocol.WEBSOCKET
        assert vendor is AdapterVendor.MOCK
        # 无配置默认
        protocol, vendor = dimensions_from_config(None, None)
        assert protocol is AdapterProtocol.HTTP
        assert vendor is AdapterVendor.API_DRIVER
