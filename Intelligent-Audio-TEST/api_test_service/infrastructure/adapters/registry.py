# -*- coding: utf-8 -*-
"""厂商适配器注册表 — 装饰器注册 + 多维 key resolve + 依赖检测 + 热更新（INT-62 / INT-497）。

INT-497 起与 device_service/infrastructure/drivers/registry.py 同构（方案审计
2026-10-16 拍板）：注册表主 key 升级为 (AdapterProtocol, AdapterVendor) 多维，
支持依赖检测（AVAILABLE / MISSING_DEPENDENCY）、resolve 精确→同协议基线兜底→抛错、
热更新（unregister_module / reload_module）、list 自描述；`VendorAdapterType`
保留为用例配置 `vendor_adapter` 扁平 key 兼容层，`create_from_config` 先由配置
推断协议维度，再 (protocol, vendor) 精确→兜底解析（向后兼容：既有 API_DRIVER /
MOCK 注册与 create_from_config 行为不变）。

三级体系：ApiVendorAdapter (Port) → protocol/RealtimeAdapterBase（协议级 base，
protocol=REALTIME）→ vendors/OpenAIRealtimeAdapter（品牌级，protocol=REALTIME,
vendor=OPENAI）。协议细节只允许出现在 infrastructure/adapters/ 具体实现中，
执行链只经 vendor_adapter_registry 分发获取 Port 实例。

贡献者使用（新增厂商适配器三步，核心链路零改动）：
    1. shared/models/common_enums.py 新增 AdapterProtocol/AdapterVendor 维度
       （或 VendorAdapterType 扁平 key）
    2. infrastructure/adapters/ 下实现 ApiVendorAdapter Port
    3. @register_vendor_adapter 装饰注册
    用例侧配置 vendor_adapter=<扁平 key> 即分发（case_config 优先于 api meta）。

调度方使用（core/ 执行链，只见 Port）：
    adapter = vendor_adapter_registry.create_from_config(api_config, case_config)
    result = adapter.execute(context_data)
"""
import importlib
import importlib.util
import logging
import threading
from enum import Enum
from typing import Optional, Tuple

from shared.models.common_enums import (
    AdapterProtocol,
    AdapterVendor,
    VendorAdapterType,
)

from api_test_service.domain.entities.api import resolve_api_endpoint
from api_test_service.domain.ports import ApiVendorAdapter

logger = logging.getLogger(__name__)

DEFAULT_ADAPTER_TYPE = VendorAdapterType.API_DRIVER

_ADAPTER_TYPE_CONFIG_KEY = 'vendor_adapter'
_PROTOCOL_CONFIG_KEY = 'protocol'


class VendorAdapterStatus(str, Enum):
    """适配器运行状态 — 供注册表与管理界面使用（INT-497，与驱动 DriverStatus 同构）"""
    AVAILABLE = 'available'
    MISSING_DEPENDENCY = 'missing_dependency'


class VendorAdapterNotFoundError(Exception):
    """请求的适配器不存在或依赖缺失"""

    def __init__(self, protocol: AdapterProtocol, vendor: AdapterVendor,
                 reason: str = ''):
        self.protocol = protocol
        self.vendor = vendor
        self.reason = reason
        super().__init__(
            f"未注册的厂商适配器: (protocol={protocol.value!r}, vendor={vendor.value!r})"
            + (f" — {reason}" if reason else "")
        )


# 扁平 key → 多维 key 映射。protocol=None 表示由配置推断（遗留 API_DRIVER/MOCK
# 无协议强绑定；OPENAI 首期仅 REALTIME 落地，协议维度固定）。
_FLAT_KEY_DIMENSIONS = {
    VendorAdapterType.API_DRIVER: (None, AdapterVendor.API_DRIVER),
    VendorAdapterType.MOCK: (None, AdapterVendor.MOCK),
    VendorAdapterType.OPENAI: (AdapterProtocol.REALTIME, AdapterVendor.OPENAI),
    VendorAdapterType.OPENAI_REALTIME: (AdapterProtocol.REALTIME, AdapterVendor.OPENAI),
}

