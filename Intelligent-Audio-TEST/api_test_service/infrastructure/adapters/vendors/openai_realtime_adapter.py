# -*- coding: utf-8 -*-
"""OpenAI Realtime 品牌适配器（INT-497）— 三级体系第三级。

继承 RealtimeAdapterBase（协议级 base，组合复用 RealtimeWSClient 传输/状态机），
仅声明品牌维度；生命周期（initialize → pre_process → send → recv → post_process
→ teardown）与 RealtimeWSClient 同形方法面全部继承基类，厂商字段解读差异
（事件归一化等）由 RealtimeWSClient 防腐层承载，本层为注册键与品牌声明。

注册键 (AdapterProtocol.REALTIME, AdapterVendor.OPENAI)，用例配置
vendor_adapter='openai_realtime' / 'openai' 在 websocket_api 路径分发到本适配器
（RealtimeSessionExecutor 最小接线，方案审计 2026-10-16 拍板第 5 项）。
"""
from __future__ import annotations

from shared.models.common_enums import AdapterProtocol, AdapterVendor, VendorAdapterType

from api_test_service.infrastructure.adapters.protocol.realtime_adapter_base import (
    RealtimeAdapterBase,
)
from api_test_service.infrastructure.adapters.registry import register_vendor_adapter


@register_vendor_adapter
class OpenAIRealtimeAdapter(RealtimeAdapterBase):
    """OpenAI Realtime 品牌适配器 — 厂商维度声明，行为继承协议级 base。"""

    protocol = AdapterProtocol.REALTIME
    vendor = AdapterVendor.OPENAI
    adapter_type = VendorAdapterType.OPENAI_REALTIME  # 用例配置扁平 key 兼容层
    display_name = 'OpenAI Realtime 适配器'

    # OpenAI Realtime 事件协议（RealtimeWSClient 归一化表默认覆盖，显式钉死）
    _transport_vendor = 'openai'
