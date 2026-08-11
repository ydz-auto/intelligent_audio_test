# -*- coding: utf-8 -*-
"""DeviceResultService ACL 仓储接口

e2e_test_service 通过此接口访问 device_service 的结果采集与转换能力。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class DeviceResultAclRepository(ABC):
    """设备结果服务 ACL 仓储接口"""

    @abstractmethod
    def collect_results(self, task_id: str, test_case_id: str,
                        device_info_list: List[Dict], extra_params: Dict,
                        **kwargs) -> List[Dict[str, Any]]:
        """采集设备原始结果"""

    @abstractmethod
    def convert_results(self, tagged_results: List[Dict], algorithm_type: str) -> List[Dict[str, Any]]:
        """转换结果字段"""

    @abstractmethod
    def reextract_result(self, task_id: str, reextract_config: Dict) -> Dict[str, Any]:
        """重新提取设备结果"""
