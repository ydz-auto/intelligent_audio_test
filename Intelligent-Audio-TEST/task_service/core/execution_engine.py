import threading
import time
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from shared.models.models import Task, TaskCase,  TestCase, API
from shared.models.database import db
from shared.utils.log_handler import log_and_emit

# 跨服务调用：通过 gRPC AudioService 调用音频引擎
from shared.clients.grpc_clients import get_audio_service_stub
from shared.utils.event_manager import EventManager
from shared.utils.config_manager import config_manager
from shared.utils import distributed_coordinator as _dc
# 跨服务调用：通过 gRPC DeviceService 调用设备驱动工厂
from shared.clients.grpc_clients import get_device_service_stub
# 跨服务调用：通过 gRPC 调用 E2E/API 测试执行（e2e_test_service / api_test_service）
from shared.clients.grpc_clients import get_e2e_execution_service_stub, get_api_test_service_stub

# 执行引擎类，负责管理和执行测试任务
# 实现单例模式，确保全局只有一个执行引擎实例
class ExecutionEngine:
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
        return cls._instance

    def shutdown(self):
        if hasattr(self, '_reference_refresh_pool') and self._reference_refresh_pool:
            self._reference_refresh_pool.shutdown(wait=False)
        for task_id, executor in list(self.api_executors.items()):
            executor.shutdown(wait=False)
        self.api_executors.clear()
        self._stop_scheduler()
        self._log(level='INFO', content="执行引擎已关闭")

    def _init_scheduler(self):
        """初始化并启动后台调度线程（在 _log 方法定义后调用）"""
        if self._scheduler_initialized:
            return

        self.scheduler_stop_event = threading.Event()
        self.scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="TaskScheduler",
            daemon=True
        )
        self.scheduler_thread.start()
        self._scheduler_initialized = True
        self._log(level='INFO', content="任务调度器已启动")

    def _start_scheduler(self):
        """启动后台调度线程，用于自动检查和启动 pending 状态的任务"""
        self._init_scheduler()

    def _stop_scheduler(self):
        """停止后台调度线程"""
        self.scheduler_stop_event.set()
        self.scheduler_event.set()  # 唤醒调度器以便快速退出
        if self.scheduler_thread is not None and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)
        self._log(level='INFO', content="任务调度器已停止")
    
    def trigger_scheduler_check(self):
        """触发调度器立即检查，用于事件驱动"""
        self.scheduler_event.set()

    def _scheduler_loop(self):
        """调度器主循环，定期检查并启动 pending 任务，支持事件驱动"""
        if self.scheduler_stop_event is None:
            return

        check_interval = config_manager.get_value('execution_engine', 'scheduler_interval', 3)

        while not self.scheduler_stop_event.is_set():
            try:
                self._schedule_pending_tasks()
            except Exception as e:
                print(f"[Scheduler] 调度器检查任务时发生错误: {str(e)}")
            finally:
                # 每轮循环结束清理本线程 DB session，防止连接泄漏
                try:
                    from shared.models.database import remove_db_session
                    remove_db_session()
                except Exception:
                    pass

            self.scheduler_event.wait(timeout=check_interval)
            self.scheduler_event.clear()

    def _schedule_pending_tasks(self):
        """检查并自动启动 pending 状态的任务

        调度规则：
        - E2E 任务：同时只能运行一个
        - API 任务：可以并发运行，但不能使用相同的 API
        """
        local_db_session = db.session()
        try:
            pending_tasks = local_db_session.query(Task).filter_by(
                status='pending',
                deleted=False
            ).order_by(Task.created_at.asc()).all()

            if not pending_tasks:
                return

            for task in pending_tasks:
                if self.scheduler_stop_event.is_set():
                    break

                task_id = task.id

                if task_id in self.workers and self.workers[task_id].is_alive():
                    continue

                with self.queue_lock:
                    if any(t['id'] == task_id for t in self.task_queue):
                        continue

                from shared.models.models import TaskAPI
                task_apis = local_db_session.query(TaskAPI).filter_by(task_id=task_id).all()
                api_ids = [task_api.api_id for task_api in task_apis]

                can_run = False

                if task.type == 'e2e':
                    if not self.running_e2e:
                        can_run = True
                else:
                    overlapping_apis = set(api_ids) & self.running_apis
                    if not overlapping_apis:
                        can_run = True

                if can_run:
                    try:
                        success, message = self.start_task(task_id)
                        if success:
                            print(f"[Scheduler] 任务 {task_id} ({task.type}) 自动启动成功")
                        else:
                            print(f"[Scheduler] 任务 {task_id} 自动启动失败: {message}")
                    except Exception as e:
                        print(f"[Scheduler] 自动启动任务 {task_id} 时发生错误: {str(e)}")

        except Exception as e:
            print(f"[Scheduler] 调度器处理任务时发生错误: {str(e)}")
        finally:
            local_db_session.close()

    def _emit_progress(self, task, force=False):
        """发送任务进度更新

        Args:
            task: 任务对象，包含当前任务状态信息
            force: 是否强制更新，跳过节流逻辑
        """
        # 获取任务ID
        task_id = None
        task_status = None
        if isinstance(task, (str, int)):
            task_id = str(task)
        elif hasattr(task, 'id'):
            task_id = str(task.id)
            task_status = getattr(task, 'status', None)

        if task_id and not force:
            if task_status in ['running', 'completed', 'failed', 'stopped', 'paused']:
                force = True
            else:
                current_time = time.time()
                last_update = self.last_progress_update.get(task_id, 0)
                if current_time - last_update < 0.5:
                    return
                self.last_progress_update[task_id] = current_time

        self.event_manager.emit_progress(task, force=force)

    @staticmethod
    def refresh_task_counts_atomic(task_id):
        """原子刷新任务的 completed/failed/total_cases 计数（多实例安全）

        用 SQL 子查询一次性 UPDATE，避免读-改-写的丢失更新问题。
        所有需要更新任务统计的地方都应调用此方法，而非直接赋值。
        """
        from sqlalchemy import text
        from shared.models.database import _engine_ref
        sql = text("""
            UPDATE test_tasks SET
                completed_cases = (
                    SELECT COUNT(*) FROM task_case_relations
                    WHERE task_id = :task_id AND status = 'completed'
                ),
                failed_cases = (
                    SELECT COUNT(*) FROM task_case_relations
                    WHERE task_id = :task_id AND status = 'failed'
                )
            WHERE id = :task_id
        """)
        try:
            with _engine_ref[0].connect() as conn:
                conn.execute(sql, {'task_id': task_id})
                conn.commit()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"原子刷新任务 {task_id} 计数失败: {e}")

    def update_case_round_progress(self, task_id, tc_rel_id, current_round, total_rounds):
        """
        Update round progress for a multi-round test case (in-memory cache).
        
        The round progress is stored in memory and read by event_manager
        during progress emission. This avoids needing a DB migration for
        an extra_data column on TaskCase.
        
        Args:
            task_id: Task ID
            tc_rel_id: TaskCase relation ID
            current_round: Current round number (0-indexed)
            total_rounds: Total number of rounds
        """
        self.round_progress_cache[tc_rel_id] = {
            'current': current_round + 1,
            'total': total_rounds,
        }
        # Force progress push on round change
        self._emit_progress(task_id, force=True)

    def _emit_alert(self, task_id, message, level='error'):
        """发送任务告警信息
        
        Args:
            task_id: 任务ID
            message: 告警消息内容
            level: 告警级别，默认为'error'
        """
        self.event_manager.emit_alert(task_id, message, level)

    def notify_case_completed(self, task_id):
        """通知等待线程：某个用例的执行或评估已完成
        
        唤醒 _run_task 中的 event.wait()，替代 time.sleep 忙等待。
        由 evaluation_service._post_evaluate_updates 和 api_executor 调用。
        """
        event = self.task_completion_events.get(task_id)
        if event:
            event.set()
            event.clear()

    def _log(self, level, content, task_id=None, test_case_id=None, api_id=None, **kwargs):
        """统一日志记录方法"""
        log_and_emit(
            level=level,
            module='Engine',
            content=content,
            category=kwargs.pop('category', 'execution'),
            source='backend',
            task_id=task_id,
            api_id=api_id,
            test_case_id=test_case_id,
            **kwargs
        )

    def start_task(self, task_id):
        """启动测试任务

        Args:
            task_id: 任务ID

        Returns:
            tuple: (是否成功, 状态消息)
        """
        # 检查任务是否已在运行或队列中
        if task_id in self.workers and self.workers[task_id].is_alive():
            return False, "任务已在运行中"
        
        with self.queue_lock:
            if any(t['id'] == task_id for t in self.task_queue):
                return False, "任务已在队列中"

        # 获取任务类型和关联的API
        local_db_session = db.session()
        try:
            task = local_db_session.get(Task, task_id)
            if not task:
                return False, "任务不存在"
            
            task_type = task.type
            
            # 获取任务关联的API ID
            from shared.models.models import TaskAPI
            task_apis = local_db_session.query(TaskAPI).filter_by(task_id=task_id).all()
            api_ids = [task_api.api_id for task_api in task_apis]
        finally:
            local_db_session.close()
        
        # 检查是否可以立即执行
        with self.queue_lock:
            can_run = False
            
            if task_type == 'e2e':
                # E2E任务：同时只允许一个E2E任务运行
                if not self.running_e2e:
                    can_run = True
            else:
                # API任务：检查是否有相同API在运行
                overlapping_apis = set(api_ids) & self.running_apis
                if not overlapping_apis:
                    can_run = True
            
            if can_run:
                # 可以立即执行，创建停止和暂停事件
                stop_event = threading.Event()
                pause_event = threading.Event()
                pause_event.set()  # 初始状态为非暂停

                # 创建任务完成事件（用于替代忙等待）
                self.task_completion_events[task_id] = threading.Event()

                # 注册任务控制事件（通过 gRPC 同步到 e2e_test_service）
                _register_task_events_via_grpc(task_id, stop_event, pause_event)

                # 更新运行状态
                self.running_tasks[task_id] = task_type
                if task_type == 'e2e':
                    self.running_e2e = True
                else:
                    self.running_apis.update(api_ids)

                # 更新任务状态为running
                # 多实例下用 DB 条件 UPDATE 做任务抢占 CAS，避免重复启动
                local_db_session = db.session()
                try:
                    # CAS: 只有 pending/queued 状态才能翻转为 running
                    claimed = local_db_session.query(Task).filter(
                        Task.id == task_id,
                        Task.status.in_(['pending', 'queued'])
                    ).update({Task.status: 'running'}, synchronize_session=False)
                    if claimed != 1:
                        # 已被其它实例抢占，回滚本地运行状态
                        local_db_session.rollback()
                        with self.queue_lock:
                            self.running_tasks.pop(task_id, None)
                            if task_type == 'e2e':
                                self.running_e2e = False
                            else:
                                self.running_apis.difference_update(api_ids)
                        return False, "任务已被其它实例启动"
                    local_db_session.commit()
                finally:
                    local_db_session.close()

                # 创建任务执行线程
                thread = threading.Thread(target=self._run_task, args=(task_id, stop_event, pause_event))
                self.workers[task_id] = thread
                self.stop_flags[task_id] = stop_event
                self.pause_flags[task_id] = pause_event

                # 启动线程
                thread.start()
                return True, "任务已启动"
            else:
                if len(self.task_queue) >= self.max_queue_size:
                    return False, f"任务队列已满 ({self.max_queue_size})"
                self.task_queue.append({
                    'id': task_id,
                    'type': task_type,
                    'api_ids': api_ids,
                })
            
            # 更新任务状态为queued
            local_db_session = db.session()
            try:
                task = local_db_session.get(Task, task_id)
                if task:
                    task.status = 'queued'
                    local_db_session.commit()
            finally:
                local_db_session.close()
            
            # 触发调度器立即检查
            self.trigger_scheduler_check()
            
            return True, "任务已加入队列"
    
    def _check_queue(self):
        """检查任务队列，启动可以执行的任务，一次启动多个可执行任务"""
        local_db_session = db.session()
        try:
            tasks_to_start = []
            
            with self.queue_lock:
                remaining_tasks = deque()
                
                while self.task_queue:
                    queued_task = self.task_queue.popleft()
                    task_id = queued_task['id']
                    task_type = queued_task['type']
                    api_ids = queued_task['api_ids']

                    task = local_db_session.get(Task, task_id)
                    task_status = task.status if task else None
                    
                    if task_status == 'stopped':
                        continue
                    
                    can_run = False
                    
                    if task_type == 'e2e':
                        if not self.running_e2e:
                            can_run = True
                    else:
                        overlapping_apis = set(api_ids) & self.running_apis
                        if not overlapping_apis:
                            can_run = True
                    
                    if can_run:
                        self.running_tasks[task_id] = task_type
                        if task_type == 'e2e':
                            self.running_e2e = True
                        else:
                            self.running_apis.update(api_ids)
                        
                        if task:
                            task.status = 'running'
                            local_db_session.commit()
                        
                        tasks_to_start.append({
                            'task_id': task_id,
                            'task': task
                        })
                    else:
                        remaining_tasks.append(queued_task)
                
                self.task_queue = remaining_tasks
            
            for task_info in tasks_to_start:
                task_id = task_info['task_id']

                stop_event = threading.Event()
                pause_event = threading.Event()
                pause_event.set()

                # 创建任务完成事件（用于替代忙等待）
                self.task_completion_events[task_id] = threading.Event()

                thread = threading.Thread(target=self._run_task, args=(task_id, stop_event, pause_event))
                self.workers[task_id] = thread
                self.stop_flags[task_id] = stop_event
                self.pause_flags[task_id] = pause_event
                
                thread.start()
        finally:
            local_db_session.close()
    
    def remove_from_queue(self, task_id):
        """
        从任务队列中移除指定任务
        
        Args:
            task_id: 任务ID
        """
        with self.queue_lock:
            new_queue = deque()
            removed = False
            for queued_task in self.task_queue:
                if queued_task['id'] == task_id:
                    removed = True
                else:
                    new_queue.append(queued_task)
            self.task_queue = new_queue
        return removed

    def control_task(self, task_id, action):
        """
        控制任务执行（暂停、恢复、停止）

        Args:
            task_id: 任务ID
            action: 操作类型，可选值：'pause', 'resume', 'stop'

        Returns:
            tuple: (是否成功, 状态消息)
        """
        # 处理停止任务操作，从队列中移除
        if action == 'stop':
            self.remove_from_queue(task_id)

        # 使用本地会话确保独立可靠的会话
        local_db_session = db.session()
        try:
            task = local_db_session.get(Task, task_id)
            if not task:
                return False, "任务不存在"

            # 检查任务状态是否允许执行操作
            if action == 'pause':
                if task.status not in ['running', 'queued']:
                    return False, "只有执行中或排队中的任务才能暂停"
            elif action == 'resume':
                if task.status != 'paused':
                    return False, "只有已暂停的任务才能恢复"
            elif action == 'stop':
                if task.status not in ['running', 'paused', 'queued', 'evaluating']:
                    return False, "只有执行中、已暂停、排队中或评估中的任务才能停止"

            # 对于停止操作，即使任务不在workers中，也应该执行
            if action == 'stop':
                # 更新任务状态为stopped
                task.status = 'stopped'
                task.completed_at = datetime.now(self.utc_plus_8)
                
                # 只处理未完成的用例（执行中、排队中、待执行），保留已完成用例的状态
                cases = local_db_session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    ~TaskCase.status.in_(['completed', 'failed', 'skipped'])
                ).all()
                for tc in cases:
                    tc.status = 'skipped'
                    tc.execution_status = 'stopped'
                    tc.evaluation_status = 'stopped'
                    tc.started_at = None
                    tc.completed_at = datetime.now(self.utc_plus_8)
                    tc.duration = None
                    tc.error_message = '任务被手动停止'
                
                local_db_session.commit()

                # 分布式停止信号（多实例下通知所有实例的执行线程）
                # 优先广播，确保 gRPC 调用失败时不阻塞停止信号传播
                _dc.set_flag(f'task:stop:{task_id}')
                _dc.clear_flag(f'task:pause:{task_id}')

                # 如果任务在workers中，设置停止标志
                if task_id in self.workers:
                    self.stop_flags[task_id].set()  # 设置停止标志
                    self.pause_flags[task_id].set()  # 确保任务不处于暂停状态，以便能响应停止指令
                    # 唤醒等待线程，使其能立即检测到 stop_event
                    self.notify_case_completed(task_id)

                # 停止所有音频播放（通过 gRPC 调用 e2e_test_service 的 AudioService）
                # 放在 Redis 标志位之后，gRPC 失败不影响停止信号传播
                try:
                    _stop_task_audio_via_grpc(task_id)
                except Exception as e:
                    self._log(level='WARNING',
                              content=f"停止音频播放 gRPC 调用失败(不阻塞停止流程): {e}",
                              task_id=task_id)
                self._emit_progress(task)  # 发送进度更新

                # 通过 gRPC 通知 e2e_test_service 同步停止事件
                if task_id in self.workers:
                    try:
                        _register_task_events_via_grpc(
                            task_id, self.stop_flags[task_id], self.pause_flags[task_id]
                        )
                    except Exception as e:
                        self._log(level='WARNING',
                                  content=f"同步停止事件 gRPC 调用失败(不阻塞停止流程): {e}",
                                  task_id=task_id)
                
                # 立即清理运行状态，避免新任务进入排队
                with self.queue_lock:
                    if task_id in self.running_tasks:
                        task_type = self.running_tasks[task_id]
                        del self.running_tasks[task_id]
                        
                        if task_type == 'e2e':
                            self.running_e2e = False
                        else:
                            # 释放占用的 API ID
                            try:
                                from shared.models.models import TaskAPI
                                task_apis = local_db_session.query(TaskAPI).filter_by(task_id=task_id).all()
                                for api_rel in task_apis:
                                    if api_rel.api_id in self.running_apis:
                                        self.running_apis.remove(api_rel.api_id)
                            except Exception as e:
                                self._log(level='WARNING', content=f"清理API资源时发生错误: {str(e)}", task_id=task_id)
                
                # 清理线程和标志位
                self.workers.pop(task_id, None)
                self.stop_flags.pop(task_id, None)
                self.pause_flags.pop(task_id, None)
                self.task_completion_events.pop(task_id, None)
                # 清理进度缓存，避免内存泄漏
                self.task_progress_cache.pop(task_id, None)
                self.last_progress_update.pop(task_id, None)
                # 清理多轮进度缓存（key 为 tc_rel_id，需查询当前任务的用例 ID）
                try:
                    tc_rel_ids = [
                        tc_id for (tc_id,) in
                        local_db_session.query(TaskCase.id).filter_by(task_id=task_id).all()
                    ]
                    for tc_rel_id in tc_rel_ids:
                        self.round_progress_cache.pop(tc_rel_id, None)
                except Exception:
                    pass

                # 检查队列并启动下一个任务
                self._check_queue()

                # 通过 gRPC 调用 e2e_test_service 的 DeviceService
                _cleanup_devices_via_grpc(task_id)
                _unregister_task_events_via_grpc(task_id)
                
                return True, "任务已停止"
            else:
                # 对于暂停和恢复操作，需要任务在workers中
                if action == 'pause' and task.status == 'queued':
                    self.remove_from_queue(task_id)
                    task.status = 'paused'
                    local_db_session.commit()
                    self._emit_progress(task)
                    return True, "任务已暂停"

                if action == 'resume' and task_id not in self.workers:
                    if task.type == 'api':
                        from shared.models.models import TaskAPI
                        api_ids = [
                            rel.api_id
                            for rel in local_db_session.query(TaskAPI).filter_by(task_id=task_id).all()
                        ]
                        with self.queue_lock:
                            self.task_queue.append({"id": task.id, "type": "api", "api_ids": api_ids, "app": app})
                        task.status = 'queued'
                        local_db_session.commit()
                        self._emit_progress(task)
                        self.trigger_scheduler_check()
                        return True, "任务已恢复"
                    return False, "未找到运行中的任务"

                if task_id not in self.workers:
                    return False, "未找到运行中的任务"

                if action == 'pause':
                    # 暂停任务
                    self.pause_flags[task_id].clear()  # 清除暂停标志，触发暂停
                    # 分布式暂停信号（多实例下通知所有实例的执行线程）
                    _dc.set_flag(f'task:pause:{task_id}')
                    # 通过 gRPC 通知 e2e_test_service 同步暂停事件
                    _register_task_events_via_grpc(
                        task_id, self.stop_flags[task_id], self.pause_flags[task_id]
                    )
                    task.status = 'paused'  # 更新任务状态
                    
                    # 对于 API 任务，不重置执行中的用例状态为 pending
                    # 因为 API 线程是在 pause_event 上阻塞，恢复时会自动继续执行
                    # 如果重置为 pending，会导致调度器重新启动新线程，造成重复执行
                    if task.type == 'e2e':
                        # E2E 任务是同步顺序执行的，暂停时可以将当前正在执行的用例重置
                        # 但为了统一和简单，建议也不重置，让 E2E 执行器内部处理暂停
                        running_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, execution_status='running').all()
                        for tc in running_cases:
                            tc.execution_status = 'pending'
                            tc.completed_at = None
                            tc.duration = None
                    
                    local_db_session.commit()
                    # 暂停时停止所有音频播放（通过 gRPC AudioService）
                    _stop_task_audio_via_grpc(task_id)
                    # 暂停时清理设备并注销事件（通过 gRPC DeviceService）
                    _cleanup_devices_via_grpc(task_id)
                    _unregister_task_events_via_grpc(task_id)
                    self._emit_progress(task)  # 发送进度更新
                    return True, "任务已暂停"
                elif action == 'resume':
                    # 恢复任务
                    # 检查事件是否还存在，如果不存在需要重新注册
                    # 跨服务调用：通过 gRPC DeviceService 获取任务事件
                    if _get_task_events_via_grpc(task_id) is None:
                        # 重新注册事件
                        if task_id not in self.pause_flags:
                            self.pause_flags[task_id] = threading.Event()
                        if task_id not in self.stop_flags:
                            self.stop_flags[task_id] = threading.Event()
                        # 跨服务调用：通过 gRPC DeviceService 注册任务事件
                        _register_task_events_via_grpc(task_id, self.stop_flags[task_id], self.pause_flags[task_id])

                    self.pause_flags[task_id].set()  # 设置暂停标志，恢复执行
                    # 清除分布式暂停信号（多实例下通知所有实例恢复执行）
                    _dc.clear_flag(f'task:pause:{task_id}')
                    # 通过 gRPC 通知 e2e_test_service 同步恢复事件
                    _register_task_events_via_grpc(
                        task_id, self.stop_flags[task_id], self.pause_flags[task_id]
                    )
                    task.status = 'running'  # 更新任务状态
                    local_db_session.commit()
                    self._emit_progress(task)  # 发送进度更新
                    return True, "任务已恢复"
                return False, "无效的操作指令"
        finally:
            local_db_session.close()

    def _run_task(self, task_id, stop_event, pause_event):
        """执行测试任务的核心方法

        Args:
            task_id: 任务ID
            stop_event: 停止事件，用于通知任务停止
            pause_event: 暂停事件，用于通知任务暂停/恢复
        """
        try:
            from shared.models.models import Log, TaskCase
            from shared.models.database import remove_db_session
            
            # 使用本地会话获取任务对象
            local_db_session = db.session()
            try:
                # 获取任务对象
                task = local_db_session.get(Task, task_id)
                if not task:
                    self._log(
                        level='ERROR', 
                        content=f"任务 {task_id} 不存在，无法执行",
                        task_id=task_id
                    )
                    return
                
                # 记录任务开始日志
                self._log(
                    level='INFO', 
                    content=f"开始执行任务 {task_id}, 类型: {task.type}",
                    task_id=task_id
                )

                # 更新任务状态为运行中，并记录开始时间
                task.status = 'running'
                task.started_at = datetime.now(self.utc_plus_8)
                local_db_session.commit()
                # 发送进度更新，传递task对象以便触发强制更新逻辑
                self._emit_progress(task)
            finally:
                local_db_session.close()

            try:
                # 使用本地会话确保独立可靠的会话
                local_db_session = db.session()
                try:
                    # 重新获取任务对象，确保它在有效会话中
                    task = local_db_session.get(Task, task_id)
                    if not task:
                        self._log(
                            level='ERROR', 
                            content=f"任务 {task_id} 不存在，无法执行",
                            task_id=task_id
                        )
                        return
                    
                    # API任务初始化
                    if task.type == 'api':
                        try:
                            from shared.models.models import TaskAPI
                            # 获取API配置
                            task_api = local_db_session.query(TaskAPI).filter_by(task_id=task.id).first()
                            api_config = local_db_session.get(API, task_api.api_id) if task_api else None
                            
                            # 获取可用的API端点
                            available_endpoints = []
                            if api_config and api_config.api_endpoints:
                                available_endpoints = [ep for ep in api_config.api_endpoints if ep.get('status') == 'online']
                                available_endpoints.sort(key=lambda x: x.get('priority', 0), reverse=True)
                            
                            # 确定最大工作线程数
                            if available_endpoints:
                                # 计算所有可用端点的最大进程数之和
                                max_workers = sum(ep.get('max_process', 5) for ep in available_endpoints)
                            elif api_config:
                                max_workers = api_config.default_max_process
                            else:
                                max_workers = 5
                            
                            # 保存API配置和可用端点到任务对象
                            task._api_config = api_config
                            task._available_endpoints = available_endpoints
                            
                            # 微服务化后：不再创建本地线程池，API 用例通过 gRPC 调用 api_test_service 执行
                            # api_test_service 内部管理自己的线程池和并发控制
                            self._log(
                                level='INFO', 
                                content=f"API任务 {task_id} 初始化成功，执行下沉到 api_test_service",
                                task_id=task_id,
                                api_id=api_config.id if api_config else None
                            )
                        except Exception as e:
                            self._log(
                                level='ERROR', 
                                content=f"API任务 {task_id} 初始化失败: {str(e)}",
                                task_id=task_id
                            )
                            # API任务初始化失败，将任务标记为失败
                            task.status = 'failed'
                            task.completed_at = datetime.now(self.utc_plus_8)
                            task.error_message = f"API任务初始化失败: {str(e)}"
                            local_db_session.commit()
                            return
                finally:
                    local_db_session.close()

                # 主循环：处理测试用例
                while not stop_event.is_set():
                    # 使用本地会话确保独立可靠的会话
                    local_db_session = db.session()
                    try:
                        # 重新获取任务对象，确保它在有效会话中
                        task = local_db_session.get(Task, task_id)
                        if not task:
                            self._log(
                                level='ERROR', 
                                content=f"任务 {task_id} 不存在，无法执行",
                                task_id=task_id
                            )
                            break
                        
                        # 获取下一个待执行的测试用例
                        tc_rel = local_db_session.query(TaskCase).filter_by(
                            task_id=task_id, 
                            execution_status='pending'
                        ).order_by(TaskCase.created_at.asc()).first()

                        if not tc_rel:
                            # 对于API任务，检查是否还有正在执行或评估的用例
                            if task.type == 'api':
                                # 检查是否有正在执行或评估的用例
                                in_progress_count = local_db_session.query(TaskCase).filter(
                                    TaskCase.task_id == task_id,
                                    TaskCase.execution_status.in_(['queued', 'running'])
                                ).count()

                                # 检查是否有正在评估的用例（评估可能在执行完成后才开始）
                                evaluating_count = local_db_session.query(TaskCase).filter(
                                    TaskCase.task_id == task_id,
                                    TaskCase.evaluation_status.in_(['running', 'calculating', 'queued', 'pending'])
                                ).count()
                                
                                if in_progress_count > 0 or evaluating_count > 0:
                                    # 有用例正在执行或评估，等待完成事件通知
                                    total_in_progress = in_progress_count + evaluating_count
                                    self._log(
                                        level='DEBUG',
                                        content=f"等待 {total_in_progress} 个执行中/评估中的用例完成 (执行中: {in_progress_count}, 评估中: {evaluating_count})...",
                                        task_id=task_id
                                    )
                                    
                                    # 释放当前数据库会话，等待事件通知
                                    local_db_session.close()
                                    
                                    # 事件驱动等待：评估/执行完成时会被 notify_case_completed 唤醒
                                    completion_event = self.task_completion_events.get(task_id)
                                    if completion_event:
                                        completion_event.wait(timeout=5)
                                    else:
                                        time.sleep(1)
                                    
                                    # 继续下一次循环检查
                                    continue
                            
                            # 确认没有待执行和执行中的用例，真正完成
                            self._log(
                                level='INFO',
                                content=f"任务 {task_id} 所有用例执行完成，退出主循环",
                                task_id=task_id
                            )
                            break 
                        
                        # 检查是否需要暂停
                        if not pause_event.is_set():
                            self._emit_progress(task)
                            pause_event.wait()  # 等待暂停标志被设置（恢复执行）

                        # 检查是否需要停止
                        if stop_event.is_set():
                            break

                        # 设备状态检查（仅E2E任务需要）
                        device_check_passed = True
                        error_message = ""

                        if task.type == 'e2e':
                            self._log(
                                level='DEBUG',
                                content=f"开始检查设备状态: 任务ID={task_id}, 用例ID={tc_rel.id}",
                                task_id=task_id
                            )
                            
                            from shared.models.models import Device, TaskDevice
                            task_device_relations = local_db_session.query(TaskDevice).filter_by(task_id=task_id).all()
                            device_ids = [rel.device_id for rel in task_device_relations]
                            
                            self._log(
                                level='DEBUG',
                                content=f"设备关联信息: 关联数={len(task_device_relations)}, 设备ID列表={device_ids}",
                                task_id=task_id
                            )
                            
                            if not device_ids:
                                device_check_passed = True
                                self._log(
                                    level='DEBUG',
                                    content=f"没有关联设备，设备检查通过",
                                    task_id=task_id
                                )
                            else:
                                devices = local_db_session.query(Device).filter(Device.id.in_(device_ids)).all()
                                self._log(
                                    level='DEBUG',
                                    content=f"查询到设备数量={len(devices)}",
                                    task_id=task_id
                                )
                                for device in devices:
                                    device_status = device.status
                                    self._log(
                                        level='DEBUG',
                                        content=f"检查设备状态: 设备ID={device.id}, 设备名称={device.name}, 状态={device_status}",
                                        task_id=task_id,
                                        device_id=device.id
                                    )
                                    if device_status != 'online':
                                        device_check_passed = False
                                        error_message = f"被测设备 {device.name} 离线，无法执行测试"
                                        self._log(
                                            level='ERROR',
                                            content=error_message,
                                            task_id=task_id,
                                            device_id=device.id
                                        )
                                        break
                        # else:
                        #     self._log(
                        #         level='DEBUG',
                        #         content=f"跳过设备检查 (API任务不需要): 任务ID={task_id}, 用例ID={tc_rel.id}",
                        #         task_id=task_id
                        #     )
                        
                        # 检查播放设备状态 - 只有E2E测试需要检查播放设备
                        if device_check_passed and task.type == 'e2e':
                            self._log(
                                level='DEBUG',
                                content=f"开始检查播放设备状态",
                                task_id=task_id
                            )
                            from shared.models.models import PlaybackDevice
                            case = local_db_session.get(TestCase, tc_rel.test_case_id)
                            if case:
                                playback_devices = set()
                                # 从配置中获取音频播放设备
                                # audios 存储在 rounds[].audios 中（rounds-as-top-level 格式）
                                config = case.config or {}
                                rounds = config.get('rounds', []) if isinstance(config, dict) else []
                                audios = []
                                for round_item in rounds:
                                    if isinstance(round_item, dict):
                                        round_audios = round_item.get('audios', [])
                                        if isinstance(round_audios, list):
                                            audios.extend(round_audios)
                                self._log(
                                    level='DEBUG',
                                    content=f"E2E用例配置: 音频数量={len(audios)}",
                                    task_id=task_id
                                )
                                for audio in audios:
                                    pb_dev_id = audio.get('playback_device_id')
                                    if pb_dev_id:
                                        playback_devices.add(pb_dev_id)
                                
                                self._log(
                                    level='DEBUG',
                                    content=f"播放设备ID集合: {playback_devices}",
                                    task_id=task_id
                                )
                                
                                # 检查播放设备状态
                                for device_id in playback_devices:
                                    playback_dev = local_db_session.get(PlaybackDevice, device_id)
                                    if playback_dev:
                                        pb_dev_status = playback_dev.status
                                        self._log(
                                            level='DEBUG',
                                            content=f"检查播放设备: 设备ID={device_id}, 设备名称={playback_dev.name}, 状态={pb_dev_status}",
                                            task_id=task_id
                                        )
                                        if pb_dev_status != 'online':
                                            device_check_passed = False
                                            error_message = f"播放设备 {playback_dev.name} 离线，无法执行测试"
                                            self._log(
                                                level='ERROR',
                                                content=error_message,
                                                task_id=task_id
                                            )
                                            break
                                    else:
                                        device_check_passed = False
                                        error_message = f"找不到播放设备，ID: {device_id}"
                                        self._log(
                                            level='ERROR',
                                            content=error_message,
                                            task_id=task_id
                                        )
                                        break
                            else:
                                self._log(
                                    level='DEBUG',
                                    content=f"未找到测试用例: {tc_rel.test_case_id}",
                                    task_id=task_id
                                )
                        
                        # 设备检查失败处理
                        if not device_check_passed:
                            tc_rel.status = 'failed'
                            tc_rel.execution_status = 'failed'  # 更新execution_status为failed，避免死循环
                            tc_rel.completed_at = datetime.now(self.utc_plus_8)
                            tc_rel.duration = 0
                            tc_rel.error_message = error_message
                            local_db_session.commit()
                            
                            # 更新任务统计信息
                            success_count = local_db_session.query(TaskCase).filter(
                                TaskCase.task_id == task_id,
                                TaskCase.status == 'completed'
                            ).count()
                            task.completed_cases = success_count
                            task.failed_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, status='failed').count()
                            local_db_session.commit()
                            
                            # 发送告警和进度更新
                            self._emit_alert(task_id, error_message)
                            self._emit_progress(task)
                            continue

                        # 不预先设置状态，状态由执行引擎内部管理
                        # pending → running → completed/failed
                        # 注意：只有真正进入等待队列的用例才会被统计为"排队中"

                        # 重新获取任务对象以避免 detached instance 问题
                        task = local_db_session.get(Task, task_id)
                        if not task:
                            continue
                        
                        # 根据任务类型执行测试用例
                        if task.type == 'api':
                            try:
                                # 原子占用用例，避免重复提交
                                tc_rel_id = tc_rel.id
                                claimed = local_db_session.query(TaskCase).filter(
                                    TaskCase.id == tc_rel_id,
                                    TaskCase.task_id == task_id,
                                    TaskCase.execution_status == 'pending'
                                ).update(
                                    {
                                        TaskCase.execution_status: 'queued',
                                        TaskCase.status: 'running'
                                    },
                                    synchronize_session=False
                                )
                                if claimed != 1:
                                    local_db_session.rollback()
                                    continue
                                local_db_session.commit()

                                # 微服务化后：直接同步通过 gRPC 调用 api_test_service 执行
                                # api_test_service 内部管理自己的线程池和并发控制
                                self._execute_api_case(task_id, tc_rel_id)
                                continue
                            except Exception as e:
                                # API任务执行异常，标记为失败，不执行E2E流程
                                self._log(
                                    level='ERROR', 
                                    content=f"API任务执行异常: {str(e)}",
                                    task_id=task_id
                                )
                                tc_rel.status = 'failed'
                                tc_rel.execution_status = 'failed'
                                tc_rel.error_message = f"API任务执行异常: {str(e)}"
                                local_db_session.commit()
                                continue
                        else:
                            # E2E任务直接执行
                            # 注意：这里会阻塞直到E2E用例执行完成
                            success = self._execute_e2e_case(task_id, tc_rel.id)
                            
                            # 重新获取tc_rel对象，因为execute_e2e_case方法内部可能已经更新了它
                            tc_rel = local_db_session.get(TaskCase, tc_rel.id)
                            
                            # 更新任务统计信息
                            success_count = local_db_session.query(TaskCase).filter(
                                TaskCase.task_id == task_id,
                                TaskCase.status == 'completed'
                            ).count()
                            task.completed_cases = success_count
                            task.failed_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, status='failed').count()
                        
                        # 发送告警（如果执行失败）
                        if not success:
                            # E2E执行失败时，若用例仍停留在pending（gRPC内部未自行更新状态），
                            # 必须将状态置为failed，避免while循环反复取到同一个用例造成死循环
                            if tc_rel.execution_status not in ('completed', 'failed'):
                                tc_rel.execution_status = 'failed'
                                tc_rel.status = 'failed'
                                # 评估状态也置为completed，避免后续任务级状态判定误认为"评估中"
                                tc_rel.evaluation_status = 'completed'
                                tc_rel.completed_at = datetime.now(self.utc_plus_8)
                                tc_rel.error_message = tc_rel.error_message or 'E2E用例执行失败（gRPC返回失败或异常）'
                            self._emit_alert(task_id, f"用例执行失败: {tc_rel.test_case_id}")

                        local_db_session.commit()
                        self._emit_progress(task)  # 发送进度更新
                    finally:
                        local_db_session.close()

                # 检查是否所有测试用例都已执行完成，提前更新任务状态
                local_db_session = db.session()
                try:
                    task = local_db_session.get(Task, task_id)
                    if task:
                        # 获取所有测试用例
                        all_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id).count()
                        # 获取已处理的测试用例（状态为completed/failed/skipped）
                        all_processed_cases = local_db_session.query(TaskCase).filter(
                            TaskCase.task_id == task_id, 
                            TaskCase.status.in_(['completed', 'failed', 'skipped'])
                        ).count()
                        # 获取运行中的测试用例 (只包括执行中、排队中，不包括评估中/待评估)
                        running_cases = local_db_session.query(TaskCase).filter(
                            TaskCase.task_id == task_id,
                            TaskCase.execution_status.in_(['running', 'queued'])
                        ).count()
                        failed_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, status='failed').count()
                        completed_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, status='completed').count()

                        # 如果所有测试用例都已处理完成，提前更新任务状态
                        if all_processed_cases == all_cases and running_cases == 0:
                            # 检查是否还有用例在评估中
                            evaluating_cases = local_db_session.query(TaskCase).filter(
                                TaskCase.task_id == task_id,
                                TaskCase.evaluation_status.in_(['running', 'calculating', 'queued', 'pending'])
                            ).count()

                            if evaluating_cases > 0:
                                # 还有用例在评估中，设为 evaluating 过渡态
                                task.status = 'evaluating'
                            elif all_cases > 0:
                                if failed_cases > 0:
                                    task.status = 'failed'
                                else:
                                    task.status = 'completed'
                            else:
                                task.status = 'completed'
                            
                            # 提前更新任务状态和统计信息，后续等待循环会继续监控评估完成
                            # 最终状态由评估服务的 _post_evaluate_updates 统一确认

                            if task.status in ['completed', 'failed']:
                                # 更新任务完成时间和实际执行时长
                                task.completed_at = datetime.now(self.utc_plus_8)
                                if task.started_at:
                                    # 确保 started_at 是带时区的 datetime 对象
                                    if task.started_at.tzinfo is None:
                                        task.started_at = task.started_at.replace(tzinfo=self.utc_plus_8)
                                    # 计算实际执行时长（秒）
                                    task.actual_duration = int((task.completed_at - task.started_at).total_seconds())
                            # 更新任务的已完成用例数和失败用例数
                            task.completed_cases = completed_cases
                            task.failed_cases = failed_cases
                            local_db_session.commit()
                            # 发送最终进度更新
                            self._emit_progress(task)
                finally:
                    local_db_session.close()

                # API/E2E任务：等待所有测试用例执行完成
                if task.type in ('api', 'e2e'):
                    # 等待所有测试用例的执行状态都不是running或queued
                    max_wait_time = self.test_case_wait_time  # 从配置文件读取的超时时间
                    wait_start_time = time.time()
                    last_log_time = 0
                    last_counts = None
                    
                    while True:
                        local_db_session = db.session()
                        try:
                            local_db_session.expire_all()
                            
                            task_obj = local_db_session.query(Task).filter_by(id=task_id).first()
                            task_status = task_obj.status if task_obj else 'unknown'
                            
                            from sqlalchemy import func
                            status_counts = local_db_session.query(
                                TaskCase.execution_status,
                                TaskCase.evaluation_status,
                                TaskCase.status,
                                func.count(TaskCase.id)
                            ).filter(TaskCase.task_id == task_id).group_by(
                                TaskCase.execution_status,
                                TaskCase.evaluation_status,
                                TaskCase.status
                            ).all()
                            
                            running_cases = 0
                            queued_cases = 0
                            execution_running_cases = 0
                            execution_success_cases = 0
                            execution_failed_cases = 0
                            evaluation_running_cases = 0
                            evaluation_success_cases = 0
                            evaluation_failed_cases = 0
                            all_processed_cases = 0
                            passed_cases = 0
                            failed_cases = 0
                            
                            for exec_status, eval_status, final_status, count in status_counts:
                                if exec_status in ['running', 'queued']:
                                    running_cases += count
                                if exec_status == 'queued':
                                    queued_cases += count
                                if exec_status == 'running':
                                    execution_running_cases += count
                                if exec_status == 'completed':
                                    execution_success_cases += count
                                if exec_status == 'failed':
                                    execution_failed_cases += count
                                if eval_status in ['running', 'queued']:
                                    evaluation_running_cases += count
                                if eval_status == 'completed':
                                    evaluation_success_cases += count
                                if eval_status == 'failed':
                                    evaluation_failed_cases += count
                                if final_status in ['completed', 'failed', 'skipped']:
                                    all_processed_cases += count
                                if final_status == 'completed':
                                    passed_cases += count
                                if final_status == 'failed':
                                    failed_cases += count
                            
                            current_counts = (
                                running_cases, queued_cases, execution_running_cases, evaluation_running_cases,
                                execution_success_cases, evaluation_success_cases,
                                failed_cases, execution_failed_cases, evaluation_failed_cases,
                                all_processed_cases, task_status
                            )
                            
                            # 添加详细调试日志
                            self._log(
                                level='DEBUG',
                                content=f"任务 {task_id} 统计结果: "
                                       f"all_cases={all_cases}, "
                                       f"running={running_cases}, "
                                       f"all_processed={all_processed_cases}, "
                                       f"evaluation_success={evaluation_success_cases}, "
                                       f"evaluation_failed={evaluation_failed_cases}",
                                task_id=task_id
                            )
                            
                            # 检查任务是否已停止
                            if task_status == 'stopped':
                                # 任务已停止，将所有未完成的测试用例标记为失败
                                uncompleted_cases = local_db_session.query(TaskCase).filter(
                                    TaskCase.task_id == task_id,
                                    TaskCase.execution_status.in_(['running', 'queued'])
                                ).all()
                                for tc in uncompleted_cases:
                                    tc.status = 'failed'
                                    tc.execution_status = 'failed'
                                    tc.completed_at = datetime.now(self.utc_plus_8)
                                    tc.duration = 0
                                    tc.error_message = '任务被停止，用例执行中断'
                                local_db_session.commit()
                                
                                self._log(
                                    level='INFO',
                                    content=f"任务已停止，标记 {len(uncompleted_cases)} 个未完成用例为失败",
                                    task_id=task_id
                                )
                                break
                            
                            # 当所有用例都已处理完成（无论成功失败），退出等待
                            if running_cases == 0 and all_processed_cases == all_cases:
                                # 检查是否还有用例在评估中
                                evaluating_cases = local_db_session.query(TaskCase).filter(
                                    TaskCase.task_id == task_id,
                                    TaskCase.evaluation_status.in_(['running', 'calculating', 'queued', 'pending'])
                                ).count()
                                
                                if evaluating_cases > 0:
                                    # 还有用例在评估中，事件驱动等待
                                    self._log(
                                        level='INFO',
                                        content=f"等待测试用例执行完成 |任务状态：{task_status} 总用例数: {all_cases}, 运行中: {running_cases} (排队中: {queued_cases}, 执行中: {execution_running_cases}, 评估中: {evaluation_running_cases}, 执行成功: {execution_success_cases}), 已完成： {all_cases -running_cases}(评估成功: {evaluation_success_cases}, 失败: {failed_cases} (执行失败: {execution_failed_cases}, 评估失败: {evaluation_failed_cases}))",
                                        task_id=task_id
                                    )
                                    local_db_session.close()
                                    completion_event = self.task_completion_events.get(task_id)
                                    if completion_event:
                                        completion_event.wait(timeout=5)
                                    else:
                                        time.sleep(1)
                                    continue
                                
                                # 注意：不在此处更新任务状态，由评估服务的 _post_evaluate_updates 统一更新
                                # 避免执行引擎和评估服务重复更新导致状态不一致
                                task_obj = local_db_session.query(Task).filter_by(id=task_id).first()
                                if task_obj:
                                    task_obj.completed_cases = passed_cases
                                    task_obj.failed_cases = failed_cases
                                    local_db_session.commit()
                                    # 更新task_status为新状态，确保日志中显示正确状态
                                    task_status = task_obj.status
                                
                                self._log(
                                    level='INFO',
                                    content=f"等待测试用例执行完成 |任务状态：{task_status} 总用例数: {all_cases}, 运行中: {running_cases} (排队中: {queued_cases}, 执行中: {execution_running_cases}, 评估中: {evaluation_running_cases}, 执行成功: {execution_success_cases}), 已完成： {all_cases -running_cases}(评估成功: {evaluation_success_cases}, 失败: {failed_cases} (执行失败: {execution_failed_cases}, 评估失败: {evaluation_failed_cases}))",
                                    task_id=task_id
                                )
                                break
                            elif running_cases == 0:
                                # 特殊情况：所有用例都已完成运行，但可能存在状态未更新的情况
                                # 检查每个用例的状态，确保它们都被正确标记为completed或failed
                                all_task_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id).all()
                                updated = False
                                for tc in all_task_cases:
                                    if tc.status not in ['completed', 'failed', 'skipped']:
                                        # 如果用例状态不是completed或failed，根据执行状态和评估状态推断
                                        if tc.execution_status == 'completed':
                                            # 执行完成，检查评估状态
                                            if tc.evaluation_status == 'completed':
                                                tc.status = 'completed'
                                                tc.completed_at = datetime.now(self.utc_plus_8)
                                            elif tc.evaluation_status == 'failed':
                                                # 评估失败，标记为失败
                                                tc.status = 'failed'
                                                tc.completed_at = datetime.now(self.utc_plus_8)
                                            elif tc.evaluation_status in ['running', 'queued', 'pending']:
                                                # 如果还在评估中或待评估，保持running状态，不标记为失败
                                                tc.status = 'running'
                                                continue
                                            else:
                                                # 其他评估状态（如unknown等），标记为失败
                                                tc.status = 'failed'
                                                tc.completed_at = datetime.now(self.utc_plus_8)
                                        else:
                                            # 执行未完成，标记为失败
                                            tc.status = 'failed'
                                            tc.completed_at = datetime.now(self.utc_plus_8)
                                        updated = True
                                if updated:
                                    local_db_session.commit()
                                    self._log(
                                        level='DEBUG',
                                        content=f"修复用例状态 |任务ID：{task_id} 更新了 {sum(1 for tc in all_task_cases if tc.status not in ['completed', 'failed'])} 个用例的状态",
                                        task_id=task_id
                                    )
                            
                            # 仅在状态变化或超过10秒时记录日志
                            current_time = time.time()
                            if current_counts != last_counts or current_time - last_log_time >= 10:
                                self._log(
                                    level='INFO',
                                    content=f"等待测试用例执行完成 |任务状态：{task_status} 总用例数: {all_cases}, 运行中: {running_cases} (排队中: {queued_cases}, 执行中: {execution_running_cases}, 评估中: {evaluation_running_cases}, 执行成功: {execution_success_cases}), 已完成： {all_cases -running_cases}(评估成功: {evaluation_success_cases}, 失败: {failed_cases} (执行失败: {execution_failed_cases}, 评估失败: {evaluation_failed_cases}))",
                                    task_id=task_id
                                )
                                last_log_time = current_time
                                last_counts = current_counts
                            
                            if time.time() - wait_start_time > max_wait_time:
                                self._log(
                                    level='WARNING',
                                    content=f"等待测试用例执行完成超时，还有 {running_cases} 个用例状态为running或queued",
                                    task_id=task_id
                                )
                                break
                            # 事件驱动等待：评估/执行完成时会被 notify_case_completed 唤醒
                            local_db_session.close()
                            completion_event = self.task_completion_events.get(task_id)
                            if completion_event:
                                completion_event.wait(timeout=5)
                            else:
                                time.sleep(2)
                            continue
                        finally:
                            try:
                                local_db_session.close()
                            except Exception:
                                pass

                # 检查任务状态，如果是暂停状态则保持暂停，不改变状态
                if task.status != 'paused':
                    # 使用本地会话确保独立可靠的会话
                    local_db_session = db.session()
                    try:
                        # 重新获取任务对象，确保它在有效会话中
                        task = local_db_session.get(Task, task_id)
                        if not task:
                            # 任务不存在，直接返回，不继续处理
                            return
                        
                        # 根据停止事件和执行结果更新任务状态
                        if stop_event.is_set():
                            task.status = 'stopped'
                        else:
                            # 检查是否所有测试用例都失败
                            all_cases = local_db_session.query(TaskCase).filter_by(task_id=task.id).count()
                            failed_cases = local_db_session.query(TaskCase).filter_by(task_id=task.id, status='failed').count()
                            all_processed_cases = local_db_session.query(TaskCase).filter(
                                TaskCase.task_id == task.id,
                                TaskCase.status.in_(['completed', 'failed', 'skipped'])
                            ).count()
                            
                            # 成功完成的用例数量
                            successfully_completed_cases = local_db_session.query(TaskCase).filter_by(
                                task_id=task.id, 
                                status='completed'
                            ).count()
                            
                            # 动态更新任务的total_cases字段，确保进度计算准确
                            task.total_cases = all_cases
                            
                            # 确保所有测试用例都已处理完成
                            if all_processed_cases == all_cases:
                                if failed_cases > 0:
                                    task.status = 'failed'
                                else:
                                    task.status = 'completed'
                            else:
                                # 如果还有测试用例未完成，标记为失败
                                task.status = 'failed'
                                # 将所有未处理的测试用例标记为失败，避免任务被重新执行
                                unprocessed_cases = local_db_session.query(TaskCase).filter(
                                    TaskCase.task_id == task.id,
                                    TaskCase.status.notin_(['completed', 'failed', 'skipped'])
                                ).all()
                                for tc in unprocessed_cases:
                                    tc.status = 'failed'
                                    tc.execution_status = 'failed'
                                    tc.completed_at = datetime.now(self.utc_plus_8)
                                    tc.duration = 0
                                    tc.error_message = "任务执行失败，未处理的用例被标记为失败"
                        
                        # 记录任务完成时间和实际执行时长
                        task.completed_at = datetime.now(self.utc_plus_8)
                        if task.started_at:
                            # 确保 started_at 是带时区的 datetime 对象
                            if task.started_at.tzinfo is None:
                                task.started_at = task.started_at.replace(tzinfo=self.utc_plus_8)
                            # 计算实际执行时长（秒）
                            task.actual_duration = int((task.completed_at - task.started_at).total_seconds())
                        
                        # 更新任务的已完成用例数和失败用例数
                        success_count = local_db_session.query(TaskCase).filter(
                            TaskCase.task_id == task_id,
                            TaskCase.status == 'completed'
                        ).count()
                        task.completed_cases = success_count
                        task.failed_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, status='failed').count()
                        
                        local_db_session.commit()
                        # 在关闭会话前发送任务完成进度更新
                        self._emit_progress(task)
                    finally:
                        local_db_session.close()

            except Exception as e:
                # 异常处理
                import traceback
                error_trace = traceback.format_exc()
                
                # 使用本地会话确保独立可靠的会话
                local_db_session = db.session()
                try:
                    # 重新获取任务对象，确保它在有效会话中
                    task = local_db_session.get(Task, task_id)
                    if not task:
                        self._log(
                            level='ERROR', 
                            content=f"任务 {task_id} 不存在，无法更新状态",
                            task_id=task_id
                        )
                        # 任务不存在，直接返回，不继续处理
                        return
                    
                    # 更新所有正在执行的测试用例状态为 failed
                    running_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, execution_status='running').all()
                    for tc_rel in running_cases:
                        tc_rel.status = 'failed'
                        tc_rel.execution_status = 'failed'
                        tc_rel.completed_at = datetime.now(self.utc_plus_8)
                        if tc_rel.started_at:
                            # 确保两个datetime对象都具有相同的时区信息
                            try:
                                if tc_rel.started_at.tzinfo is None:
                                    # 如果started_at不带时区，将其转换为带时区的datetime对象
                                    started_at_with_tz = tc_rel.started_at.replace(tzinfo=self.utc_plus_8)
                                    completed_at_with_tz = datetime.now(self.utc_plus_8)
                                else:
                                    started_at_with_tz = tc_rel.started_at
                                    completed_at_with_tz = datetime.now(self.utc_plus_8)
                                # 计算执行时长
                                tc_rel.duration = int((completed_at_with_tz - started_at_with_tz).total_seconds())
                            except Exception as duration_error:
                                # 如果计算失败，设置时长为0
                                tc_rel.duration = 0
                        tc_rel.error_message = f"任务执行异常: {str(e)}"
                    
                    # 更新任务状态为失败
                    task.status = 'failed'
                    task.completed_at = datetime.now(self.utc_plus_8)
                    if task.started_at:
                        # 确保两个datetime对象都具有相同的时区信息
                        if task.started_at.tzinfo is None:
                            started_at_with_tz = task.started_at.replace(tzinfo=self.utc_plus_8)
                            completed_at_with_tz = task.completed_at
                        elif task.completed_at.tzinfo is None:
                            started_at_with_tz = task.started_at
                            completed_at_with_tz = task.completed_at.replace(tzinfo=self.utc_plus_8)
                        else:
                            started_at_with_tz = task.started_at
                            completed_at_with_tz = task.completed_at
                        # 计算实际执行时长
                        task.actual_duration = int((completed_at_with_tz - started_at_with_tz).total_seconds())
                    
                    # 更新任务统计信息
                    task.completed_cases = local_db_session.query(TaskCase).filter(
                        TaskCase.task_id == task_id,
                        TaskCase.status == 'completed'
                    ).count()
                    task.failed_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, status='failed').count()
                    
                    local_db_session.commit()
                    
                    # 记录详细错误日志
                    self._log(
                        level='ERROR', 
                        content=f"任务 {task_id} 执行失败: {str(e)}\n{error_trace}",
                        task_id=task_id
                    )
                    
                    # 发送告警和进度更新
                    self._emit_alert(task_id, f"任务执行异常: {str(e)}")
                    self._emit_progress(task)
                    
                    # 记录错误日志
                    self._log(
                        level='ERROR', 
                        content=f"执行任务 {task_id} 时发生错误: {str(e)}",
                        task_id=task_id
                    )
                    self._log(
                        level='DEBUG', 
                        content=f"错误详情: {error_trace}",
                        task_id=task_id
                    )
                except Exception as ex:
                    # 记录会话操作异常
                    self._log(
                        level='ERROR', 
                        category='database',
                        content=f"处理任务异常时发生数据库会话错误: {str(ex)}\n{traceback.format_exc()}",
                        task_id=task_id
                    )
                finally:
                    local_db_session.close()
            finally:
                # 重新检查任务状态，决定是否清理资源
                should_cleanup = True
                local_db_session = db.session()
                try:
                    task = local_db_session.get(Task, task_id)
                    # 只有当任务明确处于 'paused' 状态时，才保留资源（以便恢复）
                    # 如果任务被停止 ('stopped')、完成 ('completed') 或失败 ('failed')，必须清理
                    if task and task.status == 'paused' and not stop_event.is_set():
                        should_cleanup = False
                except Exception as e:
                    self._log(level='WARNING', content=f"获取任务状态失败，默认清理资源: {str(e)}", task_id=task_id)
                finally:
                    local_db_session.close()
                
                if should_cleanup:
                    # 清理运行状态
                    with self.queue_lock:
                        if task_id in self.running_tasks:
                            task_type = self.running_tasks[task_id]
                            del self.running_tasks[task_id]
                            
                            if task_type == 'e2e':
                                self.running_e2e = False
                            else:
                                # 释放占用的 API ID
                                local_db_session = db.session()
                                try:
                                    from shared.models.models import TaskAPI
                                    task_apis = local_db_session.query(TaskAPI).filter_by(task_id=task_id).all()
                                    for api_rel in task_apis:
                                        if api_rel.api_id in self.running_apis:
                                            self.running_apis.remove(api_rel.api_id)
                                finally:
                                    local_db_session.close()
                    
                    # 清理线程和标志位
                    self.workers.pop(task_id, None)
                    self.stop_flags.pop(task_id, None)
                    self.pause_flags.pop(task_id, None)
                    self.task_completion_events.pop(task_id, None)
                    # 清理进度缓存，避免内存泄漏
                    self.task_progress_cache.pop(task_id, None)
                    self.last_progress_update.pop(task_id, None)
                    # 清理多轮进度缓存（key 为 tc_rel_id，需查询当前任务的用例 ID）
                    try:
                        cleanup_session = db.session()
                        try:
                            tc_rel_ids = [
                                tc_id for (tc_id,) in
                                cleanup_session.query(TaskCase.id).filter_by(task_id=task_id).all()
                            ]
                            for tc_rel_id in tc_rel_ids:
                                self.round_progress_cache.pop(tc_rel_id, None)
                        finally:
                            cleanup_session.close()
                    except Exception:
                        pass

                    # 检查队列并启动下一个任务
                    self._check_queue()
        finally:
            # 后台线程结束时清理本线程 DB session，防止连接泄漏
            try:
                from shared.models.database import remove_db_session
                remove_db_session()
            except Exception:
                pass

    def _update_endpoint_health(self, endpoint_url, available):
        """更新API入口(Master)的可用性状态
        
        Args:
            endpoint_url: 入口URL
            available: 是否可用
        """
        with self.api_entry_lock:
            if endpoint_url not in self.api_entry_status:
                self.api_entry_status[endpoint_url] = {'available': True, 'fail_count': 0}
            
            old_status = self.api_entry_status[endpoint_url]['available']
            self.api_entry_status[endpoint_url]['available'] = available
            
            if not available:
                self.api_entry_status[endpoint_url]['fail_count'] += 1
            else:
                self.api_entry_status[endpoint_url]['fail_count'] = 0
                
            if old_status != available:
                status_str = "可用" if available else "不可用"
                self._log(level='WARNING' if not available else 'INFO', 
                         content=f"API入口状态变更: {endpoint_url} -> {status_str}")

    def _execute_api_case(self, task_id, tc_rel_id):
        """执行API测试用例

        微服务化迁移后，不再直接调用本地 self.api_executor，
        改为通过 gRPC 调用 api_test_service 执行用例。

        Args:
            task_id: 任务ID
            tc_rel_id: 任务用例关联ID

        Returns:
            执行结果
        """
        try:
            # 通过 gRPC 调用 api_test_service 的 CreateAPITest
            # test_config 携带 case_ids，由 api_test_service 内部驱动 APIExecutor 执行
            import json as _json
            from shared.proto import api_test_service_pb2 as api_pb
            from shared.clients.grpc_clients import get_api_test_service_stub

            stub = get_api_test_service_stub()
            req = api_pb.CreateAPITestRequest(
                task_id=str(task_id),
                test_config=_json.dumps({'case_ids': [str(tc_rel_id)]}),
            )
            resp = stub.CreateAPITest(req)
            if not resp.success:
                raise RuntimeError(f"api_test_service 执行失败: {resp.message}")

            # 更新任务统计信息（基于 api_test_service 已写入数据库的 TaskCase 状态）
            local_db_session = db.session()
            try:
                tc_rel = local_db_session.get(TaskCase, tc_rel_id)
                if tc_rel:
                    # 若 api_test_service 未设置 started_at，在此兜底
                    if not tc_rel.started_at:
                        tc_rel.started_at = datetime.now(self.utc_plus_8)
                        local_db_session.commit()
            finally:
                local_db_session.close()

            return True
        except Exception as e:
            # 捕获所有异常，确保测试用例状态被正确更新
            import traceback
            error_trace = traceback.format_exc()
            error_msg = f"API 执行异常: {str(e)}"

            self._log(
                level='ERROR',
                content=f"API 用例执行失败: {error_msg}\n{error_trace}",
                task_id=task_id
            )

            # 更新测试用例状态为失败
            local_db_session = db.session()
            try:
                tc_rel = local_db_session.get(TaskCase, tc_rel_id)
                if tc_rel:
                    tc_rel.status = 'failed'
                    tc_rel.execution_status = 'failed'
                    # 如果started_at字段为空，设置它
                    if not tc_rel.started_at:
                        tc_rel.started_at = datetime.now(self.utc_plus_8)
                    tc_rel.completed_at = datetime.now(self.utc_plus_8)
                    # 计算测试用例执行时长，确保时区一致
                    started_at = tc_rel.started_at
                    if started_at.tzinfo is None:
                        started_at = started_at.replace(tzinfo=self.utc_plus_8)
                    tc_rel.duration = int((tc_rel.completed_at - started_at).total_seconds())
                    tc_rel.error_message = error_msg
                    local_db_session.commit()

                    # 更新任务统计信息
                    task = local_db_session.get(Task, task_id)
                    if task:
                        task.completed_cases = local_db_session.query(TaskCase).filter(
                            TaskCase.task_id == task_id,
                            TaskCase.status == 'completed'
                        ).count()
                        task.failed_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, status='failed').count()
                        local_db_session.commit()
                        self._emit_progress(task)
            finally:
                local_db_session.close()
            return False

    def _execute_e2e_case(self, task_id, tc_rel_id):
        """执行端到端测试用例

        通过 gRPC 调用 e2e_test_service 的 ExecutionService.StartE2ETask，
        E2E 业务逻辑已下沉到 e2e_test_service 进程。

        Args:
            task_id: 任务ID
            tc_rel_id: 任务用例关联ID

        Returns:
            执行结果（成功返回True，失败返回False）
        """
        return _execute_e2e_case_via_grpc(task_id, tc_rel_id)

