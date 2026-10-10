# -*- coding: utf-8 -*-
"""INT-72 验收测试 — UC-1003 OCP 实弹演练（测试工程师2）。

设计验收标准：新厂商适配器只新增一个子类文件，基类 / executor / 工厂
零改动（OCP），vendor 枚举化，注册即生效。

本文件真实地向 adapters 包写入一个新厂商子类模块（内部自注册），重载
包模拟服务重启（pkgutil 自动发现），验证 (protocol, vendor) 自动匹配与
adapter_class 显式类名通道都能命中新适配器；结束后完整还原（模块文件 /
sys.modules / 单例注册表），不污染同进程其他用例（如精确快照断言）。
"""
import hashlib
import importlib
import os
import sys

import pytest

# BaseConfig 导入期强校验（tests/conftest.py 已兜底 DATABASE_URL，此处补
# OSS 两键的进程级兜底；显式配置的环境变量不受影响）
os.environ.setdefault('OSS_ACCESS_KEY', 'ut-dummy-ak')
os.environ.setdefault('OSS_SECRET_KEY', 'ut-dummy-sk')

ADAPTERS_PKG = 'api_adapter_service.adapters'
NEW_MODULE_NAME = 'zz_acceptance_acme_adapter'
GUARDED_FILES = ('factory.py', 'base.py')

NEW_MODULE_SRC = f'''# -*- coding: utf-8 -*-
"""验收演练：模拟新厂商 Acme 仅新增一个子类文件即完成接入（UC-1003）。"""
from api_adapter_service.adapters.base import BaseAdapter
from api_adapter_service.adapters.factory import api_adapter_factory
from api_adapter_service.domain.enums import AdapterProtocol


class AcmeRealtimeAdapter(BaseAdapter):
    """UC-1003 演练厂商适配器（websocket 协议）。"""

    def send_request(self, task_id, session_id, input_type, input_data,
                     **kwargs):
        return {{
            'asr_text': 'acme-asr', 'trans_text': 'acme-trans',
            'output': 'acme-out', 'session_id': session_id,
            'latency': 0.0, 'raw_response': {{'vendor': 'acme'}},
        }}


api_adapter_factory.register(
    AdapterProtocol.WEBSOCKET, 'acme', AcmeRealtimeAdapter)
'''

