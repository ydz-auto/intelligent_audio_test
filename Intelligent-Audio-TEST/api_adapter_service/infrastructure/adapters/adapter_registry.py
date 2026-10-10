# -*- coding: utf-8 -*-
"""适配器注册表：包装已有的 adapters/factory.py。

将领域层 AdapterSelector 推导出的“适配器类型标识”映射到
具体的 BaseAdapter 实例，委托给已有的 select_adapter 工厂函数。
"""

from typing import Dict

from api_adapter_service.adapters.base import BaseAdapter
from api_adapter_service.adapters.factory import select_adapter
from api_adapter_service.domain.services import AdapterSelector
from api_adapter_service.utils.logger import logger


class AdapterRegistry:
    """适配器注册表。

    职责：
    1. 由领域层 AdapterSelector 推导适配器类型；
    2. 委托已有 factory.select_adapter 完成实例化；
    3. （可选）缓存适配器实例。
    """

    def __init__(self):
        self._cache: Dict[str, BaseAdapter] = {}

    def get_adapter(
        self, vendor: str, vendor_config: dict, is_dialog: bool = False
    ) -> BaseAdapter:
        """获取适配器实例。"""
        # 领域层推导类型（用于日志/审计）
        adapter_type = AdapterSelector.select_adapter_type_from_dict(
            vendor, vendor_config
        )
        logger.debug(
            f'AdapterRegistry: vendor={vendor} type={adapter_type}'
        )
        # 委托已有工厂实例化
        return select_adapter(vendor, vendor_config, is_dialog=is_dialog)

    def clear_cache(self) -> None:
        """清空适配器缓存。"""
        self._cache.clear()


# 单例
adapter_registry = AdapterRegistry()
