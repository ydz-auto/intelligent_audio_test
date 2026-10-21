# -*- coding: utf-8 -*-
"""厂商适配器 Port — 厂商协议差异的唯一隔离边界（INT-62）。

架构约束（设计文档 01_测试执行/02_架构设计.md §3.6）：
- 协议细节（报文格式、WS 帧协议、字段映射）只允许出现在
  infrastructure/adapters/ 的具体适配器实现中；
- 执行链（core/ 执行器）只依赖本 Port 与
  infrastructure/adapters 的注册表分发，禁止 import 具体适配器。

生命周期语义（V9.7.10 APIAdapterFactory/BaseAPIAdapter 保留；INT-497 三级体系
协议级 base 扩展 Realtime 六钩子）：
    HTTP/WS 适配器：initialize → [render_request_parts → execute]* → teardown
    Realtime 适配器：initialize → pre_process → send → recv → post_process → teardown
initialize/teardown 提供默认空实现，适配器按需覆写。

构造契约（注册表 create_from_config 统一实例化入口）：
    所有适配器 __init__ 接受
    (api_config, case_config=None, endpoint=None,
     test_case_id=None, task_id=None)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, Optional, Tuple

from shared.models.common_enums import APIProtocol, AdapterProtocol, AdapterVendor, VendorAdapterType


class ApiVendorAdapter(ABC):
    """厂商协议适配器 Port。

    类属性（INT-497 注册表多维 key：三级体系 base_adaptor → 协议_base_adaptor
    → 品牌适配器，与设备驱动注册表同构）：
        protocol: 协议维度，必须为 AdapterProtocol 枚举成员（新式适配器声明；
            遗留适配器缺省 AdapterProtocol.ANY）。
        vendor:   品牌维度，必须为 AdapterVendor 枚举成员（新式适配器声明；
            遗留适配器由 adapter_type 映射）。
        adapter_type: 用例配置扁平 key 兼容层（VendorAdapterType 枚举成员，
            遗留单维注册使用；新式适配器可不声明，缺省 None）。
        supported_protocols: 适配器支持的传输协议（协议类型枚举化，
            供 list_adapters 自描述与后续按协议分型扩展）。
    """

    protocol: ClassVar[AdapterProtocol] = AdapterProtocol.ANY
    vendor: ClassVar[AdapterVendor] = AdapterVendor.ANY
    adapter_type: ClassVar[Optional[VendorAdapterType]] = None
    supported_protocols: ClassVar[Tuple[APIProtocol, ...]] = (
        APIProtocol.HTTP, APIProtocol.WEBSOCKET,
    )

    # —— 生命周期钩子（默认空实现） ——

    def initialize(self) -> None:
        """会话/连接前置准备（默认无操作）。"""

    def teardown(self) -> None:
        """会话/连接清理（默认无操作）。"""

    # —— 请求渲染（pre_process） ——

    @abstractmethod
    def render_request_parts(self, context_data: Dict[str, Any]) -> Tuple[Dict, Dict]:
        """按厂商协议渲染请求头与请求体。

        Returns:
            (rendered_headers, rendered_body) 二元组。
        """
        ...

    # —— 请求执行（send + recv + post_process） ——

    @abstractmethod
    def execute(self, context_data: Dict[str, Any], files=None,
                method: str = None) -> Dict[str, Any]:
        """执行一次厂商协议调用并返回结构化结果。

        Returns:
            统一结果字典（success / latency / status_code / raw_response /
            error / json 及协议解析附加字段）。
        """
        ...

    def execute_voice_llm_chat(self, **kwargs) -> Dict[str, Any]:
        """voice_llm chat 等价能力（INT-1169/1176 迁移默认路径）。

        多轮会话默认路径（use_adapter=True）经本方法内嵌执行，HTTP/mock
        适配器覆写；Realtime 等非 HTTP 适配器默认不支持，显式报错拒绝
        静默降级。
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} 不支持 voice_llm chat 执行路径")
