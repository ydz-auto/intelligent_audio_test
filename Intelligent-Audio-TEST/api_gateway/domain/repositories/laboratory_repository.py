# -*- coding: utf-8 -*-
"""api_gateway 领域层 —— 实验室仓储接口（ABC）（INT-493/INT-537 拆分①）

实验室为网关自有域，仓储实现直连共享库 laboratories 表
（infrastructure/repositories/laboratory_repository.py，复用
shared.models.database.get_db_session()），与 read_models TODO(DB穿透) 先例一致。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Tuple

from api_gateway.domain.entities.laboratory import Laboratory


class LaboratoryRepository(ABC):
    """实验室仓储接口（命令 + 查询）。"""

    # ---- 读操作 ----

    @abstractmethod
    def list(self, status: Optional[str] = None, page: int = 1,
             per_page: int = 20) -> Tuple[list[Laboratory], int]:
        """分页查询未删除实验室；status 为空不过滤。返回 (items, total)。"""

    @abstractmethod
    def get(self, lab_id: int) -> Optional[Laboratory]:
        """按 id 查询未删除实验室；不存在或已软删返回 None。"""

    @abstractmethod
    def get_by_code(self, code: str) -> Optional[Laboratory]:
        """按 code 查询（含软删行）——用于 code 唯一冲突校验（软删冲突也 409）。"""

    # ---- 写操作 ----

    @abstractmethod
    def create(self, data: dict) -> Laboratory:
        """创建实验室；data 含 code/name/status 等字段与操作人上下文。"""

    @abstractmethod
    def update(self, lab_id: int, data: dict) -> Optional[Laboratory]:
        """更新实验室（仅 data 中存在的字段）；不存在或已软删返回 None。"""

    @abstractmethod
    def delete(self, lab_id: int, deleted_by_user_id: Optional[int] = None) -> bool:
        """软删（deleted=TRUE）；不存在或已软删返回 False。"""
