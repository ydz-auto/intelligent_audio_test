# -*- coding: utf-8 -*-
"""E2E 测试仓储实现。

仓储（Repository）为应用层提供对聚合根的持久化访问抽象。本实现
委托给已有的 core/ 模块（e2e_service）维护的内存状态，以及
shared/models/database 提供的 DB 访问。

注意：当前 E2E 测试会话状态由 e2e_service 单例在内存中维护，
本仓储主要作为应用层与已有实现之间的适配门面。
"""

from typing import Dict


class E2ETestRepository:
    """E2E 测试仓储

    委托给已有的 e2e_service（core/e2e_service.py）单例，提供对
    E2ETestSession 运行时状态的读取能力。
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._e2e_service = None
        return cls._instance

    @property
    def e2e_service(self):
        if self._e2e_service is None:
            from e2e_test_service.core.e2e_service import e2e_service
            self._e2e_service = e2e_service
        return self._e2e_service

    def get_status(self, task_id: str) -> Dict:
        """获取任务的运行时状态"""
        return self.e2e_service.get_e2e_task_status(task_id)

    def get_round_progress(self, task_id: str) -> Dict:
        """获取任务的轮次进度"""
        status = self.e2e_service.get_e2e_task_status(task_id)
        return status.get('round_progress', {})

    def save_status(self, task_id: str, status: Dict):
        """保存任务状态（委托给 e2e_service 内部 _task_status）"""
        # e2e_service 内部通过 _task_status 字典维护状态
        with self.e2e_service._task_lock:
            self.e2e_service._task_status[task_id] = status
