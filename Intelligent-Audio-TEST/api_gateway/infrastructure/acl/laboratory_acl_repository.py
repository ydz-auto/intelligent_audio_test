# -*- coding: utf-8 -*-
"""laboratory_service ACL 仓储实现（INT-655）— 委托 grpc_proxies 实现。

所有方法委托 grpc_proxies 单例完成 gRPC 调用，将返回的
{success, message, data, code} 信封封装为 CommandResultDTO。
"""
from __future__ import annotations

from api_gateway.domain.dto import CommandResultDTO
from api_gateway.domain.repositories.acl.device_acl_repository import (
    LaboratoryAclRepository,
)


def _wrap(result) -> CommandResultDTO:
    """将 gRPC 返回的信封 dict 封装为 CommandResultDTO。"""
    if isinstance(result, dict):
        return CommandResultDTO(
            success=result.get('success', False),
            message=result.get('message'),
            data=result.get('data'),
            code=result.get('code'),
        )
    return CommandResultDTO(success=False, data=result)


class LaboratoryAclRepositoryImpl(LaboratoryAclRepository):
    """laboratory 实体 ACL 实现。"""

    def create(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_proxies
        return _wrap(device_proxies.laboratory_config_service.create(data))

    def update(self, lab_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_proxies
        return _wrap(device_proxies.laboratory_config_service.update(lab_id, data))

    def delete(self, lab_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_proxies
        return _wrap(device_proxies.laboratory_config_service.delete(lab_id))

    def get_all(self, page=1, per_page=10, keyword=None, status=None) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_proxies
        return _wrap(device_proxies.laboratory_config_service.get_all(
            page=page, per_page=per_page, keyword=keyword, status=status,
        ))

    def get_one(self, lab_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_proxies
        return _wrap(device_proxies.laboratory_config_service.get_one(lab_id))

    def get_summary(self, lab_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_proxies
        return _wrap(device_proxies.laboratory_config_service.get_summary(lab_id))
