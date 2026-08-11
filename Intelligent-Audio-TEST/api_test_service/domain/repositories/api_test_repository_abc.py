# -*- coding: utf-8 -*-
"""API 测试仓储抽象接口（ABC）

DDD 规则3：Repository 必须继承 ABC。本模块定义领域层的仓储抽象接口，
infrastructure/persistence/api_test_repository.py 提供具体实现（APITestRepository）。

抽象方法签名与具体实现保持一致，确保上层通过依赖注入使用接口，
不直接依赖 ORM 实现。

提供两类接口：
1. 聚合根生命周期接口（get_by_id / save / add / soft_delete）—— 输入输出均为 APIAggregate
2. 兼容应用层 dict 风格的 CRUD 接口（create_api / update_api / delete_api /
   get_api / list_apis 等）
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:  # 避免循环引用，仅用于类型注解
    from api_test_service.domain.entities import APIAggregate


class APITestRepositoryABC(ABC):
    """API 测试仓储抽象接口。

    遵循 DDD 仓储模式：外部只看到聚合根，不感知 ORM。
    """

    # ==================== 聚合根生命周期接口 ====================

    @abstractmethod
    def get_by_id(self, api_id: int) -> Optional['APIAggregate']:
        """按 ID 加载 API 聚合根（PO → Entity）。

        Returns:
            APIAggregate 或 None（API 不存在）。
        """

    @abstractmethod
    def save(self, aggregate: 'APIAggregate') -> None:
        """持久化聚合根变更（Entity → PO）。"""

    @abstractmethod
    def add(self, aggregate: 'APIAggregate') -> int:
        """新增 API 聚合根，返回新 ID。"""

    @abstractmethod
    def soft_delete(self, api_id: int) -> bool:
        """软删除 API。"""

    # ==================== 兼容应用层 CRUD 接口 ====================

    @abstractmethod
    def create_api(self, data: dict) -> 'APIAggregate':
        """创建 API 配置，返回聚合根。

        Args:
            data: 包含 API 字段的字典（name, vendor, api_url, ...）
        """

    @abstractmethod
    def update_api(self, api_id: int, data: dict) -> Optional['APIAggregate']:
        """更新 API 配置，返回聚合根。"""

    @abstractmethod
    def delete_api(self, api_id: int) -> bool:
        """软删除 API 配置（委托 soft_delete）。"""

    @abstractmethod
    def list_apis(
        self,
        page: int = 1,
        per_page: int = 10,
        keyword: str = None,
        status: str = None,
        algorithm_type: str = None,
    ) -> dict:
        """分页查询 API 列表，items 为 APIAggregate 聚合根列表。"""

    @abstractmethod
    def get_api(self, api_id: int) -> Optional['APIAggregate']:
        """查询单个 API 配置详情（仅未删除），返回聚合根。"""

    @abstractmethod
    def find_api_by_id(self, api_id: int) -> Optional['APIAggregate']:
        """根据 ID 查询 API，返回聚合根（不过滤 deleted）。"""

    # ==================== 关联数据查询（不返回 API PO） ====================

    @abstractmethod
    def find_api_ids_by_task(self, task_id: int) -> List[int]:
        """查询任务关联的 API ID 列表（通过 gRPC 调用 task_service.GetTaskApis）。"""

    @abstractmethod
    def find_task_by_id(self, task_id: int) -> Optional[dict]:
        """根据 ID 查询测试任务（通过 gRPC 调用 task_service.GetTaskById，返回 dict）。"""

    @abstractmethod
    def task_exists(self, task_id: int) -> bool:
        """判断任务是否存在（通过 gRPC 调用 task_service.GetTaskById）。"""

    @abstractmethod
    def check_api_in_running_tasks(self, api_id: int) -> list:
        """检查 API 是否被正在运行的任务引用。

        通过 gRPC 查询 task_service 的 TaskApis 和 Task，
        返回引用此 API 的运行中任务列表（dict 列表）。
        """
