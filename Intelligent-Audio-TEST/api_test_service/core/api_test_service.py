"""
API Test Service - 服务接口层
接收 Task Service 的 gRPC 请求，执行 API 测试

迁移后由 stub 改为真正驱动 APIExecutor。
"""
import contextvars
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from shared.utils.dto_utils import dto_to_dict
from shared.utils.status_constants import ExecutionStatus
from api_test_service.infrastructure.acl import TaskDataAclRepositoryImpl

_logger = logging.getLogger(__name__)

# 跨服务出站 gRPC 经 ACL 仓储（返回 DTO），不返回 raw dict
_task_data_acl = TaskDataAclRepositoryImpl()


class _APIEngineAdapter:
    """api_test_service 内部的执行引擎适配器

    提供 APIExecutor / BaseExecutor 所需的最小接口集：
    - stop_flags / pause_flags（任务控制）
    - api_entry_lock / api_entry_status（负载均衡）
    - _emit_progress（进度推送，本服务内为空实现，进度由 task_service 端管理）
    - notify_case_completed（空实现）
    - update_case_round_progress（内存缓存）
    """
    def __init__(self):
        self.stop_flags = {}
        self.pause_flags = {}
        self.api_entry_status = {}
        self.api_entry_lock = threading.Lock()
        self.round_progress_cache = {}

    def _emit_progress(self, task_id, force=False):
        """进度推送占位：api_test_service 不直接推送前端，进度由 task_service 通过 gRPC 查询获取"""
        pass

    def notify_case_completed(self, task_id):
        """用例完成通知占位"""
        pass

    def update_case_round_progress(self, task_id, tc_rel_id, current_round, total_rounds):
        """更新多轮进度缓存"""
        self.round_progress_cache[tc_rel_id] = {
            'current': current_round,
            'total': total_rounds
        }


