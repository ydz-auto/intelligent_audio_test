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
