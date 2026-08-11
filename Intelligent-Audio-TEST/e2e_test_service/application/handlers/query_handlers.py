# -*- coding: utf-8 -*-
"""E2E 测试查询处理器。

查询处理器委托给已有的 core/ 模块（e2e_service）读取运行时状态，
不改变系统状态。
"""

from typing import Dict

from e2e_test_service.application.queries.e2e_queries import (
    GetDeviceStatusQuery,
    GetTestProgressQuery,
)


class GetDeviceStatusHandler:
    """处理 GetDeviceStatusQuery

    委托给已有的 e2e_service.get_e2e_task_status()（core/e2e_service.py）。
    """

    def __init__(self, e2e_service=None):
        self._e2e_service = e2e_service

    @property
    def e2e_service(self):
        if self._e2e_service is None:
            from e2e_test_service.application.services.e2e_service import e2e_service
            self._e2e_service = e2e_service
        return self._e2e_service

    def handle(self, query: GetDeviceStatusQuery) -> Dict:
        """查询设备状态"""
        task_status = self.e2e_service.get_e2e_task_status(query.task_id)
        return {
            'task_id': query.task_id,
            'device_id': query.device_id,
            'task_status': task_status.get('status', 'idle'),
            'round_progress': task_status.get('round_progress', {}),
        }


class GetTestProgressHandler:
    """处理 GetTestProgressQuery

    委托给已有的 e2e_service.get_e2e_task_status()（core/e2e_service.py）。
    """

    def __init__(self, e2e_service=None):
        self._e2e_service = e2e_service

    @property
    def e2e_service(self):
        if self._e2e_service is None:
            from e2e_test_service.application.services.e2e_service import e2e_service
            self._e2e_service = e2e_service
        return self._e2e_service

    def handle(self, query: GetTestProgressQuery) -> Dict:
        """查询测试进度"""
        task_status = self.e2e_service.get_e2e_task_status(query.task_id)
        return {
            'task_id': query.task_id,
            'status': task_status.get('status', 'idle'),
            'tc_rel_id': task_status.get('tc_rel_id'),
            'round_progress': task_status.get('round_progress', {}),
        }
