# -*- coding: utf-8 -*-
"""api_test_service 基础设施层 — 厂商适配器包（INT-62）。

厂商协议差异（报文格式、WS 帧协议、字段映射）唯一落位；执行链只经
vendor_adapter_registry 分发获取 Port 实例，禁止 import 本包内具体适配器
（具体实现模块仅供注册表装载与测试直接引用）。
"""
from api_test_service.infrastructure.adapters.registry import (
    VendorAdapterRegistry,
    adapter_type_from_config,
    register_vendor_adapter,
    vendor_adapter_registry,
)

# 内置适配器注册副作用（装饰器入表；实现类不经本包 __init__ 导出）
from api_test_service.infrastructure.adapters import api_driver_adapter  # noqa: F401
from api_test_service.infrastructure.adapters import mock_vendor_adapter  # noqa: F401

__all__ = [
    'VendorAdapterRegistry',
    'adapter_type_from_config',
    'register_vendor_adapter',
    'vendor_adapter_registry',
]
