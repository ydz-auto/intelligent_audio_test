# -*- coding: utf-8 -*-
"""INT-72 单测（INT-1169/1176 改写）— 内嵌注册表 adapter_class 通道（UC-1003）。

api_adapter_service 删除后，apis.adapter_class 列保留，内嵌
vendor_adapter_registry 负责映射/校验：
- adapter_class=MockDialogAdapter → vendor_adapter='mock'（存量值映射）
- 未知 adapter_class → 显式报错（拒绝静默降级到 API_DRIVER）
- 未配置 adapter_class → 按 vendor_adapter / vendor 自动匹配
"""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'ut-dummy-ak')
os.environ.setdefault('OSS_SECRET_KEY', 'ut-dummy-sk')

from api_test_service.infrastructure.adapters import registry as reg
from api_test_service.infrastructure.adapters import vendor_adapter_registry


def _cfg(meta=None, adapter_class=None, vendor=None):
    return SimpleNamespace(
        id=1, meta=meta or {}, api_endpoints=[], api_url='http://api',
        adapter_class=adapter_class, vendor=vendor, proxy_type=None,
        proxy_url=None, max_timeout=30)


class TestAdapterClassChannelEmbedded:
    """apis.adapter_class → 内嵌注册表映射（UC-0901/UC-1003 通道）。"""

    def test_mock_dialog_adapter_maps_to_mock(self):
        cls = vendor_adapter_registry.create_from_config(
            _cfg(adapter_class='MockDialogAdapter'), {})
        assert type(cls).__name__ == 'MockVendorAdapter'

    def test_unknown_adapter_class_raises(self):
        with pytest.raises(ValueError, match='未注册'):
            vendor_adapter_registry.create_from_config(
                _cfg(adapter_class='DoubaoRealtimeAdapter'), {})

    def test_no_adapter_class_falls_back_to_vendor_adapter(self):
        cls = vendor_adapter_registry.create_from_config(
            _cfg(meta={'vendor_adapter': 'api_driver'}), {})
        assert type(cls).__name__ == 'ApiDriverAdapter'

    def test_no_adapter_class_vendor_mock_guard(self):
        cls = vendor_adapter_registry.create_from_config(
            _cfg(vendor='mock'), {})
        assert type(cls).__name__ == 'MockVendorAdapter'


class TestEmbeddedRegistryDefaults:
    """内嵌注册表默认注册快照（INT-62/INT-497 注册即生效）。"""

    def test_builtin_adapters_registered(self):
        from shared.models.common_enums import VendorAdapterType
        names = {e['class'] for e in vendor_adapter_registry.list_adapters()}
        assert 'ApiDriverAdapter' in names
        assert 'MockVendorAdapter' in names
        assert 'OpenAIRealtimeAdapter' in names

    def test_mock_vendor_adapter_type(self):
        from shared.models.common_enums import VendorAdapterType
        assert reg._FLAT_KEY_DIMENSIONS[VendorAdapterType.MOCK] == (
            None, reg.AdapterVendor.MOCK)
