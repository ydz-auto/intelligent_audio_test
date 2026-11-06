# -*- coding: utf-8 -*-
"""适配器品牌级子包（INT-497）— 三级体系第三级。

品牌适配器继承对应协议级 base，声明 (protocol, vendor) 品牌维度注册键。
"""
from api_test_service.infrastructure.adapters.vendors.openai_realtime_adapter import (
    OpenAIRealtimeAdapter,
)

__all__ = ['OpenAIRealtimeAdapter']
