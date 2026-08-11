# -*- coding: utf-8 -*-
"""api_adapter_service.AdapterService 跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from api_test_service.domain.dto import AdapterRoundResultDTO


class AdapterAclRepository(ABC):
    """api_adapter_service.AdapterService 跨域调用接口。"""

    @abstractmethod
    def send_round(self, request) -> AdapterRoundResultDTO:
        """发送一轮请求到 adapter 服务，返回结果 DTO。

        request 为构造好的 adapter_service_pb2.SendRoundRequest。
        """
        ...
