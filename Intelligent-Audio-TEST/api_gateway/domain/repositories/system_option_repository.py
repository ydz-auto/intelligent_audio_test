# -*- coding: utf-8 -*-
"""系统选项仓储接口（ABC，INT-620）。

对齐 DDD 红线：应用服务只依赖本接口，不直接触达 SQLAlchemy；
基础设施层持有实现（SystemOptionRepositoryImpl）。
"""
from abc import ABC, abstractmethod
from typing import Dict

from api_gateway.domain.entities.system_option import SystemOptionValue


class SystemOptionRepository(ABC):
    """系统选项 KV 仓储接口。"""

    @abstractmethod
    def get_all(self) -> Dict[str, SystemOptionValue]:
        """全量 KV 拉取（读侧，无副作用）。"""

    @abstractmethod
    def upsert(self, key: str, value: SystemOptionValue) -> None:
        """单键写入（写侧，upsert：存在即更新，不存在即插入）。"""
