# -*- coding: utf-8 -*-
"""device_service 设备分组/监控仓储接口（ABC）— INT-80。

domain 层定义接口，infrastructure/persistence/ 做实现。
application 层依赖此 ABC，不直接 import 具体仓储类。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from device_service.domain.entities import DeviceGroupEntity


class DeviceGroupRepositoryInterface(ABC):
    """设备分组仓储接口。"""

    @abstractmethod
    def create_group(self, data: dict, member_device_ids: Optional[List[int]] = None) -> DeviceGroupEntity: ...

    @abstractmethod
    def update_group(self, group_id: str, update_fields: dict) -> Optional[DeviceGroupEntity]: ...

    @abstractmethod
    def get_group(self, group_id: str) -> Optional[DeviceGroupEntity]: ...

    @abstractmethod
    def get_group_by_name(self, name: str) -> Optional[DeviceGroupEntity]: ...

    @abstractmethod
    def delete_group(self, group_id: str, cascade: bool = False) -> bool: ...

    @abstractmethod
    def list_groups(self, page: int = 1, per_page: int = 100, keyword: str = None,
                    group_type: str = None) -> dict: ...

    @abstractmethod
    def add_devices(self, group_id: str, device_ids: List[int]) -> int: ...

    @abstractmethod
    def remove_devices(self, group_id: str, device_ids: List[int]) -> int: ...

    @abstractmethod
    def count_group_devices(self, group_ids: List[str]) -> Dict[str, int]: ...

    @abstractmethod
    def get_group_device_ids(self, group_id: str) -> List[int]: ...


class DeviceMonitorRepositoryInterface(ABC):
    """设备监控/告警仓储接口（状态历史 + 告警规则 + 告警记录）。"""

    # ========== 状态历史 ==========
    @abstractmethod
    def record_status_event(self, data: dict) -> dict: ...

    @abstractmethod
    def list_status_events(self, device_ids: List[int] = None, event_type: str = None,
                           start_time=None, end_time=None,
                           page: int = 1, per_page: int = 50) -> dict: ...

    @abstractmethod
    def count_health_check_failures_batch(self, device_ids: List[int]) -> Dict[int, int]: ...

    @abstractmethod
    def get_last_online_events(self, device_ids: List[int]) -> Dict[int, dict]: ...

    @abstractmethod
    def get_latest_health_details(self, device_ids: List[int]) -> Dict[int, dict]: ...

    @abstractmethod
    def update_alarm_email(self, alarm_id: int, sent: bool, error: str = '') -> None: ...

    # ========== 告警规则 ==========
    @abstractmethod
    def create_alarm_rule(self, data: dict) -> dict: ...

    @abstractmethod
    def update_alarm_rule(self, rule_id: int, update_fields: dict) -> Optional[dict]: ...

    @abstractmethod
    def delete_alarm_rule(self, rule_id: int) -> bool: ...

    @abstractmethod
    def get_alarm_rule(self, rule_id: int) -> Optional[dict]: ...

    @abstractmethod
    def list_alarm_rules(self, page: int = 1, per_page: int = 50,
                         metric_type: str = None, enabled: bool = None) -> dict: ...

    @abstractmethod
    def list_enabled_alarm_rules(self) -> List[dict]: ...

    # ========== 告警记录 ==========
    @abstractmethod
    def create_alarm(self, data: dict) -> dict: ...

    @abstractmethod
    def list_alarms(self, status: str = None, severity: str = None, device_id: int = None,
                    page: int = 1, per_page: int = 50) -> dict: ...

    @abstractmethod
    def acknowledge_alarm(self, alarm_id: int, acknowledged_by: str) -> Optional[dict]: ...

    @abstractmethod
    def get_alarm_stats(self) -> dict: ...

    @abstractmethod
    def has_unresolved_alarm(self, rule_id: int, device_id: int) -> bool: ...
