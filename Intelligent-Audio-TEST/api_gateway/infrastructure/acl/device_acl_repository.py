# -*- coding: utf-8 -*-
"""device_service ACL 仓储实现 — 委托 grpc_proxies 实现。

所有方法委托 grpc_proxies 单例完成 gRPC 调用，将返回的
{success, message, data, code} 信封封装为 CommandResultDTO。
"""
from __future__ import annotations

from api_gateway.domain.dto import CommandResultDTO
from api_gateway.domain.repositories.acl.device_acl_repository import (
    DeviceAclRepository,
    PlaybackConfigAclRepository,
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


class DeviceAclRepositoryImpl(DeviceAclRepository):
    """device_config_service 实体 ACL 实现。"""

    def create(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.create(data))

    def update(self, device_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.update(device_id, data))

    def delete(self, device_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.delete(device_id))

    def get_all(self, **kwargs) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.get_all(**kwargs))

    def get_one(self, device_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.get_one(device_id))

    def get_statuses(self, device_ids=None) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.get_statuses(device_ids))

    def scan(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.scan())

    def test(self, device_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.test(device_id))

    def stop_test(self, device_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.stop_test(device_id))

    def get_driver_keywords(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.get_driver_keywords())

    def health_check(self, device_ids) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.health_check(device_ids))

    def get_available_serials(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.get_available_serials())


class PlaybackConfigAclRepositoryImpl(PlaybackConfigAclRepository):
    """playback_config_service 实体 ACL 实现。"""

    def create(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import playback_config_service
        return _wrap(playback_config_service.create(data))

    def update(self, device_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import playback_config_service
        return _wrap(playback_config_service.update(device_id, data))

    def delete(self, device_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import playback_config_service
        return _wrap(playback_config_service.delete(device_id))

    def associate_spl(self, device_id, spl_mapping_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import playback_config_service
        return _wrap(playback_config_service.associate_spl(device_id, spl_mapping_id))

    def test(self, device_id, test_params) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import playback_config_service
        return _wrap(playback_config_service.test(device_id, test_params))

    def stop_test(self, device_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import playback_config_service
        return _wrap(playback_config_service.stop_test(device_id))

    def get_all(self, **kwargs) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import playback_config_service
        return _wrap(playback_config_service.get_all(**kwargs))

    def get_one(self, device_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import playback_config_service
        return _wrap(playback_config_service.get_one(device_id))

    def scan(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import playback_config_service
        return _wrap(playback_config_service.scan())

    def check_status(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import playback_config_service
        return _wrap(playback_config_service.check_status())
