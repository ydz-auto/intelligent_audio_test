# -*- coding: utf-8 -*-
"""api_test_service 基础设施层 — 厂商适配器包（INT-62 / INT-497）。

厂商协议差异（报文格式、WS 帧协议、字段映射）唯一落位；执行链只经
vendor_adapter_registry 分发获取 Port 实例，禁止 import 本包内具体适配器
（具体实现模块仅供注册表装载与测试直接引用）。

INT-497 三级体系：ApiVendorAdapter (Port) → 协议级 base → 品牌适配器；
注册表主 key (protocol, vendor) 与设备驱动注册表同构。目录按「协议 / 厂商 /
版本」三层组织（与 device_service/infrastructure/drivers 平台 / 应用 / 版本
同构），目录名即注册维度（ANY 记为 any），实现写在 v1/__init__.py：

- any/api_driver/v1     ApiDriverAdapter       (ANY, API_DRIVER)
- any/mock/v1           MockVendorAdapter      (ANY, MOCK)
- grpc/any/v1           GrpcAdapter            (GRPC, ANY)
- realtime/any/v1       RealtimeAdapterBase    (REALTIME, ANY) 协议级 base
- realtime/openai/v1    OpenAIRealtimeAdapter  (REALTIME, OPENAI) 品牌级
- websocket/any/v1      WebSocketAdapter       (WEBSOCKET, ANY)

传输件与公共工具：common/（proxy_utils / audio_input）、http/transport/v1
（http_client + sse_client）、grpc/transport/v1（grpc_client）、
realtime/transport/v1（realtime_ws_client）。
"""
from api_test_service.infrastructure.adapters.registry import (
    _ADAPTER_TYPE_CONFIG_KEY,
    VendorAdapterNotFoundError,
    VendorAdapterRegistry,
    VendorAdapterStatus,
    adapter_type_from_config,
    dimensions_from_config,
    infer_protocol,
    register_vendor_adapter,
    vendor_adapter_registry,
)

# 内置适配器注册副作用（装饰器入表）
from api_test_service.infrastructure.adapters.any.api_driver.v1 import (  # noqa: F401
    ApiDriverAdapter,
)
from api_test_service.infrastructure.adapters.any.mock.v1 import (  # noqa: F401
    MockVendorAdapter,
)
from api_test_service.infrastructure.adapters.grpc.any.v1 import GrpcAdapter  # noqa: F401
from api_test_service.infrastructure.adapters.realtime.any.v1 import (  # noqa: F401
    RealtimeAdapterBase,
)
from api_test_service.infrastructure.adapters.realtime.openai.v1 import (  # noqa: F401
    OpenAIRealtimeAdapter,
)
from api_test_service.infrastructure.adapters.websocket.any.v1 import (  # noqa: F401
    WebSocketAdapter,
)

__all__ = [
    'VendorAdapterNotFoundError',
    'VendorAdapterRegistry',
    'VendorAdapterStatus',
    'adapter_type_from_config',
    'dimensions_from_config',
    'infer_protocol',
    'register_vendor_adapter',
    'vendor_adapter_registry',
]