class APITestService:
    """API 测试服务"""
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
            app: 保留参数以兼容旧调用，内部不再使用（DB session 由 scoped_session 提供）
        """
        self._engine = _APIEngineAdapter()
        self._executor = None
        self._executor_lock = threading.Lock()
        self._running_tasks = set()
        self._running_tasks_lock = threading.Lock()
        # 会话亲和注册表（双副本同会话粘同实例，§5.2）：TTL 与执行器同源配置
        from shared.utils.config_manager import config_manager
        from shared.utils.realtime_session_registry import RealtimeSessionRegistry
        self._session_registry = RealtimeSessionRegistry(
            bind_ttl_seconds=int(config_manager.get_value(
                'realtime_session', 'bind_ttl_seconds', 3600)))
        # 固定线程池：所有 API 任务共享，避免频繁创建/销毁
        # 1U4G 服务器建议 8 个线程（详见线程预算分析）
        self._task_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix='api_test_')
        self._initialized = True

    @property
    def api_executor(self):
        """懒加载 APIExecutor"""
        if self._executor is None:
            with self._executor_lock:
                if self._executor is None:
                    from api_test_service.core.api_executor import APIExecutor
                    self._executor = APIExecutor(self._engine)
        return self._executor

    def start_task(self, task_id, case_ids, api_ids):
        """启动 API 测试任务

        Args:
            task_id: 任务ID
            case_ids: 待执行的 TaskCase 关联ID列表
            api_ids: 任务关联的 API ID 列表

        Returns:
            dict: 启动结果
        """
        if not self._initialized:
            return {'success': False, 'task_id': task_id, 'message': '服务未初始化'}

        # 会话亲和门禁（§5.2）：绑定在其它存活实例的会话不在本地执行，
        # 转发到持有实例；Redis 降级/本地绑定/持有实例不可达时本地执行
        forwarded = self._affinity_forward_start(task_id, case_ids, api_ids)
        if forwarded is not None:
            return forwarded

        # 标记任务运行中
        with self._running_tasks_lock:
            if task_id in self._running_tasks:
                return {'success': False, 'task_id': task_id, 'message': '任务已在运行中'}
            self._running_tasks.add(task_id)

        executor = self.api_executor

        # 引用计数：全部用例完成后才将任务标记为 idle，
        # 避免首个用例完成即置 idle 导致状态误报与任务重复启动
        pending_count = [0]
        pending_lock = threading.Lock()

        def _run_case(tc_rel_id):
            try:
                executor.execute_api_case(task_id, tc_rel_id)
            except Exception as e:
                import traceback
                self._log(task_id, 'ERROR', f"API 用例 {tc_rel_id} 执行异常: {str(e)}\n{traceback.format_exc()}")
            finally:
                with pending_lock:
                    pending_count[0] -= 1
                    is_last = pending_count[0] <= 0
                if is_last:
                    self._mark_task_idle(task_id)

        try:
            # 查询待执行的 TaskCase ID（如果调用方未提供 case_ids，
            # 则通过 gRPC 从 task_service 按 pending/queued 状态读取）
            target_case_ids = list(case_ids) if case_ids else []
            if not target_case_ids:
                try:
                    tcs = [dto_to_dict(d) for d in _task_data_acl.get_task_case_by_ids(task_id)]
                    target_case_ids = [
                        tc.get('id') for tc in tcs
                        if tc.get('execution_status') in [ExecutionStatus.PENDING, ExecutionStatus.QUEUED]
                    ]
                except Exception as e:
                    self._log(task_id, 'WARNING', f"查询待执行 TaskCase 失败: {e}")

            if not target_case_ids:
                self._mark_task_idle(task_id)
                return {'success': True, 'task_id': task_id, 'message': '无可执行的用例'}

            # 提交到固定线程池，全部用例完成后在 _run_case 的 finally 中自动清理。
            # 每用例独立 copy_context：把 servicer 绑定的 worker_instance_id
            # 传播进池线程（UC-1001 事件 payload 贯通），各 Context 互不共享写。
            pending_count[0] = len(target_case_ids)
            for tc_rel_id in target_case_ids:
                case_ctx = contextvars.copy_context()
                self._task_pool.submit(case_ctx.run, _run_case, tc_rel_id)

            return {
                'success': True,
                'task_id': task_id,
                'message': 'API test task started',
                'case_count': len(target_case_ids),
            }
        except Exception as e:
            self._mark_task_idle(task_id)
            return {'success': False, 'task_id': task_id, 'message': f'启动失败: {str(e)}'}

    def _affinity_forward_start(self, task_id, case_ids, api_ids):
        """启动请求的会话亲和门禁（§5.2 亲和路由）

        Returns:
            dict = 已转发，持有实例响应；None = 本地执行
            （resolve 降级/绑定本实例；绑定实例路由信息缺失或转发不可达时
            降级本地，由 resolve 的失联重路由语义收敛绑定）
        """
        try:
            affinity = self._session_registry.resolve(task_id)
        except Exception as e:
            self._log(task_id, 'WARNING', f"会话亲和门禁解析异常，本地执行: {e}")
            return None
        if affinity.get('degraded') or affinity.get('is_local') or not affinity.get('instance_id'):
            return None
        from api_test_service.infrastructure.peer_rpc import forward_create_api_test
        result = forward_create_api_test(task_id, case_ids, api_ids,
                                         affinity['instance_id'])
        if result is not None:
            self._log(task_id, 'INFO',
                      f"会话亲和转发启动请求到持有实例 {affinity['instance_id']}")
        return result

    def stop_task(self, task_id):
        """停止 API 测试任务"""
        with self._running_tasks_lock:
            self._running_tasks.discard(task_id)

        # 设置 stop_event，让执行器内部 _handle_control 检测到停止信号
        stop_event = self._engine.stop_flags.get(task_id)
        if stop_event is None:
            stop_event = threading.Event()
            self._engine.stop_flags[task_id] = stop_event
        stop_event.set()

        return {'success': True, 'task_id': task_id, 'message': 'API test task stopped'}

    def get_task_status(self, task_id):
        """获取任务状态"""
        with self._running_tasks_lock:
            running = task_id in self._running_tasks

        # round_progress_cache 的 key 是 tc_rel_id（TaskCase.id），与写入侧 update_case_round_progress 一致。
        # 任务级查询无法仅凭 task_id 精确匹配：单用例任务时命中该条目，多用例任务返回 None（避免误报）。
        round_progress = None
        rpc = self._engine.round_progress_cache
        if rpc:
            if len(rpc) == 1:
                round_progress = next(iter(rpc.values()))
            elif task_id in rpc:
                round_progress = rpc[task_id]

        return {
            'task_id': task_id,
            'status': 'running' if running else 'idle',
            'round_progress': round_progress,
        }

    def _mark_task_idle(self, task_id):
        with self._running_tasks_lock:
            self._running_tasks.discard(task_id)

    def _log(self, task_id, level, content):
        """简易日志"""
        try:
            from shared.utils.log_handler import log_and_emit
            log_and_emit(level=level, module='APITestService', content=content,
                         source='backend', task_id=task_id)
        except Exception as _e:
            _logger.debug("log_and_emit failed: %s", _e)


api_test_service = APITestService()