DEFAULT_REGISTRY_SNAPSHOT = {
    '(http, default)': 'HttpAdapter',
    '(mock, mock)': 'MockDialogAdapter',
    '(sse, default)': 'SseAdapter',
    '(websocket, qwen)': 'QwenAdapter',
    '(websocket, volc_ast)': 'VolcAstAdapter',
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
        # 重载包 = 服务重启：__init__ 的 pkgutil 自动发现应导入新模块并自注册
        importlib.reload(pkg)
        yield pkg_dir, guarded_before
    finally:
        if os.path.exists(new_path):
            os.remove(new_path)
        sys.modules.pop(f'{ADAPTERS_PKG}.{NEW_MODULE_NAME}', None)
        importlib.invalidate_caches()
        importlib.reload(pkg)
        from api_adapter_service.adapters.factory import api_adapter_factory
        with api_adapter_factory._lock:
            api_adapter_factory._table.pop(('websocket', 'acme'), None)
            api_adapter_factory._by_name.pop('AcmeRealtimeAdapter', None)


class TestUC1003OCPDrill:
    """新厂商仅新增一个子类文件 → 注册即生效（验收标准逐条演练）。"""

    def test_new_vendor_single_file_zero_touch(self, acme_drill):
        pkg_dir, guarded_before = acme_drill
        # 基类 / 工厂零改动：写入新厂商文件前后哈希一致
        for name, digest in guarded_before.items():
            assert _file_hash(os.path.join(pkg_dir, name)) == digest, name

        from api_adapter_service.adapters.factory import api_adapter_factory
        mod = importlib.import_module(f'{ADAPTERS_PKG}.{NEW_MODULE_NAME}')
        cls = mod.AcmeRealtimeAdapter

        # (protocol, vendor) 自动匹配命中新厂商
        assert api_adapter_factory.resolve(
            'acme', {'protocol': 'websocket'}) is cls
        # 归一化：大小写 / 空白容错
        assert api_adapter_factory.resolve(
            ' ACME ', {'protocol': 'WebSocket'}) is cls
        # 实例化与调用可用
        adapter = api_adapter_factory.get_adapter(
            'acme', {'protocol': 'websocket'})
        assert isinstance(adapter, cls)
        assert adapter.send_request('t', 's', 'text', 'hi')['output'] == (
            'acme-out')

    def test_new_vendor_via_adapter_class_channel(self, acme_drill):
        """adapter_class 显式类名同样命中新厂商（通道零改动即对新类生效）。"""
        from api_adapter_service.adapters.factory import api_adapter_factory
        mod = importlib.import_module(f'{ADAPTERS_PKG}.{NEW_MODULE_NAME}')
        assert api_adapter_factory.resolve(
            'anything-else',
            {'protocol': 'http',
             'adapter_class': 'AcmeRealtimeAdapter'},
        ) is mod.AcmeRealtimeAdapter

    def test_registry_restored_to_default_snapshot(self):
        """演练还原后注册表回到五内置快照（不污染同进程其他用例）。"""
        from api_adapter_service.adapters.factory import api_adapter_factory
        assert api_adapter_factory.list_adapters() == (
            DEFAULT_REGISTRY_SNAPSHOT)


class TestRegistrySemantics:
    """注册表语义复核（独立工厂实例，不触碰单例）。"""

    def test_conflict_raises_and_idempotent_same_class(self):
        """同 (protocol, vendor) 注册不同实现 → 抛错；同类重复注册幂等。"""
        from api_adapter_service.adapters.base import BaseAdapter
        from api_adapter_service.adapters.factory import APIAdapterFactory
        from api_adapter_service.domain.enums import AdapterProtocol, Vendor

        factory = APIAdapterFactory()

        class FakeA(BaseAdapter):
            def send_request(self, **kwargs):
                return {}

        class FakeB(BaseAdapter):
            def send_request(self, **kwargs):
                return {}

        factory.register(AdapterProtocol.WEBSOCKET, Vendor.QWEN, FakeA)
        with pytest.raises(ValueError, match='适配器注册冲突'):
            factory.register(AdapterProtocol.WEBSOCKET, Vendor.QWEN, FakeB)
        # 同类重复注册幂等
        assert factory.register(
            AdapterProtocol.WEBSOCKET, Vendor.QWEN, FakeA) is FakeA

    def test_non_baseadapter_rejected(self):
        """非 BaseAdapter 子类禁止注册。"""
        from api_adapter_service.adapters.factory import APIAdapterFactory

        factory = APIAdapterFactory()
        with pytest.raises(TypeError, match='BaseAdapter'):
            factory.register('http', 'default', dict)

    def test_adapter_class_unknown_lists_registered(self):
        """adapter_class 拼错类名 → 明确报错并列出已注册类名。"""
        from api_adapter_service.adapters.factory import APIAdapterFactory, \
            api_adapter_factory  # 导入 factory 即触发父包自动发现与自注册

        with pytest.raises(ValueError, match='未注册'):
            APIAdapterFactory().resolve('qwen', {'protocol': 'sse',
                                                 'adapter_class': 'Nope'})
        assert 'Nope' not in api_adapter_factory._by_name

    def test_websocket_unregistered_rejected_no_silent_fallback(self):
        """websocket + 未登记 vendor 且未配 adapter_class → 拒绝静默降级。"""
        from api_adapter_service.adapters.factory import APIAdapterFactory

        with pytest.raises(ValueError, match='websocket'):
            APIAdapterFactory().get_adapter('doubao',
                                            {'protocol': 'websocket'})

    def test_vendor_alias_and_case_folding(self):
        """vendor 别名（volc→volc_ast / qwen3→qwen）与大小写归一化生效。"""
        from api_adapter_service.adapters.factory import api_adapter_factory  # 导入 factory 即触发父包自动发现与自注册

        # 只读使用单例（内置适配器注册在模块级单例上）
        assert api_adapter_factory.resolve(
            'volc', {'protocol': 'websocket'}).__name__ == 'VolcAstAdapter'
        assert api_adapter_factory.resolve(
            'Qwen3', {'protocol': 'websocket'}).__name__ == 'QwenAdapter'
