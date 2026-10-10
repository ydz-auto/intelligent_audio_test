# -*- coding: utf-8 -*-
"""APIAdapterFactory — 适配器注册表工厂（UC-1003，设计文档 04_类设计 §5.5）。

注册表形态（替代原 select_adapter if 链）：
- 具体适配器模块在自身底部调用 ``api_adapter_factory.register(protocol,
  vendor, adapter_cls)`` 自注册；adapters/__init__ 导入时自动发现包内
  模块 → 新增厂商只新增一个子类文件，基类 / executor / 工厂零改动（OCP）。
- ``get_adapter`` 优先按 ``vendor_config['adapter_class']`` 指定类名创建
  （UC-0901 apis.adapter_class 通道），未指定按 (protocol, vendor) 自动
  匹配；websocket 未注册抛 ValueError（拒绝静默降级），http/sse/mock
  未注册回退 default，最终回退 HttpAdapter。
- 同一 (protocol, vendor) 注册不同实现 → 注册期（服务启动）抛错，
  强制第二个实现改用显式 adapter_class 通道（UC-1003 扩展流程 5a）。
"""
import threading

from api_adapter_service.adapters.base import BaseAdapter
from api_adapter_service.domain.enums import (
    DEFAULT_REGISTRY_VENDOR,
    AdapterProtocol,
    Vendor,
    normalize_protocol,
    normalize_vendor,
)
from api_adapter_service.utils.logger import logger


class APIAdapterFactory:
    """适配器注册表 — (protocol, vendor) → 适配器类，线程安全。

    注册表键 (protocol, vendor) 均经 domain.enums 归一化（别名折叠、
    大小写容错），注册与自动匹配使用同一规则。
    """

    def __init__(self):
        self._table = {}    # (protocol, vendor) -> adapter 类
        self._by_name = {}  # 适配器类名 -> adapter 类（adapter_class 显式通道）
        self._lock = threading.RLock()

    def register(self, protocol, vendor, adapter_cls) -> type:
        """注册适配器类（新厂商子类文件的自注册入口）。

        同一 (protocol, vendor) 重复注册不同实现视为冲突，注册期抛错
        （UC-1003 扩展流程 5a）：第二个实现须使用独立注册键，并在 API
        配置中显式 adapter_class。类名通道同理：不同类同名注册会令
        adapter_class 解析到错误实现，注册期一并抛错。同类重复注册幂等
        （支持模块重导入）。
        """
        if not (isinstance(adapter_cls, type)
                and issubclass(adapter_cls, BaseAdapter)):
            raise TypeError(f'{adapter_cls!r} 不是 BaseAdapter 子类，禁止注册')
        protocol_key = normalize_protocol(protocol)
        vendor_key = normalize_vendor(vendor)
        with self._lock:
            existing = self._table.get((protocol_key, vendor_key))
            if existing is not None and existing is not adapter_cls:
                raise ValueError(
                    f'适配器注册冲突: ({protocol_key}, {vendor_key}) 已注册 '
                    f'{existing.__module__}.{existing.__name__}，拒绝 '
                    f'{adapter_cls.__module__}.{adapter_cls.__name__} —— '
                    f'同 (protocol, vendor) 多实现冲突，第二个实现请使用独立'
                    f'注册键并在 API 配置显式 adapter_class（UC-1003 扩展流程 5a）'
                )
            existing_by_name = self._by_name.get(adapter_cls.__name__)
            if (existing_by_name is not None
                    and existing_by_name is not adapter_cls):
                raise ValueError(
                    f'适配器类名注册冲突: 类名 {adapter_cls.__name__!r} 已注册 '
                    f'{existing_by_name.__module__}.{existing_by_name.__name__}，'
                    f'拒绝 {adapter_cls.__module__}.{adapter_cls.__name__} —— '
                    f'adapter_class 通道按类名解析，同名类会命中错误实现，'
                    f'请重命名类'
                )
            self._table[(protocol_key, vendor_key)] = adapter_cls
            self._by_name[adapter_cls.__name__] = adapter_cls
        logger.debug(
            f'APIAdapterFactory: registered ({protocol_key}, {vendor_key}) '
            f'-> {adapter_cls.__name__}'
        )
        return adapter_cls

    def get_adapter(self, vendor, vendor_config,
                    is_dialog: bool = False) -> BaseAdapter:
        """选择并实例化适配器。

        优先级：vendor_config['adapter_class'] 显式类名（UC-0901/UC-1003
        步骤 5）> (protocol, vendor) 自动匹配。is_dialog 为现有调用契约
        参数（会话型适配器内部按 vendor_config.session 生效）。
        """
        adapter_cls = self.resolve(vendor, vendor_config)
        logger.info(f'Using {adapter_cls.__name__} for vendor={vendor}')
        return adapter_cls(vendor_config or {})

    def resolve(self, vendor, vendor_config) -> type:
        """仅解析适配器类，不实例化（审计/日志与测试用）。"""
        vendor_config = vendor_config or {}
        adapter_class_name = vendor_config.get('adapter_class')
        if adapter_class_name:
            with self._lock:
                cls = self._by_name.get(str(adapter_class_name))
                registered = sorted(self._by_name)
            if cls is None:
                raise ValueError(
                    f"adapter_class {adapter_class_name!r} 未注册"
                    f"（已注册: {registered}）"
                )
            return cls
        return self._resolve_by_key(vendor, vendor_config)

    def _resolve_by_key(self, vendor, vendor_config) -> type:
        """(protocol, vendor) 自动匹配（UC-1003 步骤 5 'vendor 自动匹配'）。"""
        protocol_key = normalize_protocol(vendor_config.get('protocol'))
        vendor_key = normalize_vendor(vendor)
        if vendor_key == Vendor.MOCK.value:
            protocol_key = AdapterProtocol.MOCK.value
        with self._lock:
            cls = (
                self._table.get((protocol_key, vendor_key))
                or self._table.get((protocol_key, DEFAULT_REGISTRY_VENDOR))
            )
            if cls is not None:
                return cls
            if protocol_key == AdapterProtocol.WEBSOCKET.value:
                registered = sorted(self._table)
                raise ValueError(
                    f'websocket 协议 vendor={vendor!r} 未注册适配器'
                    f'（已注册: {registered}）—— 请在 API 配置显式 adapter_class'
                )
            fallback = self._table[
                (AdapterProtocol.HTTP.value, DEFAULT_REGISTRY_VENDOR)
            ]
        logger.warning(
            f'Unknown vendor={vendor}, protocol={protocol_key}, '
            f'defaulting to {fallback.__name__}'
        )
        return fallback

    def list_adapters(self) -> dict:
        """列出注册表快照（调试/诊断用）。"""
        with self._lock:
            return {
                f'({protocol}, {vendor})': cls.__name__
                for (protocol, vendor), cls in sorted(self._table.items())
            }


# 模块级单例（设计文档 §5.5）
api_adapter_factory = APIAdapterFactory()