# adapter_class 显式通道（INT-1169/1176，决策 a：保留列 + 内嵌映射 + 显式校验）。
# 存量值仅 MockDialogAdapter（主库/隔离库均 deleted 冒烟残留）→ 映射
# vendor_adapter='mock'；未知值报错，拒绝静默降级到 API_DRIVER（对齐独立服务
# factory.py:103-106 显式报错语义）。旧文档类名（HttpAPIAdapter 等）从未落地
# 可解析类，仅文档回写不建映射。
_ADAPTER_CLASS_MAPPING = {
    'MockDialogAdapter': VendorAdapterType.MOCK,
}


def _resolve_adapter_class(api_config=None, case_config=None):
    """解析用例配置 adapter_class（apis.adapter_class 列 + case 级覆盖）。"""
    raw = None
    if isinstance(case_config, dict):
        raw = case_config.get('adapter_class')
    if raw is None and api_config is not None:
        raw = getattr(api_config, 'adapter_class', None)
    return str(raw) if raw is not None else None


def _adapter_class_override(api_config=None, case_config=None):
    """adapter_class → 内嵌扁平 key；未知类名显式报错（拒绝静默降级）。"""
    raw = _resolve_adapter_class(api_config, case_config)
    if raw is None:
        return None
    mapped = _ADAPTER_CLASS_MAPPING.get(raw)
    if mapped is None:
        raise ValueError(
            f"adapter_class {raw!r} 未注册"
            f"（已注册: {sorted(_ADAPTER_CLASS_MAPPING)}）—— "
            f"未知适配器类名禁止静默降级到 API_DRIVER")
    return mapped


def _vendor_mock_guard(api_config=None, case_config=None) -> bool:
    """vendor='mock' 且无 adapter_class / vendor_adapter 时兜底 MOCK。

    INT-1170 审计非阻塞项 3：现 dimensions_from_config 不读 vendor 字段，
    vendor='mock' 且无显式 adapter_class/vendor_adapter 的配置会静默落到
    API_DRIVER（直发首端点 /chat），与 mock 厂商语义不符——此处兜底映射。
    """
    vendor = None
    if isinstance(case_config, dict):
        vendor = case_config.get('vendor')
    if vendor is None and api_config is not None:
        vendor = getattr(api_config, 'vendor', None)
    return str(vendor or '').strip().lower() == 'mock'


def _has_explicit_vendor_adapter(api_config=None, case_config=None) -> bool:
    """是否显式配置了 vendor_adapter（case_config > api_config.meta）。"""
    raw = None
    if isinstance(case_config, dict):
        raw = case_config.get(_ADAPTER_TYPE_CONFIG_KEY)
    if raw is None and api_config is not None:
        raw = (getattr(api_config, 'meta', None) or {}).get(_ADAPTER_TYPE_CONFIG_KEY)
    return raw is not None


def _check_dependencies(dependencies: list) -> Tuple[bool, str]:
    """检测依赖包是否可用

    Returns:
        (is_available, missing_module_name)
    """
    for dep in dependencies or []:
        try:
            if importlib.util.find_spec(dep) is None:
                return False, dep
        except (ImportError, ValueError):
            return False, dep
    return True, ""


def _coerce_protocol(value) -> AdapterProtocol:
    if isinstance(value, AdapterProtocol):
        return value
    if isinstance(value, str):
        try:
            return AdapterProtocol(value)
        except ValueError:
            raise KeyError(f"未知的协议维度: {value!r}（合法值: {[p.value for p in AdapterProtocol]}）")
    raise KeyError(f"协议维度必须为 AdapterProtocol 枚举成员: {value!r}")


def _coerce_vendor(value) -> AdapterVendor:
    if isinstance(value, AdapterVendor):
        return value
    if isinstance(value, str):
        try:
            return AdapterVendor(value)
        except ValueError:
            raise KeyError(f"未知的品牌维度: {value!r}（合法值: {[v.value for v in AdapterVendor]}）")
    raise KeyError(f"品牌维度必须为 AdapterVendor 枚举成员: {value!r}")


