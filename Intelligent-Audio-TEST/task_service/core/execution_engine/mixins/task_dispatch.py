# -*- coding: utf-8 -*-
"""用例分发 Mixin（从 _task_runner_mixin.py 拆分，P4-4）。

包含主循环中的用例领取、分发与失败处理：
- _get_next_pending_case / _handle_no_pending_case：用例选取与空转处理
- _dispatch_case_by_type / _dispatch_api_case / _dispatch_e2e_case：按任务类型分发
- _claim_case：原子占用用例
- _handle_e2e_failure / _handle_device_check_failed：失败处理
"""
from datetime import datetime

from sqlalchemy.exc import InvalidRequestError

from task_service.infrastructure.persistence.models import Task, TaskCase
from shared.utils.status_utils import (
    derive_task_case_status, task_case_not_removed, REMOVED_CASE_MESSAGE,
)
from shared.utils.status_constants import (
    TaskCaseStatus, ExecutionStatus, EvaluationStatus,
    ACTIVE_EXECUTION_STATUSES, ACTIVE_EVALUATION_STATUSES,
)

import logging

logger = logging.getLogger(__name__)


class TaskDispatchMixin:
    """用例分发：领取 / 原子占用 / 按类型分发 / 失败处理"""

    def _get_next_pending_case(self, task_id, session):
        """获取下一个待执行的测试用例（INT-305：移除留痕行不参与领取）

        INT-1115：config.target_modes 含任一 serial 时按目标级门控（双道语义）
        选行；否则维持现行为（最早 PENDING 先取，全并行零回归）。
        """
        if self._is_serial_task(task_id, session):
            return self._get_next_pending_case_target_gated(task_id, session)
        return session.query(TaskCase).filter(
            TaskCase.task_id == task_id,
            TaskCase.execution_status == ExecutionStatus.PENDING,
            task_case_not_removed(TaskCase),
        ).order_by(TaskCase.created_at.asc()).first()

    # ---- INT-1115 目标级门控（§5.2.4（三）双道语义） ----

    def _target_modes(self, task_id, session):
        """读取任务逐目标执行模式（Task.config.target_modes，缺省空列表）。

        列表保序，元素为 {target_type, target_id, mode}（mode 见 ExecutionMode）。
        历史任务旧 execution_mode/serial_first 字段引擎不再读取（按全并行处理）。
        """
        task = session.get(Task, task_id)
        if task is None or not task.config:
            return []
        return task.config.get('target_modes') or []

    def _is_serial_task(self, task_id, session):
        """是否含串行目标（config.target_modes 任一 mode=serial）。

        兼作主循环 keep-alive 开关：含任一 serial 时沿用串行 keep-alive，
        避免串行门控等待期被提前收敛（_handle_no_pending_case 复用）。
        """
        from shared.models.common_enums import ExecutionMode
        return any(
            item.get('mode') == ExecutionMode.SERIAL.value
            for item in self._target_modes(task_id, session)
        )

    @staticmethod
    def _row_target_key(tc_rel):
        """用例行归属目标键 (target_type, str(target_id))；不可解析返回 None。

        目标行集合 = task_case_relations 中 (device_type, device_id) 命中者：
        device 道 = device_type='physical' 且 device_id=str(target_id)；
        api 道 = device_type ∈ {http_api, websocket_api} 且 device_id=str(target_id)。
        device_id 为空 / 类型未知的行不可解析（视为 parallel 可派发，不受门控）。
        """
        from shared.models.common_enums import DeviceType, TargetType
        device_type = tc_rel.device_type or DeviceType.PHYSICAL.value
        if device_type == DeviceType.PHYSICAL.value:
            target_type = TargetType.DEVICE.value
        elif device_type in (DeviceType.HTTP_API.value, DeviceType.WEBSOCKET_API.value):
            target_type = TargetType.API.value
        else:
            return None
        if not tc_rel.device_id:
            return None
        return (target_type, str(tc_rel.device_id))

    @staticmethod
    def _is_case_row_terminal(tc_rel):
        """用例行是否全终态（exec + eval 均终态，status ∈ FINISHED_CASE_STATUSES）。

        停止/移除留痕行分别由 stop_event 与 task_case_not_removed 兜底，
        这里以推导 status 判定（derive(stopped, stopped)=failed → 终态）。
        """
        from shared.utils.status_constants import FINISHED_CASE_STATUSES
        return (tc_rel.status or '') in FINISHED_CASE_STATUSES

    def _get_next_pending_case_target_gated(self, task_id, session):
        """目标级门控选行（INT-1115 双道语义）。

        双道：设备道（target_type=device）与 API 道（target_type=api）始终并发、
        互不等待。并行目标行不受任何目标门控（任务启动即并发派发，现行为）；
        串行目标 t_k（类型 T）仅当其同类型道内全部前序目标（类型 T 内位置 < k，
        含同类型前序并行目标）的用例行全部到达终态后才派发；两个同类型串行目标
        不重叠（后者在前者全终态后启动）。不可解析目标的行视为 parallel 可派发。
        目标内部门控放行后仍按现有逐用例并发分发（physical 由设备锁天然串行）。
        """
        from shared.models.common_enums import ExecutionMode

        target_modes = self._target_modes(task_id, session)
        rows = session.query(TaskCase).filter(
            TaskCase.task_id == task_id,
            task_case_not_removed(TaskCase),
        ).order_by(TaskCase.created_at.asc()).all()
        if not rows:
            return None
        pending = [r for r in rows if r.execution_status == ExecutionStatus.PENDING]
        if not pending:
            return None

        # 目标位置索引：(target_type, str(target_id)) → 列表位置（串行链顺序）
        position = {}
        for idx, item in enumerate(target_modes):
            key = (item.get('target_type'), str(item.get('target_id')))
            position.setdefault(key, idx)

        gate_ok_cache = {}

        def _gate_ok(key):
            if key in gate_ok_cache:
                return gate_ok_cache[key]
            item_mode = next(
                (item.get('mode') for item in target_modes
                 if (item.get('target_type'), str(item.get('target_id'))) == key),
                ExecutionMode.PARALLEL.value,
            )
            ok = True
            if item_mode == ExecutionMode.SERIAL.value:
                my_pos = position.get(key, len(target_modes))
                my_type = key[0]
                # 同类型道内全部前序目标（含同类型前序并行目标）用例行全部终态；
                # 跨类型目标（另一条道）不影响本目标派发
                for prior_key, p in position.items():
                    if p < my_pos and prior_key[0] == my_type:
                        prior_rows = [r for r in rows if self._row_target_key(r) == prior_key]
                        if prior_rows and not all(self._is_case_row_terminal(r) for r in prior_rows):
                            ok = False
                            break
            gate_ok_cache[key] = ok
            return ok

        for row in pending:
            key = self._row_target_key(row)
            if key is None or key not in position or _gate_ok(key):
                return row
        return None

    def _handle_no_pending_case(self, task_id, task, session, stop_event=None):
        """没有待执行用例时的处理，返回 True 表示需要继续循环"""
        # INT-604：serial 模式逐用例门控——用例两侧全终态前主循环不得退出
        # （否则纯 physical 任务在评估等待期退出后，后续用例的 PENDING 行
        #  会被 _update_post_loop_status 提前收敛，串行编排失效）
        if self._is_serial_task(task_id, session):
            return self._handle_no_pending_case_serial(task_id, session, stop_event=stop_event)

        if not self._task_uses_api_async(task_id, task, session):
            self._log(level='INFO', content=f"任务 {task_id} 所有用例执行完成，退出主循环", task_id=task_id)
            return False

        # API 流程：检查是否有执行中/评估中的用例
        in_progress = self._count_in_progress_cases(task_id, session)
        evaluating = self._count_evaluating_cases(task_id, session)
        if in_progress > 0 or evaluating > 0:
            session.close()
            # INT-120：退避等待 + 评估挂起超时仲裁（日志节流与任务收敛防御）
            # INT-308：stop_event 透传，等待可被停止中断
            self._wait_active_cases_with_backoff(task_id, stop_event=stop_event)
            return True

        self._log(level='INFO', content=f"任务 {task_id} 所有用例执行完成，退出主循环", task_id=task_id)
        return False

    def _handle_no_pending_case_serial(self, task_id, session, stop_event=None):
        """serial 模式：仍有用例行未全终态（含评估中）时继续等待，不退出主循环。"""
        from shared.utils.status_constants import FINISHED_CASE_STATUSES
        remaining = session.query(TaskCase).filter(
            TaskCase.task_id == task_id,
            task_case_not_removed(TaskCase),
            TaskCase.status.notin_(FINISHED_CASE_STATUSES),
        ).count()
        if remaining > 0:
            session.close()
            self._wait_active_cases_with_backoff(task_id, stop_event=stop_event)
            return True
        self._log(level='INFO', content=f"任务 {task_id} 所有用例执行完成，退出主循环", task_id=task_id)
        return False

    def _task_uses_api_async(self, task_id, task, session):
        """任务是否需要 API 异步等待流程

        差异#2 收尾：路由判定完全由用例级 device_type 承载
        （http_api / websocket_api 为异步 API 流程）。
        历史 NULL 行已由 INT-789 回填迁移按关系表补齐
        （api→http_api / device→physical），
        仍为 NULL 的行按物理流程处理（同步执行，不进入异步等待）。
        """
        from shared.models.common_enums import DeviceType
        api_types = (DeviceType.HTTP_API.value, DeviceType.WEBSOCKET_API.value)
        api_case = session.query(TaskCase).filter(
            TaskCase.task_id == task_id,
            TaskCase.device_type.in_(api_types),
        ).first()
        return api_case is not None

    def _count_in_progress_cases(self, task_id, session):
        """统计执行中/排队中的用例数"""
        return session.query(TaskCase).filter(
            TaskCase.task_id == task_id,
            TaskCase.execution_status.in_(ACTIVE_EXECUTION_STATUSES)
        ).count()

    def _count_evaluating_cases(self, task_id, session):
        """统计评估中的用例数"""
        return session.query(TaskCase).filter(
            TaskCase.task_id == task_id,
            TaskCase.evaluation_status.in_(ACTIVE_EVALUATION_STATUSES)
        ).count()

    def _handle_device_check_failed(self, task_id, task, tc_rel, error_msg, session):
        """设备检查失败时的用例标记和统计更新

        终态收敛复用 _finalize_dispatch_failure 口径：evaluation_status 停留
        pending 会被主循环计入活跃评估集合，混合 device_type 任务死等不收敛。
        """
        self._finalize_dispatch_failure(tc_rel)
        tc_rel.completed_at = datetime.now(self.utc_plus_8)
        tc_rel.duration = 0
        tc_rel.error_message = error_msg
        session.commit()

        # 用例级统计（一个用例 × 多 API 只计一次），口径集中在 task_case_stats
        self.refresh_task_counts_atomic(task_id)
        session.refresh(task)
        self._emit_alert(task_id, error_msg)
        self._emit_progress(task)

    def _dispatch_case_by_type(self, task_id, task, tc_rel, session):
        """根据用例级 device_type 分发用例执行

        差异#2 收尾：路由判定完全由 task_case_relations.device_type 承载
        （task.type 已废弃）。历史 NULL 行已由 INT-789 回填迁移补齐，
        仍为 NULL 的行兜底按物理设备流程处理。
        """
        from shared.models.common_enums import DeviceType
        device_type = tc_rel.device_type or DeviceType.PHYSICAL.value
        if device_type in (DeviceType.HTTP_API.value, DeviceType.WEBSOCKET_API.value):
            self._dispatch_api_case(task_id, tc_rel, session, device_type)
        else:
            self._dispatch_e2e_case(task_id, task, tc_rel, session)

    def _dispatch_api_case(self, task_id, tc_rel, session, device_type=None):
        """API 任务用例执行

        会话亲和（架构设计 §5.2 认领即绑定）：Realtime（websocket_api）用例
        派发前经 RealtimeSessionRegistry.route_or_bind 解析 task → 实例绑定
        （无健康绑定则选最闲在册实例写入），StartAPITest 直连该实例派发，
        保证同任务的 Realtime 会话粘同实例；解析降级时回退默认负载均衡通道。

        INT-71：device_type/device_id 路由决策随 StartAPITestRequest 下发，
        api_test_service 按其路由 executor。
        """
        from shared.models.common_enums import DeviceType
        try:
            claimed = self._claim_case(task_id, tc_rel.id, session)
            if claimed != 1:
                session.rollback()
                return
            session.commit()
            dispatch_target = None
            if device_type == DeviceType.WEBSOCKET_API.value:
                dispatch_target = self._route_realtime_dispatch(task_id)
            self._execute_api_case(
                task_id, tc_rel.id, dispatch_target=dispatch_target,
                device_type=device_type, device_id=tc_rel.device_id)
        except Exception as e:
            self._log(level='ERROR', content=f"API任务执行异常: {str(e)}", task_id=task_id)
            self._finalize_dispatch_failure(tc_rel)
            tc_rel.error_message = f"API任务执行异常: {str(e)}"
            session.commit()

    def _route_realtime_dispatch(self, task_id):
        """Realtime 用例的亲和路由目标（认领即绑定）；降级/不可用时返回 None"""
        try:
            from shared.utils.realtime_session_registry import RealtimeSessionRegistry
            target = RealtimeSessionRegistry().route_or_bind(task_id)
            if target is not None:
                self._log(level='INFO',
                          content=f"Realtime 会话亲和路由: task={task_id} -> "
                                  f"{target['instance_id']} (bound={target.get('bound')})",
                          task_id=task_id)
            return target
        except Exception as e:
            self._log(level='WARNING',
                      content=f"Realtime 会话亲和路由失败，回退默认通道: {e}",
                      task_id=task_id)
            return None

    def _dispatch_e2e_case(self, task_id, task, tc_rel, session):
        """E2E 任务用例执行

        physical 设备互斥（INT-80）：派发前经 DistributedLock
        （lock:task:physical:{device_id}，RedisKeyPrefix.TASK_PHYSICAL_LOCK）
        抢占物理设备，同一设备同一时刻仅允许一个用例执行；
        抢占失败按分发失败收敛（设备被其他任务/用例占用）。
        Redis 不可用时 DistributedLock 降级放行，不阻塞执行链。
        """
        claimed = self._claim_case(task_id, tc_rel.id, session)
        if claimed != 1:
            session.rollback()
            return
        session.commit()

        device_lock = self._acquire_physical_device_lock(task_id, tc_rel)
        if device_lock is None:
            self._handle_physical_lock_busy(task_id, tc_rel)
            return

        # 先取设备号：执行期间用例行可能被删（INT-305），finally 日志不再触实例属性
        e2e_device_id = tc_rel.device_id
        try:
            success = self._execute_e2e_case(task_id, tc_rel.id)
            # INT-308 复验打回：同步执行期间执行器可经 gRPC 写入 TaskCase 终态
            # （停止分支 execution_status=stopped / error_message='任务被手动停止'），
            # 而 tc_rel 仍持有派发/抢锁时的 identity map 快照——session.get 命中
            # 未过期陈旧对象，失败收敛会把停止终态覆盖回兜底失败文案。
            # 强制 refresh 重读，收敛一律以落库值为准。
            # 先取主键：refresh 失败后实例过期，再访问属性会二次触发刷新抛错
            tc_rel_id = tc_rel.id
            try:
                session.refresh(tc_rel)
            except InvalidRequestError:
                # refresh 对已删行抛 InvalidRequestError（ObjectDeletedError 子类）——
                # 行确认不存在则跳过收敛（无终态可写），其余 refresh 异常照常上抛不吞；
                # 探测须走 query 且用已捕获的主键值（不可再触 tc_rel 属性）
                row_exists = session.query(TaskCase.id).filter(
                    TaskCase.id == tc_rel_id).first() is not None
                if row_exists:
                    raise
                self._log(level='INFO',
                          content=f"用例 {tc_rel_id} 执行期间已被删除，跳过终态收敛",
                          task_id=task_id)
                return

            # 用例级统计（一个用例 × 多 API 只计一次）
            self.refresh_task_counts_atomic(task_id)
            session.refresh(task)

            if not success:
                self._handle_e2e_failure(task_id, tc_rel)
        finally:
            try:
                device_lock.release()
            except Exception:
                self._log(level='WARNING',
                          content=f"释放物理设备互斥锁失败 (device_id={e2e_device_id})",
                          task_id=task_id)

    def _acquire_physical_device_lock(self, task_id, tc_rel):
        """抢占物理设备互斥锁；无 device_id 返回无锁句柄，被占用返回 None。

        TTL 覆盖单用例同步执行上限（StartE2ETask 同步执行整个 E2E 用例），
        持有者崩溃后由 TTL 兜底自愈。
        """
        from shared.models.common_enums import RedisKeyPrefix
        from shared.utils.distributed_coordinator import DistributedLock
        from shared.infrastructure.config import BaseConfig

        device_id = tc_rel.device_id
        if not device_id:
            # 用例未绑定具体物理设备：无可锁资源，直接放行（保持原行为）
            class _NoOpLock:
                def release(self):
                    pass
            return _NoOpLock()

        ttl = int(getattr(BaseConfig, 'GRPC_E2E_SYNC_TIMEOUT_SECONDS', 600)) + 60
        lock = DistributedLock(
            f'{RedisKeyPrefix.TASK_PHYSICAL_LOCK.value}:{device_id}',
            ttl=ttl, retry_timeout=10,
        )
        if not lock.acquire(blocking=True):
            return None
        return lock

    def _handle_physical_lock_busy(self, task_id, tc_rel):
        """物理设备被占用：用例置失败收敛，避免主循环死等活跃用例

        UC-1001 5b：等锁期间用例保持 QUEUED（仅排队状态，无执行事件；
        RUNNING 由 e2e_test_service 拿锁开始执行后才置位，无"假运行中"）；
        抢占失败收敛为失败终态时同步任务统计并发布告警/进度事件，
        保证"排队→失败"收敛对前端可观测（对齐 _handle_device_check_failed）。

        终态收敛复用 _finalize_dispatch_failure：evaluation_status 停留 pending
        会被 _count_evaluating_cases 计入活跃评估集合，混合 device_type 任务
        主循环死等不收敛；任务统计走 refresh_task_counts_atomic（progress.py
        约定：统计更新一律原子刷新，不直接赋值）。
        """
        error_msg = f'物理设备 {tc_rel.device_id} 正被其他任务/用例占用'
        self._log(level='WARNING',
                  content=f"物理设备 {tc_rel.device_id} 正被其他任务/用例占用，"
                          f"用例 {tc_rel.id} 派发失败",
                  task_id=task_id, device_id=tc_rel.device_id)
        from task_service.infrastructure.persistence.models import Task, TaskCase
        from shared.models.database import create_db_session
        from datetime import datetime as _dt
        session = create_db_session()
        try:
            row = session.get(TaskCase, tc_rel.id)
            if row and row.execution_status in (ExecutionStatus.QUEUED, ExecutionStatus.RUNNING):
                now = _dt.now()
                if not row.started_at:
                    row.started_at = now
                row.completed_at = now
                row.duration = 0
                self._finalize_dispatch_failure(row)
                row.error_message = error_msg
                session.commit()

                self.refresh_task_counts_atomic(task_id)
                task = session.get(Task, task_id)
                if task is not None:
                    self._emit_alert(task_id, error_msg)
                    self._emit_progress(task)
        finally:
            session.close()

    def _claim_case(self, task_id, tc_rel_id, session):
        """原子占用用例，避免重复提交"""
        return session.query(TaskCase).filter(
            TaskCase.id == tc_rel_id,
            TaskCase.task_id == task_id,
            TaskCase.execution_status == ExecutionStatus.PENDING
        ).update({
            TaskCase.execution_status: ExecutionStatus.QUEUED,
            TaskCase.status: derive_task_case_status(ExecutionStatus.QUEUED, EvaluationStatus.PENDING)
        }, synchronize_session=False)

    def _finalize_dispatch_failure(self, tc_rel):
        """分发侧失败兜底：执行置终态失败；评估尚未启动时同步补写评估终态。

        evaluation_status 停留 pending/queued 会被主循环计入评估中活跃集合
        （ACTIVE_EVALUATION_STATUSES 含 PENDING），导致 _handle_no_pending_case 死等、任务永不收敛；
        评估置 completed 与 api_test_service 侧失败逃生门语义一致（失败由 execution_status 承载）。
        """
        if (tc_rel.evaluation_status or EvaluationStatus.PENDING) in (EvaluationStatus.PENDING, EvaluationStatus.QUEUED):
            tc_rel.evaluation_status = EvaluationStatus.COMPLETED
        tc_rel.execution_status = ExecutionStatus.FAILED
        tc_rel.status = derive_task_case_status(tc_rel.execution_status, tc_rel.evaluation_status or EvaluationStatus.PENDING)

    def _handle_e2e_failure(self, task_id, tc_rel):
        """E2E 执行失败收敛（调用前须 session.refresh 重读落库值，见 _dispatch_e2e_case）。

        INT-308 复验打回：执行器经 gRPC 写入的终态不得被兜底覆盖——
        - 停止分支已写 execution_status=stopped / error_message='任务被手动停止'
          （取证点③契约），防护条件排除 STOPPED，用户停止不被改写为执行失败；
        - INT-305 移除留痕行（error_message='用例已被移除'）不收敛，保留移除语义。
        告警仅对执行失败终态发布（停止/移除/完成路径各有自己的事件）。
        """
        is_removed = (tc_rel.error_message or '') == REMOVED_CASE_MESSAGE
        if not is_removed and tc_rel.execution_status not in (
                ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.STOPPED):
            tc_rel.execution_status = ExecutionStatus.FAILED
            tc_rel.evaluation_status = EvaluationStatus.COMPLETED
            tc_rel.status = derive_task_case_status(tc_rel.execution_status, tc_rel.evaluation_status)
            tc_rel.completed_at = datetime.now(self.utc_plus_8)
            tc_rel.error_message = tc_rel.error_message or 'E2E用例执行失败（gRPC返回失败或异常）'
        if tc_rel.execution_status == ExecutionStatus.FAILED:
            self._emit_alert(task_id, f"用例执行失败: {tc_rel.test_case_id}")