# 创建ExecutionEngine实例，供外部调用
execution_engine = ExecutionEngine()


# ──────────────────────────────────────────────────────────────────
#  gRPC 调用封装：把对 e2e_test_service 的直接 import 调用替换为 gRPC stub 调用
# ──────────────────────────────────────────────────────────────────

def _stop_task_audio_via_grpc(task_id):
    """通过 gRPC AudioService 停止任务音频（原 audio_service.stop_task_audio）"""
    import json as _json
    from shared.proto import e2e_service_pb2
    try:
        stub = get_audio_service_stub()
        stub.StopAudio(e2e_service_pb2.StopAudioRequest(task_id=str(task_id)))
    except Exception:
        pass


def _cleanup_devices_via_grpc(task_id):
    """通过 gRPC DeviceService 清理任务设备（原 device_driver_factory.cleanup_devices）"""
    import json as _json
    from shared.proto import e2e_service_pb2
    try:
        stub = get_device_service_stub()
        stub.DestroyDriver(e2e_service_pb2.DestroyDriverRequest(
            task_id=str(task_id),
            driver_id='',
        ))
    except Exception:
        pass


def _unregister_task_events_via_grpc(task_id):
    """通过 gRPC DeviceService 注销任务事件（原 unregister_task_events）"""
    import json as _json
    from shared.proto import e2e_service_pb2
    try:
        stub = get_device_service_stub()
        stub.UnregisterTaskEvents(e2e_service_pb2.UnregisterTaskEventsRequest(
            task_id=str(task_id)
        ))
    except Exception:
        pass


