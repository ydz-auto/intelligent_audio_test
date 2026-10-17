# -*- coding: utf-8 -*-
"""实验室仓储接口（INT-655 实验室管理）。

定义 device_service 对 laboratories 主表及其资源计数的读写边界。
实现位于 device_service/infrastructure/persistence/laboratory_repository.py。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from device_service.domain.entities import LaboratoryAggregate


class LaboratoryRepositoryInterface(ABC):
    """实验室聚合仓储接口"""

    @abstractmethod
    def create_laboratory(self, data: dict) -> LaboratoryAggregate:
        """创建实验室，返回 LaboratoryAggregate。"""

    @abstractmethod
    def update_laboratory(self, lab_id: int, update_fields: dict) -> Optional[LaboratoryAggregate]:
        """更新实验室字段，返回更新后的 LaboratoryAggregate；不存在返回 None。"""

    @abstractmethod
    def delete_laboratory(self, lab_id: int) -> bool:
        """逻辑删除实验室；不存在返回 False。"""

    @abstractmethod
    def get_laboratory(self, lab_id: int) -> Optional[LaboratoryAggregate]:
        """按 ID 查询未删除实验室。"""

    @abstractmethod
    def get_laboratory_by_code(self, code: str) -> Optional[LaboratoryAggregate]:
        """按唯一 code 查询未删除实验室（重名校验）。"""

    @abstractmethod
    def list_laboratories(self, page: int = 1, per_page: int = 10,
                          keyword: str = None, status: str = None) -> dict:
        """分页查询实验室列表（items 含 device_count/playback_device_count/test_case_count）。"""

    @abstractmethod
    def count_devices(self, lab_ids: List[int]) -> Dict[int, int]:
        """统计各实验室的未删除被测设备数（devices.lab_id）。"""

    @abstractmethod
    def count_playback_devices(self, lab_ids: List[int]) -> Dict[int, int]:
        """统计各实验室的未删除播放设备数（playback_devices.lab_id）。"""

    @abstractmethod
    def count_test_cases(self, lab_ids: List[int]) -> Dict[int, int]:
        """统计各实验室的用例数（task_service test_cases.config JSONB 中的 lab_id，跨域 gRPC）。"""
