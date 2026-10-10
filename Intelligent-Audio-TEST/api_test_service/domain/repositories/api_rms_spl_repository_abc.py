# -*- coding: utf-8 -*-
"""被测 API RMS→SPL 映射仓储端口（INT-61）"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from api_test_service.domain.entities.api_rms_spl_mapping import ApiRmsSplMapping


class ApiRmsSplRepository(ABC):
    """被测 API RMS→SPL 映射仓储接口（本服务 owned 表 api_rms_spl_mappings）"""

    @abstractmethod
    def get_default_mapping(self, api_id) -> Optional[ApiRmsSplMapping]:
        """取被测 API 的当前默认映射：优先 apis.rms_spl_mapping_id 指定项，
        未指定时取该 API 最新一条未删除映射；无映射返回 None（调用方走线性近似）。"""
        ...

    @abstractmethod
    def get_mapping(self, mapping_id) -> Optional[ApiRmsSplMapping]:
        """按 ID 取映射。"""
        ...
