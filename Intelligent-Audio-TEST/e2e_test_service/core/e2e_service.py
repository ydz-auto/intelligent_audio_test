"""
E2E Test Service - 服务接口层
接收 Task Service 的 gRPC 请求，执行 E2E 测试
"""
import threading
import os
import sys
import time


class _E2EEngineContext:
    """E2E 执行上下文：在 e2e_test_service 进程内提供 E2EExecutor 所需的 execution_engine 能力

    E2EExecutor 原本依赖 task_service 进程内的 execution_engine 单例，提供：
    - device_control_pool: 设备控制线程池
    - stop_flags / pause_flags: 任务控制事件
    - update_case_round_progress: 更新轮次进度
    - _emit_progress: 推送进度

    在 e2e_test_service 进程内，用本地实现的轻量上下文替代，控制事件通过 gRPC
    DeviceService 的 RegisterTaskEvents 与 task_service 同步状态。
    """

    def __init__(self):
        import concurrent.futures
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


class E2EService:
    """E2E 测试服务"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def init_app(self, app):
        """初始化服务"""
        self.app = app
        self._engine_ctx = _E2EEngineContext()
        self._executor = None
        self._task_status = {}
        self._task_threads = {}
        self._task_lock = threading.Lock()
        self._initialized = True

    @property
    def executor(self):
        """懒加载 E2EExecutor，注入本地引擎上下文"""
        if self._executor is None:
            from e2e_test_service.core.e2e_executor import E2EExecutor
            self._executor = E2EExecutor(self._engine_ctx)
        return self._executor

    def start_task(self, task_id, case_ids, device_id):
        """启动 E2E 任务（HTTP 入口，实际执行通过 gRPC 由 task_service 驱动）"""
        return {'success': True, 'task_id': task_id, 'message': 'E2E task started'}

    def stop_task(self, task_id):
        """停止 E2E 任务"""
        return {'success': True, 'task_id': task_id, 'message': 'E2E task stopped'}

    def get_task_status(self, task_id):
        """获取任务状态"""
        return {'task_id': task_id, 'status': 'idle'}

    def start_e2e_case(self, task_id, tc_rel_id):
        """启动单个 E2E 用例执行（gRPC StartE2ETask 调用入口）

        同步执行 E2EExecutor.execute_e2e_case，返回执行结果。
        """
        if not self._initialized:
            return {'success': False, 'message': 'E2EService 未初始化'}

        try:
            # 确保控制事件已创建
            self._engine_ctx._get_or_create_flags(task_id)
            with self._task_lock:
                self._task_status[task_id] = {'status': 'running', 'tc_rel_id': tc_rel_id}

            success = self.executor.execute_e2e_case(task_id, tc_rel_id)

            with self._task_lock:
                self._task_status[task_id] = {
                    'status': 'completed' if success else 'failed',
                    'tc_rel_id': tc_rel_id,
                    'success': success,
                }
            return {
                'success': success,
                'task_id': str(task_id),
                'tc_rel_id': str(tc_rel_id),
                'message': 'ok' if success else 'E2E 用例执行失败',
            }
        except Exception as e:
            import traceback
            with self._task_lock:
                self._task_status[task_id] = {
                    'status': 'failed',
                    'tc_rel_id': tc_rel_id,
                    'error': str(e),
                }
            return {
                'success': False,
                'task_id': str(task_id),
                'tc_rel_id': str(tc_rel_id),
                'message': f'E2E 用例执行异常: {e}',
                'traceback': traceback.format_exc(),
            }

    def stop_e2e_case(self, task_id):
        """停止 E2E 用例执行（gRPC StopE2ETask 调用入口）

        设置本地 stop_event，E2EExecutor 的 _handle_control 会在下一次轮询时检测到并中止。
        """
        try:
            self._engine_ctx.set_stop(task_id)
            with self._task_lock:
                if task_id in self._task_status:
                    self._task_status[task_id]['status'] = 'stopping'
            return {'success': True, 'task_id': str(task_id), 'message': 'stop signal sent'}
        except Exception as e:
            return {'success': False, 'task_id': str(task_id), 'message': str(e)}

    def get_e2e_task_status(self, task_id):
        """获取 E2E 任务状态（gRPC GetE2ETaskStatus 调用入口）"""
        with self._task_lock:
            status = self._task_status.get(task_id, {'status': 'idle'})
            round_progress = self._engine_ctx.get_round_progress(task_id)
        return {
            'task_id': str(task_id),
            'status': status.get('status', 'idle'),
            'tc_rel_id': status.get('tc_rel_id'),
            'round_progress': round_progress,
        }


e2e_service = E2EService()