class VendorAdapterEntry:
    """注册表中单个适配器条目"""

    def __init__(self, adapter_cls, protocol: AdapterProtocol, vendor: AdapterVendor,
                 status: VendorAdapterStatus, missing_dep: str = '',
                 module_name: str = ''):
        self.adapter_cls = adapter_cls
        self.protocol = protocol
        self.vendor = vendor
        self.display_name = getattr(adapter_cls, 'display_name', adapter_cls.__name__)
        self.dependencies: list = list(getattr(adapter_cls, 'dependencies', []))
        self.status = status
        self.missing_dep = missing_dep
        self.module_name = module_name or adapter_cls.__module__

    @property
    def is_available(self) -> bool:
        return self.status == VendorAdapterStatus.AVAILABLE

    def to_dict(self) -> dict:
        """自描述信息（供管理界面/调试/测试断言用）"""
        a_type = getattr(self.adapter_cls, 'adapter_type', None)
        return {
            'protocol': self.protocol.value,
            'vendor': self.vendor.value,
            'adapter_type': a_type.value if isinstance(a_type, VendorAdapterType) else None,
            'display_name': self.display_name,
            'status': self.status.value,
            'missing_dependency': self.missing_dep or None,
            'dependencies': self.dependencies,
            'supported_protocols': [p.value for p in getattr(
                self.adapter_cls, 'supported_protocols', [])],
            'module': self.module_name,
            'class': self.adapter_cls.__name__,
        }


def _dimensions_of(adapter_cls) -> Tuple[AdapterProtocol, AdapterVendor]:
    """类属性 → 注册表多维 key。

    新式适配器声明 protocol / vendor（协议级 base 与品牌适配器）；
    遗留适配器仅声明 adapter_type（协议维度取通配 ANY）。
    """
    proto = getattr(adapter_cls, 'protocol', AdapterProtocol.ANY)
    vendor = getattr(adapter_cls, 'vendor', AdapterVendor.ANY)
    a_type = getattr(adapter_cls, 'adapter_type', None)

    if proto is AdapterProtocol.ANY and vendor is AdapterVendor.ANY:
        # 遗留单维注册：仅 adapter_type
        if isinstance(a_type, VendorAdapterType):
            p, v = _FLAT_KEY_DIMENSIONS[a_type]
            return p or AdapterProtocol.ANY, v
        raise TypeError(
            f"{adapter_cls.__name__} 缺少注册维度：请声明 adapter_type "
            f"（VendorAdapterType 枚举成员，遗留单维）或 protocol/vendor "
            f"（AdapterProtocol/AdapterVendor 枚举成员，多维注册）")
    if not isinstance(proto, AdapterProtocol):
        raise TypeError(
            f"{adapter_cls.__name__}.protocol 必须为 AdapterProtocol 枚举成员，"
            f"而不是 {type(proto).__name__}")
    if not isinstance(vendor, AdapterVendor):
        raise TypeError(
            f"{adapter_cls.__name__}.vendor 必须为 AdapterVendor 枚举成员，"
            f"而不是 {type(vendor).__name__}")
    return proto, vendor


