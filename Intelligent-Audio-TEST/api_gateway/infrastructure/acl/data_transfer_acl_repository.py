# -*- coding: utf-8 -*-
"""任务数据导入导出 ACL 仓储实现（api_gateway 基础设施层，INT-25）

委托 data_transfer_proxies 单例完成 gRPC / Redis 读取，
统一包装为 CommandResultDTO。
"""
from typing import Dict, List, Optional

from api_gateway.domain.dto.api_gateway_acl_dto import CommandResultDTO
from api_gateway.domain.repositories.acl.data_transfer_acl_repository import (
    DataTransferAclRepository,
)


def _wrap(result: dict) -> CommandResultDTO:
    return CommandResultDTO(
        success=bool(result.get('success')),
        message=result.get('message') or '',
        data=result.get('data'),
        code=result.get('code'),
    )


class DataTransferAclRepositoryImpl(DataTransferAclRepository):
    """任务数据导入导出防腐层实现"""

    def export_tasks(self, task_ids: List[int],
                     options: Optional[Dict] = None) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import data_transfer_service
        return _wrap(data_transfer_service.export_tasks({
            'task_ids': task_ids,
            'options': options or {},
        }))

    def preview_import(self, zip_path: str) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import data_transfer_service
        return _wrap(data_transfer_service.preview_import(zip_path))

    def execute_import(self, zip_path: str) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import data_transfer_service
        return _wrap(data_transfer_service.execute_import(zip_path))

    def get_progress_snapshot(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import data_transfer_service
        return _wrap(data_transfer_service.get_progress_snapshot())
