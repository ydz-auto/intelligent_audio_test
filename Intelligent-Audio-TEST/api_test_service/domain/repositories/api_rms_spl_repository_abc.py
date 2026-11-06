# -*- coding: utf-8 -*-
"""被测 API RMS→SPL 映射仓储端口（INT-61 / UC-0902 CRUD 扩展）"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

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

    # ==================== UC-0902 写侧 ====================

    @abstractmethod
    def create_mapping(self, data: dict) -> ApiRmsSplMapping:
        """创建映射（data 为已校验的字段字典），返回含 id 的领域实体。"""
        ...

    @abstractmethod
    def update_mapping(self, mapping_id, data: dict) -> Optional[ApiRmsSplMapping]:
        """按字段字典更新映射，未找到返回 None。"""
        ...

    @abstractmethod
    def delete_mapping(self, mapping_id) -> bool:
        """软删除映射。"""
        ...

    @abstractmethod
    def list_mappings(self, page: int = 1, per_page: int = 10,
                      api_id=None, calibration_status=None) -> dict:
        """分页查询映射列表（items 为领域实体列表）。"""
        ...

    @abstractmethod
    def list_by_api(self, api_id) -> List[ApiRmsSplMapping]:
        """按 API 查全部未删除映射（创建时间倒序）。"""
        ...