class VendorAdapterRegistry:
    """厂商适配器注册表 — 执行链获取适配器的唯一入口

    Key = (AdapterProtocol, AdapterVendor) 二元组，同一 key 后注册覆盖先注册（告警）。
    线程安全：写操作加锁，读走 dict 快照。
    """

    def __init__(self):
        self._table: dict[tuple, VendorAdapterEntry] = {}
        self._lock = threading.RLock()

    # —— 注册 ——

    def register(self, adapter_cls) -> type:
        """注册一个适配器类，可作为装饰器使用。

        校验继承 Port 且声明注册维度；自动检测依赖，缺失时标记为
        MISSING_DEPENDENCY 但仍注册（供 list_adapters 展示）。
        """
        self._validate(adapter_cls)
        protocol, vendor = _dimensions_of(adapter_cls)
        deps = getattr(adapter_cls, 'dependencies', [])
        is_ok, missing = _check_dependencies(deps)
        status = VendorAdapterStatus.AVAILABLE if is_ok else VendorAdapterStatus.MISSING_DEPENDENCY
        entry = VendorAdapterEntry(adapter_cls, protocol, vendor, status, missing,
                                   module_name=adapter_cls.__module__)
        key = (protocol, vendor)
        with self._lock:
            old = self._table.get(key)
            if old is not None and old.adapter_cls is not adapter_cls:
                logger.warning("适配器覆盖: %s → %s (旧: %s)",
                               key, adapter_cls.__name__, old.adapter_cls.__name__)
            self._table[key] = entry
        return adapter_cls

    def _validate(self, adapter_cls):
        if not (isinstance(adapter_cls, type) and issubclass(adapter_cls, ApiVendorAdapter)):
            raise TypeError(
                f"{adapter_cls!r} 不是 ApiVendorAdapter 子类，禁止注册")
        # 维度完整性校验（_dimensions_of 同时承担取值）
        _dimensions_of(adapter_cls)

    # —— 注销 ——

    def unregister(self, protocol, vendor=None) -> Optional[VendorAdapterEntry]:
        """注销一个适配器（测试/热更新用）。

        单参 vendor=None 时为 VendorAdapterType 扁平 key 兼容注销。
        """
        if vendor is None:
            protocol, vendor = self._flat_key_to_dimensions(protocol)
        key = (_coerce_protocol(protocol), _coerce_vendor(vendor))
        with self._lock:
            entry = self._table.pop(key, None)
        if entry:
            logger.info("适配器注销: %s (%s)", key, entry.adapter_cls.__name__)
        return entry

    def unregister_module(self, module_name: str) -> list:
        """移除指定模块注册的所有适配器（热删整个文件）。"""
        removed = []
        with self._lock:
            keys_to_remove = [
                key for key, entry in self._table.items()
                if entry.module_name == module_name
            ]
            for key in keys_to_remove:
                removed.append(self._table.pop(key))
        if removed:
            logger.info("按模块注销 %d 个适配器: %s", len(removed), module_name)
        return removed

    # —— 热重载 ——

    def reload_module(self, module_name: str) -> list:
        """热重载一个适配器模块（热改）。

        流程:
            1. 先注销该模块的旧适配器
            2. importlib.reload 重新加载模块
            3. 扫描 reload 后的模块中所有带 @register_vendor_adapter 标记的类
               （reload 会自动触发装饰器重新注册）
        """
        with self._lock:
            old_entries = self.unregister_module(module_name)
            try:
                mod = importlib.import_module(module_name)
                mod = importlib.reload(mod)
            except Exception as e:
                for entry in old_entries:
                    self._table[(entry.protocol, entry.vendor)] = entry
                logger.error("模块 %s reload 失败，已恢复旧适配器: %s", module_name, e)
                raise
            new_entries = [
                entry for entry in self._table.values()
                if entry.module_name == module_name
            ]
        logger.info(
            "模块 %s 热重载完成: 旧 %d 个 → 新 %d 个",
            module_name, len(old_entries), len(new_entries))
        return new_entries

    # —— 查询（无锁，走 dict 快照）——

    def _flat_key_to_dimensions(self, adapter_type) -> Tuple[AdapterProtocol, AdapterVendor]:
        if not isinstance(adapter_type, VendorAdapterType):
            try:
                adapter_type = VendorAdapterType(str(adapter_type))
            except ValueError:
                raise KeyError(f"未知的厂商适配器扁平 key: {adapter_type!r}")
        if adapter_type not in _FLAT_KEY_DIMENSIONS:
            raise KeyError(f"扁平 key {adapter_type!r} 未映射到多维 key")
        protocol, vendor = _FLAT_KEY_DIMENSIONS[adapter_type]
        return protocol or AdapterProtocol.ANY, vendor

    def resolve(self, protocol, vendor=None, *, fallback: bool = True) -> type:
        """精确匹配 → 同协议基线兜底 → 抛错（与驱动 registry resolve 同构）

        Args:
            protocol: AdapterProtocol 维度；vendor 缺省时视为 VendorAdapterType
                扁平 key（遗留单维调用兼容）。
            vendor: AdapterVendor 维度。
            fallback: 精确未命中时是否兜底（同协议基线 → 遗留通配协议 → 全局默认）。
                显式配置 REALTIME 品牌适配器的接线路径传 fallback=False（防静默
                回退 RealtimeWSClient 的双通道语义歧义，方案审计 2026-10-16 裁定）。

        Returns:
            适配器类（type，未实例化）
        """
        if vendor is None:
            protocol, vendor = self._flat_key_to_dimensions(protocol)
        protocol = _coerce_protocol(protocol)
        vendor = _coerce_vendor(vendor)

        # 1. 精确匹配
        entry = self._table.get((protocol, vendor))
        if entry is not None and entry.is_available:
            return entry.adapter_cls

        if fallback:
            # 2. 同协议基线兜底（协议级 base 默认实现，如 (REALTIME, ANY)）
            baseline = self._table.get((protocol, AdapterVendor.ANY))
            if baseline is not None and baseline.is_available:
                return baseline.adapter_cls
            # 3. 遗留通配协议兜底（仅 adapter_type 的旧适配器，如 (ANY, MOCK)）
            legacy = self._table.get((AdapterProtocol.ANY, vendor))
            if legacy is not None and legacy.is_available:
                return legacy.adapter_cls
            # 4. 全局默认兜底（(ANY, ANY)）
            default = self._table.get((AdapterProtocol.ANY, AdapterVendor.ANY))
            if default is not None and default.is_available:
                return default.adapter_cls

        reason = ''
        probe = entry or self._table.get((protocol, AdapterVendor.ANY)) \
            or self._table.get((AdapterProtocol.ANY, vendor))
        if probe is not None and not probe.is_available:
            reason = f"依赖缺失: {probe.missing_dep}"
        else:
            reason = f"无可用适配器实现（已注册: {self._registered_keys()}）"
        raise VendorAdapterNotFoundError(protocol, vendor, reason=reason)

    def resolve_for(self, protocol, adapter_type, *, fallback: bool = False) -> Optional[type]:
        """表驱动分发入口：扁平 key 在该协议下有映射 → 严格 resolve；无映射 → None。

        INT-1299 分发表驱动化（替代 if/else 白名单）：执行链按当前协议查
        _FLAT_KEY_DIMENSIONS 扁平 key 映射，命中协议维度即 resolve
        （fallback=False——显式配置了 REALTIME 品牌却回退默认传输对象会造成
        双通道语义歧义，方案审计 2026-10-16 拍板）；未映射（未配置 / 默认
        API_DRIVER / 协议不匹配 / 未知扁平 key）返回 None，由调用方保持默认
        构造（向后兼容）。新增厂商从此只加枚举 + 映射一行 + 注册类，调用方零改动。

        Args:
            protocol: AdapterProtocol 维度（执行链当前协议）。
            adapter_type: VendorAdapterType 扁平 key（或等值字符串）。
            fallback: 透传 resolve 兜底开关（默认 False，严格分发）。

        Returns:
            适配器类（type）；该协议下无映射 → None。
        """
        if not isinstance(adapter_type, VendorAdapterType):
            try:
                adapter_type = VendorAdapterType(str(adapter_type))
            except ValueError:
                return None
        dims = _FLAT_KEY_DIMENSIONS.get(adapter_type)
        if dims is None:
            return None
        mapped_protocol, vendor = dims
        protocol = _coerce_protocol(protocol)
        if mapped_protocol is None or mapped_protocol != protocol:
            return None
        return self.resolve(protocol, vendor, fallback=fallback)

    def get_by_key(self, protocol, vendor) -> Optional[VendorAdapterEntry]:
        """精确查一个条目（不降级），返回原始 entry"""
        return self._table.get((_coerce_protocol(protocol), _coerce_vendor(vendor)))

    def is_available(self, protocol, vendor) -> bool:
        """检查适配器是否可用"""
        entry = self.get_by_key(protocol, vendor)
        return entry is not None and entry.is_available

    def _registered_keys(self) -> list:
        return [(p.value, v.value) for (p, v) in self._table.keys()]

    # —— 实例化 ——

    def create(self, protocol, vendor=None, **kwargs) -> ApiVendorAdapter:
        """解析并实例化适配器（构造契约见 Port docstring）"""
        return self.resolve(protocol, vendor)(**kwargs)

    def create_from_config(self, api_config=None, case_config=None,
                           **kwargs) -> ApiVendorAdapter:
        """按用例配置解析类型并实例化（执行链标准入口）

        类型解析：case_config.vendor_adapter > api_config.meta.vendor_adapter
        > 默认 API_DRIVER；协议维度由配置显式 protocol > endpoint 前缀推断；
        显式配置了未注册/不存在的类型立即报错（拒绝魔法字符串静默降级）。
        """
        protocol, vendor = dimensions_from_config(api_config, case_config)
        return self.create(protocol, vendor,
                           api_config=api_config, case_config=case_config, **kwargs)

    def list_adapters(self) -> list:
        """列出已注册适配器自描述信息（调试/管理/测试用）"""
        with self._lock:
            return [entry.to_dict() for entry in self._table.values()]

    def list_available(self, protocol: Optional[AdapterProtocol] = None) -> list:
        """列出可用适配器"""
        with self._lock:
            return [
                entry.to_dict()
                for entry in self._table.values()
                if entry.is_available
                and (protocol is None or entry.protocol == protocol)
            ]

    def get_adapter_classes(self) -> list:
        """返回已注册的适配器类，供运行时统一实例化。"""
        with self._lock:
            return [entry.adapter_cls for entry in self._table.values()]


