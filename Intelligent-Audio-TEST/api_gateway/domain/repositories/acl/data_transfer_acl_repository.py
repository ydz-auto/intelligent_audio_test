# -*- coding: utf-8 -*-
"""任务数据导入导出 ACL 仓储接口（api_gateway 域层端口，INT-25）"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from api_gateway.domain.dto.api_gateway_acl_dto import CommandResultDTO


class DataTransferAclRepository(ABC):
    """任务数据导入导出防腐层端口（网关 → task_service）"""

    @abstractmethod
    def export_tasks(self, task_ids: List[int],
                     options: Optional[Dict] = None) -> CommandResultDTO:
        """导出任务数据为 ZIP（返回 data.zip_path 供 FileResponse 下发）"""

    @abstractmethod
    def preview_import(self, zip_path: str) -> CommandResultDTO:
        """导入预检（manifest 摘要 + stats + conflicts + warnings）"""

    @abstractmethod
    def execute_import(self, zip_path: str) -> CommandResultDTO:
        """执行导入（分段提交 + 补偿回滚；长耗时）"""

    @abstractmethod
    def get_progress_snapshot(self) -> CommandResultDTO:
        """最近一次导入进度快照"""
