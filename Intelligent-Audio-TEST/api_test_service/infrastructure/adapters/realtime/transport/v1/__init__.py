# -*- coding: utf-8 -*-
"""Realtime 传输件 v1 — 实时长连接事件流统一导入面。

realtime_ws_client：RealtimeWSClient 会话传输/状态机与 RealtimeFrame 帧模型。
"""
from api_test_service.infrastructure.adapters.realtime.transport.v1.realtime_ws_client import (
    RealtimeFrame,
    RealtimeWSClient,
)

__all__ = [
    'RealtimeFrame',
    'RealtimeWSClient',
]