def _get_task_events_via_grpc(task_id):
    """通过 gRPC DeviceService 获取任务事件（原 get_task_events）

    返回 None 表示未注册事件（用于 resume 时判断是否需要重新注册）
    """
    import json as _json
    from shared.proto import e2e_service_pb2
    try:
        stub = get_device_service_stub()
        resp = stub.GetTaskEvents(e2e_service_pb2.GetTaskEventsRequest(
            task_id=str(task_id), max_events=1
        ))
        if not resp.success or not resp.data:
            return None
        return _json.loads(resp.data)
    except Exception:
        return None


def _register_task_events_via_grpc(task_id, stop_event, pause_event):
    """通过 gRPC DeviceService 注册/同步任务事件

    e2e_test_service 端首次调用创建本地 Event，后续调用根据传入的
    stop_event_set/pause_event_set 同步其本地 Event 状态，实现跨进程事件通知。
    """
    import json as _json
    from shared.proto import e2e_service_pb2
    try:
        stub = get_device_service_stub()
        callback_config = {
            'stop_event_set': stop_event.is_set() if stop_event else False,
            'pause_event_set': pause_event.is_set() if pause_event else True,
        }
        stub.RegisterTaskEvents(e2e_service_pb2.RegisterTaskEventsRequest(
            task_id=str(task_id),
            callback_config=_json.dumps(callback_config)
        ))
    except Exception:
        pass


def _execute_e2e_case_via_grpc(task_id, tc_rel_id):
    """通过 gRPC 调用 e2e_test_service 的 ExecutionService.StartE2ETask

    原 `self.e2e_executor.execute_e2e_case(task_id, tc_rel_id)` 已替换为跨服务
    gRPC 调用，E2E 业务逻辑已下沉到 e2e_test_service 进程。
    """
    import json as _json
    from shared.proto import e2e_service_pb2
    try:
        stub = get_e2e_execution_service_stub()
        resp = stub.StartE2ETask(e2e_service_pb2.StartE2ETaskRequest(
            task_id=str(task_id),
            tc_rel_id=str(tc_rel_id),
            e2e_config='',
        ))
        if not resp.success:
            return False
        return True
    except Exception as e:
        import logging as _logging
        _logging.getLogger('task_service').exception(
            f"[_execute_e2e_case_via_grpc] gRPC调用StartE2ETask异常: task_id={task_id}, tc_rel_id={tc_rel_id}, error={e}"
        )
        return False
