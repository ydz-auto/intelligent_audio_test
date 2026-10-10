# -*- coding: utf-8 -*-
"""device_service 跨域 ACL 仓储接口。

所有方法返回 CommandResultDTO，封装 gRPC 信封 {success, message, data, code}。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from api_gateway.domain.dto import CommandResultDTO


class DeviceAclRepository(ABC):
    """device_config_service 实体 ACL 接口。"""

    # ---- 写操作 ----
    @abstractmethod
    def create(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update(self, device_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete(self, device_id) -> CommandResultDTO: ...

    # ---- 读操作 ----
    @abstractmethod
    def get_all(self, **kwargs) -> CommandResultDTO: ...

    @abstractmethod
    def get_one(self, device_id) -> CommandResultDTO: ...

    @abstractmethod
    def get_statuses(self, device_ids=None) -> CommandResultDTO: ...

    @abstractmethod
    def scan(self) -> CommandResultDTO: ...

    @abstractmethod
    def test(self, device_id) -> CommandResultDTO: ...

    @abstractmethod
    def stop_test(self, device_id) -> CommandResultDTO: ...

    @abstractmethod
    def get_driver_keywords(self) -> CommandResultDTO: ...

    @abstractmethod
    def health_check(self, device_ids) -> CommandResultDTO: ...

    @abstractmethod
    def get_available_serials(self) -> CommandResultDTO: ...

    # ---- INT-80 设备操作/批量 ----
    @abstractmethod
    def control(self, device_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def batch_action(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def get_status_history(self, query: dict) -> CommandResultDTO: ...


class DeviceGroupAclRepository(ABC):
    """device_group 实体 ACL 接口（INT-80 设备分组）。"""

    @abstractmethod
    def create(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update(self, group_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete(self, group_id, cascade: bool = False) -> CommandResultDTO: ...

    @abstractmethod
    def get_all(self, page=1, per_page=100, keyword=None, group_type=None) -> CommandResultDTO: ...

    @abstractmethod
    def get_one(self, group_id) -> CommandResultDTO: ...

    @abstractmethod
    def add_devices(self, group_id, device_ids) -> CommandResultDTO: ...

    @abstractmethod
    def remove_devices(self, group_id, device_ids) -> CommandResultDTO: ...


class DeviceMonitorAclRepository(ABC):
    """device_monitor 实体 ACL 接口（INT-80 状态历史/告警）。"""

    @abstractmethod
    def list_alarm_rules(self, page=1, per_page=50, metric_type=None, enabled=None) -> CommandResultDTO: ...

    @abstractmethod
    def create_alarm_rule(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update_alarm_rule(self, rule_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete_alarm_rule(self, rule_id) -> CommandResultDTO: ...

    @abstractmethod
    def list_alarms(self, query: dict) -> CommandResultDTO: ...

    @abstractmethod
    def acknowledge_alarm(self, alarm_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def get_alarm_stats(self) -> CommandResultDTO: ...


class PlaybackConfigAclRepository(ABC):
    """playback_config_service 实体 ACL 接口。"""

    # ---- 写操作 ----
    @abstractmethod
    def create(self, data) -> CommandResultDTO: ...

    @abstractmethod
    def update(self, device_id, data) -> CommandResultDTO: ...

    @abstractmethod
    def delete(self, device_id) -> CommandResultDTO: ...

    @abstractmethod
    def associate_spl(self, device_id, spl_mapping_id) -> CommandResultDTO: ...

    @abstractmethod
    def test(self, device_id, test_params) -> CommandResultDTO: ...

    @abstractmethod
    def stop_test(self, device_id) -> CommandResultDTO: ...

    # ---- 读操作 ----
    @abstractmethod
    def get_all(self, **kwargs) -> CommandResultDTO: ...

    @abstractmethod
    def get_one(self, device_id) -> CommandResultDTO: ...

    @abstractmethod
    def scan(self) -> CommandResultDTO: ...

    @abstractmethod
    def check_status(self) -> CommandResultDTO: ...
