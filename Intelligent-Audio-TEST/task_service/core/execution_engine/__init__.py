import threading
from datetime import timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from collections import deque

from shared.utils.event_manager import EventManager
from shared.utils.config_manager import config_manager
from shared.utils.redis_pubsub import EventBus, EventChannel, EventType

# 导入所有 Mixin
from task_service.core.execution_engine._scheduler_mixin import SchedulerMixin
from task_service.core.execution_engine._progress_mixin import ProgressMixin
from task_service.core.execution_engine._task_control_mixin import TaskControlMixin
from task_service.core.execution_engine._case_execution_mixin import CaseExecutionMixin
from task_service.core.execution_engine._task_runner_mixin import TaskRunnerMixin

# 重导出 gRPC 封装函数，保持向后兼容
from task_service.core.execution_engine._grpc_helpers import (
    _stop_task_audio_via_grpc,
    _cleanup_devices_via_grpc,
    _unregister_task_events_via_grpc,
    _get_task_events_via_grpc,
    _register_task_events_via_grpc,
    _execute_e2e_case_via_grpc,
)


# 执行引擎类，负责管理和执行测试任务
# 实现单例模式，确保全局只有一个执行引擎实例
class ExecutionEngine(SchedulerMixin, ProgressMixin, TaskControlMixin, CaseExecutionMixin, TaskRunnerMixin):
    # 单例模式相关变量
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """单例模式实现，确保全局只有一个ExecutionEngine实例

        Returns:
            ExecutionEngine: 单例实例
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ExecutionEngine, cls).__new__(cls)
                # 初始化工作线程字典，用于存储运行中的任务线程
                cls._instance.workers = {}
                # 初始化停止标志字典，用于控制任务停止
                cls._instance.stop_flags = {}
                # 初始化暂停标志字典，用于控制任务暂停/恢复
                cls._instance.pause_flags = {}
                # 初始化API执行器字典，用于存储API任务的线程池
                cls._instance.api_executors = {}
                # 东八区时区定义，用于统一时间格式
                cls._instance.utc_plus_8 = timezone(timedelta(hours=8))
                # 初始化执行器和管理器
                cls._instance.api_entry_status = {}  # 存储 API 入口 (Master) 的状态: {url: {'available': True, 'fail_count': 0}}
                cls._instance.api_entry_lock = threading.Lock()
                cls._instance.event_manager = EventManager(cls._instance)  # 事件管理器，用于处理事件通知
                # API/E2E 执行逻辑已下沉到各自微服务（api_test_service / e2e_test_service）
                # task_service 通过 gRPC 调用，不再持有本地执行器实例

                # 从配置文件加载超时时间
                cls._instance.test_case_wait_time = config_manager.get_value('execution_engine', 'test_case_wait_time', 300)  # 等待测试用例执行完成的超时时间（秒）
                cls._instance.max_queue_size = config_manager.get_value('execution_engine', 'max_queue_size', 100)  # 任务队列最大长度

                # 任务队列管理
                cls._instance.task_queue = deque()  # 任务队列，使用deque提高效率
                cls._instance.queue_lock = threading.Lock()  # 队列锁，确保线程安全
                cls._instance.running_tasks = {}  # 运行中任务，{task_id: task_type}
                cls._instance.running_apis = set()  # 运行中API集合，存储正在使用的API ID
                cls._instance.running_e2e = False  # E2E任务运行状态
                cls._instance.scheduler_event = threading.Event()  # 调度器事件，用于事件驱动

                # 任务级别的锁，用于确保状态更新的原子性
                cls._instance.task_locks = {}  # 任务锁字典，{task_id: threading.Lock()}
                # 任务进度缓存，减少数据库查询
                cls._instance.task_progress_cache = {}  # 任务进度缓存，{task_id: {progress_data}}
                # 进度更新节流，避免频繁的进度更新
                cls._instance.last_progress_update = {}  # 上次进度更新时间，{task_id: timestamp}
                # 多轮进度内存缓存，{tc_rel_id: {'current': N, 'total': M}}
                cls._instance.round_progress_cache = {}
                # 任务完成事件，{task_id: threading.Event}，用于替代忙等待
                cls._instance.task_completion_events = {}

                # 调度器相关初始化（在 _log 方法定义后启动）
                cls._instance.scheduler_thread = None
                cls._instance.scheduler_stop_event = None
                cls._instance._scheduler_initialized = False

                # 独立线程池隔离 - 解决前端刷新导致音频播放卡顿问题
                # 微服务化后：API 执行下沉到 api_test_service，设备控制下沉到 e2e_test_service，
                # 音频播放下沉到 e2e_test_service.AudioService，task_service 不再持有这些线程池。
                # 保留 _reference_refresh_pool 供 reference_refresh_task 使用
                cls._instance._reference_refresh_pool = ThreadPoolExecutor(
                    max_workers=2,
                    thread_name_prefix='ref_refresh_'
                )

                # 事件总线订阅（监听用例完成事件，替代 DB 轮询）
                cls._instance._event_bus = EventBus()
                cls._instance._event_subscriber_thread = None
        return cls._instance

    def _on_case_event(self, payload):
        """处理用例级事件（执行完成/评估完成/失败）

        事件驱动改造: 各服务完成后发布事件，此处订阅后唤醒等待线程，
        替代 DB 轮询。同时保留 DB 轮询作为兜底。
        """
        try:
            task_id = payload.get('task_id')
            if not task_id:
                return
            # 尝试转换为 int（task_id 在事件中被序列化为 str）
            try:
                task_id = int(task_id)
            except (ValueError, TypeError):
                pass

            # 唤醒等待该任务完成的线程
            completion_event = self.task_completion_events.get(task_id)
            if completion_event:
                completion_event.set()

            # 触发进度更新
            self._emit_progress(task_id, force=True)

            # 触发调度器检查（可能有 pending 任务需要继续）
            self.trigger_scheduler_check()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"处理用例事件失败: {e}")

    def _on_task_event(self, payload):
        """处理任务级事件（任务完成/失败）

        事件驱动改造: 评估服务在任务状态变更时发布事件，此处订阅后更新本地缓存。
        """
        try:
            task_id = payload.get('task_id')
            if not task_id:
                return
            try:
                task_id = int(task_id)
            except (ValueError, TypeError):
                pass

            # 唤醒等待该任务完成的线程
            completion_event = self.task_completion_events.get(task_id)
            if completion_event:
                completion_event.set()

            # 触发进度更新
            self._emit_progress(task_id, force=True)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"处理任务事件失败: {e}")

    def start_event_subscribers(self):
        """启动事件总线订阅线程（在 _log 方法定义后调用）"""
        if self._event_subscriber_thread is not None:
            return

        # 订阅用例级事件
        self._event_bus.start_subscriber(
            EventChannel.CASE_EVENTS,
            {
                EventType.CASE_EXECUTION_COMPLETED: self._on_case_event,
                EventType.CASE_EVALUATION_COMPLETED: self._on_case_event,
                EventType.CASE_FAILED: self._on_case_event,
            },
            name='TaskEventSub-CaseEvents',
        )

        # 订阅任务级事件
        self._event_bus.start_subscriber(
            EventChannel.TASK_EVENTS,
            {
                EventType.TASK_COMPLETED: self._on_task_event,
                EventType.TASK_FAILED: self._on_task_event,
                EventType.TASK_STOPPED: self._on_task_event,
            },
            name='TaskEventSub-TaskEvents',
        )

        self._event_subscriber_thread = True  # 标记已启动
        self._log(level='INFO', content="事件总线订阅线程已启动")

    def shutdown(self):
        if hasattr(self, '_reference_refresh_pool') and self._reference_refresh_pool:
            self._reference_refresh_pool.shutdown(wait=False)
        for task_id, executor in list(self.api_executors.items()):
            executor.shutdown(wait=False)
        self.api_executors.clear()
        self._stop_scheduler()
        self._log(level='INFO', content="执行引擎已关闭")


# 创建ExecutionEngine实例，供外部调用
execution_engine = ExecutionEngine()
