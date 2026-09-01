# -*- coding: utf-8 -*-
"""执行引擎 Mixin 子包。

按职责拆分的 Mixin 模块统一收口于此，对外提供统一导出：
- 调度器 / 进度日志 / 任务控制 / 用例执行 四大基础 Mixin
- 任务执行核心组合 Mixin（TaskRunnerMixin = lifecycle + dispatch + device_check + finalize）
- gRPC 跨服务调用封装函数（grpc_helpers）
"""
from task_service.core.execution_engine.mixins.scheduler import SchedulerMixin
from task_service.core.execution_engine.mixins.progress import ProgressMixin
from task_service.core.execution_engine.mixins.task_control import TaskControlMixin
from task_service.core.execution_engine.mixins.case_execution import CaseExecutionMixin
from task_service.core.execution_engine.mixins.task_runner import TaskRunnerMixin
from task_service.core.execution_engine.mixins.task_lifecycle import TaskLifecycleMixin
from task_service.core.execution_engine.mixins.task_dispatch import TaskDispatchMixin
from task_service.core.execution_engine.mixins.device_check import DeviceCheckMixin
from task_service.core.execution_engine.mixins.task_finalize import TaskFinalizeMixin
from task_service.core.execution_engine.mixins.grpc_helpers import (
    _stop_task_audio_via_grpc,
    _cleanup_devices_via_grpc,
    _unregister_task_events_via_grpc,
    _get_task_events_via_grpc,
    _register_task_events_via_grpc,
    _execute_e2e_case_via_grpc,
)

__all__ = [
    # Mixin 类
    "SchedulerMixin",
    "ProgressMixin",
    "TaskControlMixin",
    "CaseExecutionMixin",
    "TaskRunnerMixin",
    "TaskLifecycleMixin",
    "TaskDispatchMixin",
    "DeviceCheckMixin",
    "TaskFinalizeMixin",
    # gRPC 封装函数
    "_stop_task_audio_via_grpc",
    "_cleanup_devices_via_grpc",
    "_unregister_task_events_via_grpc",
    "_get_task_events_via_grpc",
    "_register_task_events_via_grpc",
    "_execute_e2e_case_via_grpc",
]
