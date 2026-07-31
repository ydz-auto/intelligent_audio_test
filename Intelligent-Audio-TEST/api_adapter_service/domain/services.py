# -*- coding: utf-8 -*-
"""领域服务：AdapterSelector — 根据纯领域逻辑选择适配器类型。"""

from api_adapter_service.domain.value_objects import VendorConfig


class AdapterSelector:
    """适配器选择器（纯领域逻辑）。

    根据 vendor + protocol 推导出适配器类型标识。
    不负责实例化适配器（实例化由 infrastructure 层完成）。
    """

    @staticmethod
    def select_adapter_type(vendor: str, vendor_config: VendorConfig) -> str:
        """返回适配器类型标识字符串。

        Returns:
            'mock' | 'http' | 'sse' | 'volc_ast' | 'qwen' | 'http'(default)
        """
        protocol = vendor_config.protocol

        if vendor == 'mock' or protocol == 'mock':
            return 'mock'

        if protocol == 'http':
            return 'http'

        if protocol == 'sse':
            return 'sse'

        if protocol == 'websocket' and vendor in ('volc_ast', 'volc'):
            return 'volc_ast'

        if protocol == 'websocket' and vendor in ('qwen', 'qwen3'):
            return 'qwen'

        # default
        return 'http'

    @staticmethod
    def select_adapter_type_from_dict(
        vendor: str, vendor_config_dict: dict
    ) -> str:
        """从原始 dict 配置推导适配器类型。"""
        config = VendorConfig(
            vendor=vendor,
            protocol=vendor_config_dict.get('protocol', ''),
            config=vendor_config_dict,
        )
        return AdapterSelector.select_adapter_type(vendor, config)
