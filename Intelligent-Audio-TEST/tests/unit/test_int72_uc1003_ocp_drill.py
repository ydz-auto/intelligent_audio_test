# -*- coding: utf-8 -*-
"""INT-72 验收测试（INT-1169/1176 改写）— 内嵌注册表 UC-1003 OCP 实弹演练。

api_adapter_service 删除后，OCP 演练指向内嵌 vendor_adapter_registry：
新厂商适配器只新增一个子类文件（@register_vendor_adapter 自注册），
基类 / 注册表 / 执行链零改动（OCP），注册即生效。

本文件真实地向 api_test_service/infrastructure/adapters 包写入一个新厂商子类
模块，import 触发装饰器自注册，验证 create_from_config 自动匹配，
结束后完整还原（模块文件 / sys.modules / 单例注册表），不污染同进程其他用例。
"""
import hashlib
import importlib
import os
import sys
from types import SimpleNamespace

import pytest

# BaseConfig 导入期强校验（tests/conftest.py 已兜底 DATABASE_URL，此处补
# OSS 两键的进程级兜底；显式配置的环境变量不受影响）
os.environ.setdefault('OSS_ACCESS_KEY', 'ut-dummy-ak')
os.environ.setdefault('OSS_SECRET_KEY', 'ut-dummy-sk')

from shared.models.common_enums import AdapterProtocol, AdapterVendor  # noqa: E402

ADAPTERS_PKG = 'api_test_service.infrastructure.adapters'
NEW_MODULE_NAME = 'zz_acceptance_acme_adapter'
GUARDED_FILES = ('registry.py', 'api_driver_adapter.py')

# 演练厂商注册键：(HTTP, API_DRIVER) —— 与既有 ApiDriverAdapter（(ANY, API_DRIVER)
# 遗留单维）不同键，不覆盖；create_from_config 在演练期间按该键精确命中。
NEW_MODULE_SRC = f'''# -*- coding: utf-8 -*-
"""验收演练：模拟新厂商 Acme 仅新增一个子类文件即完成接入（UC-1003）。"""
from api_test_service.domain.ports import ApiVendorAdapter
from api_test_service.infrastructure.adapters.registry import register_vendor_adapter
from shared.models.common_enums import AdapterProtocol, AdapterVendor


@register_vendor_adapter
class AcmeRealtimeAdapter(ApiVendorAdapter):
    """UC-1003 演练厂商适配器（HTTP 协议，vendor=api_driver 键）。"""

    protocol = AdapterProtocol.HTTP
    vendor = AdapterVendor.API_DRIVER

    def __init__(self, api_config=None, case_config=None, endpoint=None,
                 test_case_id=None, task_id=None):
        self.api_config = api_config
        self.case_config = case_config or {{}}

    def render_request_parts(self, context_data):
        return {{}}, dict(context_data or {{}})

    def execute(self, context_data, files=None, method=None):
        return {{
            'success': True, 'latency': 0, 'status_code': 200,
            'raw_response': {{'vendor': 'acme'}}, 'error': None,
            'json': {{}}, 'asr': 'acme-asr', 'trans': 'acme-trans',
        }}
'''

DEFAULT_ADAPTER_NAMES = {
    'ApiDriverAdapter', 'MockVendorAdapter', 'OpenAIRealtimeAdapter',
}


def _pkg_dir():
    pkg = importlib.import_module(ADAPTERS_PKG)
    return os.path.dirname(os.path.abspath(pkg.__file__))


def _file_hash(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


@pytest.fixture()
def acme_drill():
    pkg = importlib.import_module(ADAPTERS_PKG)
    pkg_dir = _pkg_dir()
    new_path = os.path.join(pkg_dir, NEW_MODULE_NAME + '.py')
    guarded_before = {
        name: _file_hash(os.path.join(pkg_dir, name))
        for name in GUARDED_FILES
    }
    assert not os.path.exists(new_path), '演练模块文件已存在，拒绝覆盖'
    with open(new_path, 'w', encoding='utf-8') as f:
        f.write(NEW_MODULE_SRC)
    importlib.invalidate_caches()
    try:
        importlib.import_module(f'{ADAPTERS_PKG}.{NEW_MODULE_NAME}')
        yield pkg_dir, guarded_before
    finally:
        if os.path.exists(new_path):
            os.remove(new_path)
        sys.modules.pop(f'{ADAPTERS_PKG}.{NEW_MODULE_NAME}', None)
        importlib.invalidate_caches()
        from api_test_service.infrastructure.adapters import \
            vendor_adapter_registry
        vendor_adapter_registry.unregister(
            AdapterProtocol.HTTP, AdapterVendor.API_DRIVER)


class TestUC1003OCPDrill:
    """新厂商仅新增一个子类文件 → 注册即生效（验收标准逐条演练）。"""

    def test_new_vendor_single_file_zero_touch(self, acme_drill):
        pkg_dir, guarded_before = acme_drill
        # 基类 / 注册表零改动：写入新厂商文件前后哈希一致
        for name, digest in guarded_before.items():
            assert _file_hash(os.path.join(pkg_dir, name)) == digest, name

        mod = importlib.import_module(f'{ADAPTERS_PKG}.{NEW_MODULE_NAME}')
        cls = mod.AcmeRealtimeAdapter

        from api_test_service.infrastructure.adapters import \
            vendor_adapter_registry
        # create_from_config 按 (HTTP, API_DRIVER) 精确命中演练适配器
        cfg = SimpleNamespace(
            id=1, meta={'vendor_adapter': 'api_driver'}, api_endpoints=[{'endpoint': 'http://x'}],
            adapter_class=None, vendor=None,
            proxy_type=None, proxy_url=None, max_timeout=30, protocol='http')
        adapter = vendor_adapter_registry.create_from_config(cfg, {})
        assert isinstance(adapter, cls)
        assert adapter.execute({})['asr'] == 'acme-asr'

    def test_registry_restored_to_default(self):
        """演练还原后注册表回到内置快照（不污染同进程其他用例）。"""
        from api_test_service.infrastructure.adapters import \
            vendor_adapter_registry
        names = {e['class'] for e in vendor_adapter_registry.list_adapters()}
        assert 'AcmeRealtimeAdapter' not in names
        assert DEFAULT_ADAPTER_NAMES <= names


class TestRegistrySemantics:
    """注册表语义复核（只读断言 / 独立配置）。"""

    def test_unknown_adapter_class_lists_registered(self):
        cfg = SimpleNamespace(
            id=1, meta={}, api_endpoints=[{'endpoint': 'http://x'}],
            adapter_class='Nope', vendor=None, proxy_type=None,
            proxy_url=None, max_timeout=30, protocol='http')
        from api_test_service.infrastructure.adapters import registry as reg
        with pytest.raises(ValueError, match='未注册'):
            reg._adapter_class_override(cfg, None)

    def test_vendor_mock_guard(self):
        from api_test_service.infrastructure.adapters import \
            vendor_adapter_registry
        cfg = SimpleNamespace(
            id=1, meta={}, api_endpoints=[{'endpoint': 'http://x'}],
            adapter_class=None, vendor='mock', proxy_type=None,
            proxy_url=None, max_timeout=30, protocol='http')
        adapter = vendor_adapter_registry.create_from_config(cfg, {})
        assert type(adapter).__name__ == 'MockVendorAdapter'
