"""
E2E Test Service - 服务接口层
接收 Task Service 的 gRPC 请求，执行 E2E 测试

引擎上下文委托给 infrastructure/e2e_engine_context.py。
"""
import threading
from shared.utils.log_handler import log_and_emit


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

    def init_app(self, app=None):
        """初始化服务

        Args:
            app: 保留参数以兼容旧调用，内部不再使用（DB session 由 gRPC 拦截器/线程管理）
        """
        from e2e_test_service.infrastructure.e2e_engine_context import E2EEngineContext
        self._engine_ctx = E2EEngineContext()
        self._executor = None
        self._task_status = {}
        self._task_threads = {}
        self._task_lock = threading.Lock()
        self._initialized = True

    @property
    def executor(self):
        """懒加载 E2EExecutor，注入本地引擎上下文"""
        if self._executor is None:
            from e2e_test_service.application.services.e2e_executor import E2EExecutor
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
        DB session 由 gRPC 线程的 scoped_session 提供，无需 app context。
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
            tb = traceback.format_exc()
            log_and_emit(
                level='ERROR',
                module='E2EService',
                content=f"start_e2e_case 执行异常: task_id={task_id}, tc_rel_id={tc_rel_id}, error={e}\n{tb}",
                category='execution',
                source='e2e_test_service',
                task_id=str(task_id),
            )
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
                'traceback': tb,
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
