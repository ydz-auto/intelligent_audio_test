# -*- coding: utf-8 -*-
"""厂商适配器 Port — 厂商协议差异的唯一隔离边界（INT-62）。

架构约束（设计文档 01_测试执行/02_架构设计.md §3.6）：
- 协议细节（报文格式、WS 帧协议、字段映射）只允许出现在
  infrastructure/adapters/ 的具体适配器实现中；
- 执行链（core/ 执行器）只依赖本 Port 与
  infrastructure/adapters 的注册表分发，禁止 import 具体适配器。

生命周期语义（V9.7.10 APIAdapterFactory/BaseAPIAdapter 保留）：
    initialize → [render_request_parts → execute]* → teardown
initialize/teardown 提供默认空实现，适配器按需覆写。

构造契约（注册表 create_from_config 统一实例化入口）：
    所有适配器 __init__ 接受
    (api_config, case_config=None, endpoint=None,
     test_case_id=None, task_id=None)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, Tuple

from shared.models.common_enums import APIProtocol, VendorAdapterType


class ApiVendorAdapter(ABC):
    """厂商协议适配器 Port。

    类属性：
        adapter_type: 注册表 key，必须为 VendorAdapterType 枚举成员。
        supported_protocols: 适配器支持的传输协议（协议类型枚举化，
            供 list_adapters 自描述与后续按协议分型扩展）。
    """

    adapter_type: ClassVar[VendorAdapterType]
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
