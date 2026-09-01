# -*- coding: utf-8 -*-
"""任务执行核心 Mixin — 聚合导出模块（P4-4 大文件拆分）。

原单文件 1045 行，已按职责拆分为 4 个子 Mixin，本文件保持
`from task_service.core.execution_engine._task_runner_mixin import TaskRunnerMixin`
的导入路径不变（TaskRunnerMixin 变为组合类）：

- _task_lifecycle_mixin.py：TaskLifecycleMixin — 任务启动 / API 初始化 / 主循环编排
- _task_dispatch_mixin.py：TaskDispatchMixin — 用例领取 / 原子占用 / 分发 / 失败处理
- _device_check_mixin.py：DeviceCheckMixin — E2E 被测设备 / 播放设备在线检查
- _task_finalize_mixin.py：TaskFinalizeMixin — 等待完成 / 状态收敛 / 异常 / 资源清理
"""
from task_service.core.execution_engine._task_lifecycle_mixin import TaskLifecycleMixin
from task_service.core.execution_engine._task_dispatch_mixin import TaskDispatchMixin
from task_service.core.execution_engine._device_check_mixin import DeviceCheckMixin
from task_service.core.execution_engine._task_finalize_mixin import TaskFinalizeMixin


class TaskRunnerMixin(TaskLifecycleMixin, TaskDispatchMixin, DeviceCheckMixin, TaskFinalizeMixin):
    """任务执行核心逻辑组合：_run_task 及其拆分出的全部子方法

    MRO：TaskLifecycleMixin → TaskDispatchMixin → DeviceCheckMixin → TaskFinalizeMixin
    各子 Mixin 之间通过 ExecutionEngine 实例上的共享属性协作
    （_log / _emit_progress / _emit_alert / _wait_completion_event /
    _execute_api_case / _execute_e2e_case / _check_queue 等）。
    """


__all__ = ["TaskRunnerMixin"]
