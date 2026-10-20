# -*- coding: utf-8 -*-
"""适配器协议级 base 子包（INT-497）— 三级体系第二级。

协议级 base 只定义协议通用生命周期与同形方法面，品牌差异落在 vendors/ 子包。
"""
from api_test_service.infrastructure.adapters.protocol.realtime_adapter_base import (
    RealtimeAdapterBase,
)

__all__ = ['RealtimeAdapterBase']
