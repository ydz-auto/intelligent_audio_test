# -*- coding: utf-8 -*-
"""厂商适配器注册表 — 装饰器注册 + 枚举 key resolve + 配置化选择（INT-62）。

参照 device_service/infrastructure/drivers/registry.py 模式（简化：
无版本/平台维度，key = VendorAdapterType 单维）。

贡献者使用（新增厂商适配器三步，核心链路零改动）：
    1. shared/models/common_enums.py 新增 VendorAdapterType 枚举成员
    2. infrastructure/adapters/ 下实现 ApiVendorAdapter Port
    3. @register_vendor_adapter 装饰注册
    用例侧配置 vendor_adapter=<枚举值> 即分发（case_config 优先于 api meta）。

调度方使用（core/ 执行链，只见 Port）：
    adapter = vendor_adapter_registry.create_from_config(api_config, case_config)
    result = adapter.execute(context_data)
"""
import threading
import logging

from shared.models.common_enums import VendorAdapterType

from api_test_service.domain.ports import ApiVendorAdapter

logger = logging.getLogger(__name__)

DEFAULT_ADAPTER_TYPE = VendorAdapterType.API_DRIVER

_ADAPTER_TYPE_CONFIG_KEY = 'vendor_adapter'


class VendorAdapterRegistry:
    """厂商适配器注册表 — 执行链获取适配器的唯一入口

    Key = VendorAdapterType 枚举成员，同一 key 后注册覆盖先注册（告警）。
    线程安全：写操作加锁，读走 dict 快照。
    """

    def __init__(self):
        self._table: dict = {}
        self._lock = threading.RLock()

    def register(self, adapter_cls) -> type:
        """注册一个适配器类，可作为装饰器使用。

        校验 adapter_type 必须为 VendorAdapterType 枚举成员且继承 Port。
        """
        self._validate(adapter_cls)
        key = adapter_cls.adapter_type
        with self._lock:
            old = self._table.get(key)
            if old is not None and old is not adapter_cls:
                logger.warning("适配器覆盖: %s → %s (旧: %s)",
                               key, adapter_cls.__name__, old.__name__)
            self._table[key] = adapter_cls
        return adapter_cls

    def _validate(self, adapter_cls):
        if not (isinstance(adapter_cls, type) and issubclass(adapter_cls, ApiVendorAdapter)):
            raise TypeError(
                f"{adapter_cls!r} 不是 ApiVendorAdapter 子类，禁止注册")
        if not isinstance(getattr(adapter_cls, 'adapter_type', None), VendorAdapterType):
            raise TypeError(
                f"{adapter_cls.__name__} 缺少 adapter_type 类属性"
                f"（必须为 VendorAdapterType 枚举成员）")

    def unregister(self, adapter_type: VendorAdapterType):
        """注销一个适配器（测试/热更新用）"""
        with self._lock:
            return self._table.pop(adapter_type, None)

    def resolve(self, adapter_type: VendorAdapterType) -> type:
        """按枚举 key 解析适配器类，未注册抛 KeyError"""
        entry = self._table.get(adapter_type)
        if entry is None:
            raise KeyError(
                f"未注册的厂商适配器类型: {adapter_type}"
                f"（已注册: {[t.value for t in self._table]}）")
        return entry

    def create(self, adapter_type: VendorAdapterType, **kwargs) -> ApiVendorAdapter:
        """解析并实例化适配器（构造契约见 Port docstring）"""
        return self.resolve(adapter_type)(**kwargs)

    def create_from_config(self, api_config=None, case_config=None,
                           **kwargs) -> ApiVendorAdapter:
        """按用例配置解析类型并实例化（执行链标准入口）

        类型解析：case_config.vendor_adapter > api_config.meta.vendor_adapter
        > 默认 API_DRIVER；显式配置了未注册/不存在的类型立即报错
        （拒绝魔法字符串静默降级）。
        """
        return self.create(adapter_type_from_config(api_config, case_config),
                           api_config=api_config, case_config=case_config, **kwargs)

    def list_adapters(self) -> list:
        """列出已注册适配器自描述信息（调试/管理用）"""
        with self._lock:
            return [
                {
                    'adapter_type': cls.adapter_type.value,
                    'class': cls.__name__,
                    'module': cls.__module__,
                    'supported_protocols': [p.value for p in cls.supported_protocols],
                }
                for cls in self._table.values()
            ]


def adapter_type_from_config(api_config=None, case_config=None) -> VendorAdapterType:
    """用例配置 → 适配器类型枚举。

    优先级：case_config.vendor_adapter > api_config.meta.vendor_adapter
    > 默认 API_DRIVER。显式配置的未知值抛 ValueError。
    """
    raw = None
    if isinstance(case_config, dict):
        raw = case_config.get(_ADAPTER_TYPE_CONFIG_KEY)
    if raw is None and api_config is not None:
        raw = (getattr(api_config, 'meta', None) or {}).get(_ADAPTER_TYPE_CONFIG_KEY)
    if raw is None:
        return DEFAULT_ADAPTER_TYPE
    try:
        return VendorAdapterType(str(raw))
    except ValueError:
        raise ValueError(
            f"未知的 {_ADAPTER_TYPE_CONFIG_KEY} 配置: {raw!r}"
            f"（合法值: {[t.value for t in VendorAdapterType]}）")


# —— 模块级单例 ——

vendor_adapter_registry = VendorAdapterRegistry()


def register_vendor_adapter(adapter_cls=None, *,
                            registry: VendorAdapterRegistry = None):
    """装饰器：注册适配器到注册表

    用法:
        @register_vendor_adapter
        class MyAdapter(ApiVendorAdapter): ...

        @register_vendor_adapter(registry=custom_registry)
        class MyAdapter(ApiVendorAdapter): ...
    """
    reg = registry or vendor_adapter_registry

    def _wrap(cls):
        return reg.register(cls)

    if adapter_cls is not None:
        return _wrap(adapter_cls)
    return _wrap
