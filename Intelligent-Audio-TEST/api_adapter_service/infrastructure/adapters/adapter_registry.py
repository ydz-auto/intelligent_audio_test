# -*- coding: utf-8 -*-
"""适配器注册表门面 — 委托 adapters/factory.APIAdapterFactory（UC-1003）。

注册表本体（(protocol, vendor) → 适配器类、adapter_class 显式通道、
注册冲突检测）在 adapters.factory.APIAdapterFactory；本类保留
infrastructure 层调用面，委托单例完成解析与实例化。
"""

from api_adapter_service.adapters.base import BaseAdapter
from api_adapter_service.adapters.factory import api_adapter_factory
from api_adapter_service.utils.logger import logger


class AdapterRegistry:
    """适配器注册表门面 — 委托 APIAdapterFactory 单例。"""

    def get_adapter(
        self, vendor: str, vendor_config: dict, is_dialog: bool = False
    ) -> BaseAdapter:
        """获取适配器实例（adapter_class 优先，未指定按 protocol+vendor）。"""
        adapter_cls = api_adapter_factory.resolve(vendor, vendor_config)
        logger.debug(f'AdapterRegistry: vendor={vendor} type={adapter_cls.__name__}')
        return api_adapter_factory.get_adapter(
            vendor, vendor_config, is_dialog=is_dialog
        )


# 单例
adapter_registry = AdapterRegistry()
