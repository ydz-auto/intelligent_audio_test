# -*- coding: utf-8 -*-
"""DeviceService ACL 仓储接口

e2e_test_service 通过此接口访问 device_service 的设备数据与驱动能力，
不直接 import shared.models 或 db.session。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class DeviceAclRepository(ABC):
    """设备服务 ACL 仓储接口"""

    @abstractmethod
    def get_devices_by_ids(self, device_ids: List[int]) -> List[Dict[str, Any]]:
        """按 ID 列表获取设备信息（name, serial_number, ip, system, keywords,
        needs_prompt_audio, prompt_config 等）"""

    @abstractmethod
    def register_task_events(self, task_id: str, stop_event_set: bool,
                             pause_event_set: bool) -> bool:
        """注册/同步任务事件"""

    @abstractmethod
    def register_task_devices(self, task_id: str, device_info_list: List[Dict]) -> bool:
        """注册任务设备"""

    @abstractmethod
    def create_driver(self, task_id: str, device_config: List[Dict]) -> bool:
        """创建设备驱动（含 action: initialize/pre_process/post_process/teardown）"""

    @abstractmethod
    def extract_archive_results(self, task_id: str, device_config: Dict) -> Optional[List]:
        """提取存档结果"""

    @abstractmethod
    def get_final_results(self, task_id: str, device_config: Dict) -> Optional[List]:
        """所有轮次完成后获取最终聚合结果"""

    @abstractmethod
    def destroy_driver(self, task_id: str) -> bool:
        """销毁设备驱动"""

    @abstractmethod
    def driver_scan(self, system: str, keywords: str = '') -> List[Dict[str, Any]]:
        """扫描设备"""

    @abstractmethod
    def driver_unlock(self, system: str, keywords: str, serial_or_ip: str) -> bool:
        """解锁设备"""

    @abstractmethod
    def get_driver_name_by_keywords(self, system: str, keywords: str) -> str:
        """获取驱动名称"""

    @abstractmethod
    def get_registered_keywords(self) -> Dict[str, Any]:
        """获取所有已注册驱动关键字"""

    @abstractmethod
    def get_mock_mode(self, system: str = '') -> bool:
        """获取 mock 模式"""

    @abstractmethod
    def set_mock_mode(self, system: str, mock_mode: bool) -> bool:
        """设置 mock 模式"""