def adapter_type_from_config(api_config=None, case_config=None) -> VendorAdapterType:
    """用例配置 → 适配器类型扁平 key（VendorAdapterType 兼容层）。

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


def _resolve_endpoint(api_config) -> str:
    """解析候选端点（api_endpoints 首个非空 endpoint，INT-1361 起唯一来源）用于协议前缀推断"""
    return resolve_api_endpoint(api_config)


def infer_protocol(api_config=None, case_config=None) -> AdapterProtocol:
    """推断协议维度：显式 protocol 配置 > endpoint 前缀 > 默认 HTTP。

    case_config.protocol / api_config.meta.protocol 显式值优先（拒绝魔法字符串，
    未知值报错）；否则按 endpoint 前缀 ws://wss:// → WEBSOCKET、http(s):// → HTTP。
    """
    raw = None
    if isinstance(case_config, dict):
        raw = case_config.get(_PROTOCOL_CONFIG_KEY)
    if raw is None and api_config is not None:
        raw = (getattr(api_config, 'meta', None) or {}).get(_PROTOCOL_CONFIG_KEY)
    if raw is not None:
        try:
            return AdapterProtocol(str(raw))
        except ValueError:
            raise ValueError(
                f"未知的 {_PROTOCOL_CONFIG_KEY} 配置: {raw!r}"
                f"（合法值: {[p.value for p in AdapterProtocol]}）")
    url = _resolve_endpoint(api_config)
    if url.startswith(('ws://', 'wss://')):
        return AdapterProtocol.WEBSOCKET
    return AdapterProtocol.HTTP


def dimensions_from_config(api_config=None, case_config=None) -> Tuple[AdapterProtocol, AdapterVendor]:
    """用例配置 → 注册表多维 key (protocol, vendor)。

    扁平 key 取 adapter_type_from_config（case_config.vendor_adapter >
    api_config.meta.vendor_adapter > API_DRIVER）；OPENAI / OPENAI_REALTIME
    协议维度固定 REALTIME（首期），其余按 infer_protocol 推断。

    INT-1169/1176 扩展：
    - adapter_class 显式通道优先（存量 MockDialogAdapter → MOCK，未知报错）；
    - vendor='mock' 且无 adapter_class/vendor_adapter 时兜底 MOCK（防静默
      落到 API_DRIVER 的守卫，INT-1170 审计项 3）。
    """
    a_type = adapter_type_from_config(api_config, case_config)
    override = _adapter_class_override(api_config, case_config)
    if override is not None:
        a_type = override
    elif (_vendor_mock_guard(api_config, case_config)
          and not _has_explicit_vendor_adapter(api_config, case_config)):
        a_type = VendorAdapterType.MOCK
    protocol, vendor = _FLAT_KEY_DIMENSIONS[a_type]
    if protocol is None:
        protocol = infer_protocol(api_config, case_config)
    return protocol, vendor


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
