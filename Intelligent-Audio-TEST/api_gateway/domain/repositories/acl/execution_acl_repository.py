# -*- coding: utf-8 -*-
"""任务执行引擎跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from api_gateway.domain.dto import ExecutionResultDTO


class ExecutionAclRepository(ABC):
    """execution_engine 跨域 ACL 仓储接口。

    封装 task_service ExecutionService 的任务执行/控制/队列管理调用，
    返回 ExecutionResultDTO（不再返回 raw (success, message) tuple）。
    """

    @abstractmethod
    def start_task(self, app, task_id) -> ExecutionResultDTO:
        ...

    @abstractmethod
    def control_task(self, app, task_id, action) -> ExecutionResultDTO:
        ...

    @abstractmethod
    def remove_from_queue(self, task_id) -> ExecutionResultDTO:
        ...
