# -*- coding: utf-8 -*-
"""device_service ACL 仓储实现 — 委托 grpc_proxies 实现。

所有方法委托 grpc_proxies 单例完成 gRPC 调用，将返回的
{success, message, data, code} 信封封装为 CommandResultDTO。
"""
from __future__ import annotations

from api_gateway.domain.dto import CommandResultDTO
from api_gateway.domain.repositories.acl.device_acl_repository import (
    DeviceAclRepository,
    DeviceGroupAclRepository,
    DeviceMonitorAclRepository,
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

    # ---- INT-80 设备操作/批量/状态历史 ----

    def control(self, device_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.control(device_id, data))

    def batch_action(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.batch_action(data))

    def get_status_history(self, query: dict) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.get_status_history(query))


class DeviceGroupAclRepositoryImpl(DeviceGroupAclRepository):
    """device_group 实体 ACL 实现（INT-80 设备分组）。"""

    def create(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.create_group(data))

    def update(self, group_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.update_group(group_id, data))

    def delete(self, group_id, cascade: bool = False) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.delete_group(group_id, cascade))

    def get_all(self, page=1, per_page=100, keyword=None, group_type=None) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.get_groups(
            page=page, per_page=per_page, keyword=keyword, group_type=group_type))

    def get_one(self, group_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.get_group(group_id))

    def add_devices(self, group_id, device_ids) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.add_devices_to_group(group_id, device_ids))

    def remove_devices(self, group_id, device_ids) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.remove_devices_from_group(group_id, device_ids))


class DeviceMonitorAclRepositoryImpl(DeviceMonitorAclRepository):
    """device_monitor 实体 ACL 实现（INT-80 状态历史/告警）。"""

    def list_alarm_rules(self, page=1, per_page=50, metric_type=None, enabled=None) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.list_alarm_rules(
            page=page, per_page=per_page, metric_type=metric_type, enabled=enabled))

    def create_alarm_rule(self, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.create_alarm_rule(data))

    def update_alarm_rule(self, rule_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.update_alarm_rule(rule_id, data))

    def delete_alarm_rule(self, rule_id) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.delete_alarm_rule(rule_id))

    def list_alarms(self, query: dict) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.list_alarms(query))

    def acknowledge_alarm(self, alarm_id, data) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.acknowledge_alarm(alarm_id, data))

    def get_alarm_stats(self) -> CommandResultDTO:
        from api_gateway.infrastructure.grpc_proxies import device_config_service
        return _wrap(device_config_service.get_alarm_stats())


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
