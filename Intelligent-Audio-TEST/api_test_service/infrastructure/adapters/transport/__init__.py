# -*- coding: utf-8 -*-
"""api_test_service 传输层收拢包（INT-1168）。

按连接形态分区：非实时请求-响应（http_client，HTTP + 阻塞式 WS）
与实时长连接事件流（realtime_ws_client，Realtime 会话传输）。

- http_client.py        ← 原 adapters/api_client.py 迁入（APIClient / api_client / endpoint_protocol）
- realtime_ws_client.py ← 原厂商 WS 传输包文件迁入（RealtimeFrame / RealtimeWSClient）

上层（适配器 / 执行器）经本包统一导入传输件，不感知具体文件落位。
"""
from api_test_service.infrastructure.adapters.transport.http_client import (
    APIClient,
    api_client,
    endpoint_protocol,
)
from api_test_service.infrastructure.adapters.transport.realtime_ws_client import (
    RealtimeFrame,
    RealtimeWSClient,
)

__all__ = [
    'APIClient',
    'api_client',
    'endpoint_protocol',
    'RealtimeFrame',
    'RealtimeWSClient',
]
