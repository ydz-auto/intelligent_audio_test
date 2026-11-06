# -*- coding: utf-8 -*-
"""api_test_service 领域层 — 端口（Port）接口包。

DDD 六边形Ports & Adapters：上层（application/core 执行链）只依赖本包
定义的抽象接口，具体协议实现全部落在 infrastructure/adapters/，
经注册表（vendor_adapter_registry）分发获取。
"""
from api_test_service.domain.ports.api_vendor_adapter import ApiVendorAdapter

__all__ = ['ApiVendorAdapter']
