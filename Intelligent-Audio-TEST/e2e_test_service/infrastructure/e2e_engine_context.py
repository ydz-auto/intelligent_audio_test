# -*- coding: utf-8 -*-
"""E2E 执行引擎上下文 — 基础设施层。

提供 E2EExecutor 所需的运行时基础设施能力：
- device_control_pool: 设备控制线程池
- stop_flags / pause_flags: 任务控制事件
- update_case_round_progress: 更新轮次进度
- _emit_progress: 推送进度（e2e_test_service 进程内为空实现）

在 e2e_test_service 进程内，控制事件通过 gRPC DeviceService
的 RegisterTaskEvents 与 task_service 同步状态。
"""
import threading
import concurrent.futures


class E2EEngineContext:
    """E2E 执行上下文：在 e2e_test_service 进程内提供 E2EExecutor 所需的 execution_engine 能力"""

    def __init__(self):
        self.device_control_pool = concurrent.futures.ThreadPoolExecutor(max_workers=8)
        self.stop_flags = {}
        self.pause_flags = {}
        self._round_progress = {}
        self._lock = threading.Lock()

    def _get_or_create_flags(self, task_id):
        with self._lock:
            if task_id not in self.stop_flags:
                self.stop_flags[task_id] = threading.Event()
            if task_id not in self.pause_flags:
                self.pause_flags[task_id] = threading.Event()
                self.pause_flags[task_id].set()
            return self.stop_flags[task_id], self.pause_flags[task_id]

    def update_case_round_progress(self, task_id, tc_rel_id, round_idx, total_rounds):
        with self._lock:
            self._round_progress.setdefault(task_id, {})[tc_rel_id] = {
                'round_idx': round_idx,
                'total_rounds': total_rounds,
            }

    def _emit_progress(self, task_id, force=False):
        # e2e_test_service 进程内不直接推送进度，由 task_service 端通过 gRPC 拉取状态
        pass

    def set_stop(self, task_id):
        stop, pause = self._get_or_create_flags(task_id)
        stop.set()

    def set_pause(self, task_id, paused):
        stop, pause = self._get_or_create_flags(task_id)
        if paused:
            pause.clear()
        else:
            pause.set()

    def get_round_progress(self, task_id):
        with self._lock:
            return dict(self._round_progress.get(task_id, {}))

    def cleanup(self, task_id):
        with self._lock:
            self.stop_flags.pop(task_id, None)
            self.pause_flags.pop(task_id, None)
            self._round_progress.pop(task_id, None)
