# -*- coding: utf-8 -*-
"""DeviceService ACL 仓储接口

e2e_test_service 通过此接口访问 device_service 的设备数据与驱动能力，
不直接 import shared.models 或 db.session。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DeviceQueryResult:
    """按 ID 批量查询设备的结果（INT-2255）

    devices：成功取到的设备 DTO 列表（单台失败只影响该台）；
    errors：失败明细 [{'device_id': int, 'error': str}]，用于区分「查询失败」
        与「查询成功但没有数据」——调用方据此给出可诊断的失败信息，
        不再把底层故障吞成空列表。
    """
    devices: List[Any] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)

    def error_map(self) -> Dict[int, str]:
        """device_id → 错误消息"""
        result: Dict[int, str] = {}
        for item in self.errors:
            try:
                result[int(item['device_id'])] = item.get('error') or ''
            except (KeyError, TypeError, ValueError):
                continue
        return result


class DeviceAclRepository(ABC):
    """设备服务 ACL 仓储接口"""

    @abstractmethod
    def get_devices_by_ids(self, device_ids: List[int]) -> DeviceQueryResult:
        """按 ID 列表获取设备信息（name, serial_number, ip, system, keywords,
        needs_prompt_audio, prompt_config 等）

        INT-2255：单台 GetDevice 失败只丢该台并累计到 errors，不因一台异常
        丢弃已取到的设备；整体连接失败时全部 device_id 均记一条 error。
        """

    @abstractmethod
    def register_task_events(self, task_id: str, stop_event_set: bool,
                             pause_event_set: bool) -> bool:
        """注册/同步任务事件"""

    @abstractmethod
    def register_task_devices(self, task_id: str, device_info_list: List[Dict]) -> bool:
        """注册任务设备"""

    @abstractmethod
    def create_driver(self, task_id: str, device_config: List[Dict]) -> bool:
        """创建设备驱动（含 action: initialize/pre_process/post_process/teardown）

        失败时上抛异常（携带 device_service 真因消息），不吞成 False（INT-206）。
        """

    @abstractmethod
    def initialize_driver(self, task_id: str, device_config: List[Dict]) -> Dict:
        """创建设备驱动（initialize 专用）：返回 device_service 结构化响应

        成功时含 ui_capabilities（INT-296：ui_capture_available / degrade_reason）；
        失败语义与 create_driver 一致（上抛异常携带真因）。
        """

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
