# -*- coding: utf-8 -*-
"""HTTP 传输件 v1 — 非实时请求-响应与流式事件流统一导入面。

- http_client：APIClient / api_client / endpoint_protocol（HTTP + 阻塞式 WS）
- sse_client：HttpStreamClient 与 EVENT_* 归一事件常量（HTTP 流式）
"""
from api_test_service.infrastructure.adapters.http.transport.v1.http_client import (
    APIClient,
    api_client,
    endpoint_protocol,
)
from api_test_service.infrastructure.adapters.http.transport.v1.sse_client import (
    EVENT_END_STREAM,
    EVENT_ERROR,
    EVENT_HEARTBEAT,
    EVENT_MESSAGE,
    HttpStreamClient,
)

__all__ = [
    'APIClient',
    'api_client',
    'endpoint_protocol',
    'HttpStreamClient',
    'EVENT_MESSAGE',
    'EVENT_ERROR',
    'EVENT_END_STREAM',
    'EVENT_HEARTBEAT',
]
