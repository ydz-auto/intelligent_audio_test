# -*- coding: utf-8 -*-
"""用例分发 Mixin（从 _task_runner_mixin.py 拆分，P4-4）。

包含主循环中的用例领取、分发与失败处理：
- _get_next_pending_case / _handle_no_pending_case：用例选取与空转处理
- _dispatch_case_by_type / _dispatch_api_case / _dispatch_e2e_case：按任务类型分发
- _claim_case：原子占用用例
- _handle_e2e_failure / _handle_device_check_failed：失败处理
"""
from datetime import datetime

from task_service.infrastructure.persistence.models import TaskCase
from shared.utils.status_utils import derive_task_case_status
from shared.utils.status_constants import (
    TaskCaseStatus, ExecutionStatus, EvaluationStatus,
    ACTIVE_EXECUTION_STATUSES, ACTIVE_EVALUATION_STATUSES,
)

import logging

logger = logging.getLogger(__name__)


class TaskDispatchMixin:
    """用例分发：领取 / 原子占用 / 按类型分发 / 失败处理"""

    def _get_next_pending_case(self, task_id, session):
        """获取下一个待执行的测试用例"""
        return session.query(TaskCase).filter_by(
            task_id=task_id, execution_status=ExecutionStatus.PENDING
        ).order_by(TaskCase.created_at.asc()).first()

    def _handle_no_pending_case(self, task_id, task, session):
        """没有待执行用例时的处理，返回 True 表示需要继续循环"""
        if not self._task_uses_api_async(task_id, task, session):
            self._log(level='INFO', content=f"任务 {task_id} 所有用例执行完成，退出主循环", task_id=task_id)
            return False

        # API 流程：检查是否有执行中/评估中的用例
        in_progress = self._count_in_progress_cases(task_id, session)
        evaluating = self._count_evaluating_cases(task_id, session)
        if in_progress > 0 or evaluating > 0:
            total = in_progress + evaluating
            self._log(level='DEBUG', content=f"等待 {total} 个执行中/评估中的用例完成 (执行中: {in_progress}, 评估中: {evaluating})...", task_id=task_id)
            session.close()
            self._wait_completion_event(task_id)
            return True

        self._log(level='INFO', content=f"任务 {task_id} 所有用例执行完成，退出主循环", task_id=task_id)
        return False

    def _task_uses_api_async(self, task_id, task, session):
        """任务是否需要 API 异步等待流程

        差异#2 收尾：路由判定完全由用例级 device_type 承载
        （http_api / websocket_api 为异步 API 流程）。
        历史 NULL 行已由 202610 迁移回填（api→http_api / e2e→physical），
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
        """设备检查失败时的用例标记和统计更新"""
        tc_rel.execution_status = ExecutionStatus.FAILED
        tc_rel.status = derive_task_case_status(tc_rel.execution_status, tc_rel.evaluation_status or EvaluationStatus.PENDING)
        tc_rel.completed_at = datetime.now(self.utc_plus_8)
        tc_rel.duration = 0
        tc_rel.error_message = error_msg
        session.commit()

        task.completed_cases = self._count_cases_by_status(task_id, session, TaskCaseStatus.COMPLETED)
        task.failed_cases = self._count_cases_by_status(task_id, session, TaskCaseStatus.FAILED, use_filter_by=True)
        session.commit()
        self._emit_alert(task_id, error_msg)
        self._emit_progress(task)

    def _count_cases_by_status(self, task_id, session, status, use_filter_by=False):
        """按状态统计用例数"""
        if use_filter_by:
            return session.query(TaskCase).filter_by(task_id=task_id, status=status).count()
        return session.query(TaskCase).filter(
            TaskCase.task_id == task_id, TaskCase.status == status
        ).count()

    def _dispatch_case_by_type(self, task_id, task, tc_rel, session):
        """根据用例级 device_type 分发用例执行

        差异#2 收尾：路由判定完全由 task_case_relations.device_type 承载
        （task.type 已废弃）。历史 NULL 行已由 202610 迁移回填，
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

        try:
            success = self._execute_e2e_case(task_id, tc_rel.id)
            tc_rel = session.get(TaskCase, tc_rel.id)

            task.completed_cases = self._count_cases_by_status(task_id, session, TaskCaseStatus.COMPLETED)
            task.failed_cases = self._count_cases_by_status(task_id, session, TaskCaseStatus.FAILED, use_filter_by=True)

            if not success:
                self._handle_e2e_failure(task_id, tc_rel)
        finally:
            try:
                device_lock.release()
            except Exception:
                self._log(level='WARNING',
                          content=f"释放物理设备互斥锁失败 (device_id={tc_rel.device_id})",
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
        """
        error_msg = f'物理设备 {tc_rel.device_id} 正被其他任务/用例占用'
        self._log(level='WARNING',
                  content=f"物理设备 {tc_rel.device_id} 正被其他任务/用例占用，"
                          f"用例 {tc_rel.id} 派发失败",
                  task_id=task_id, device_id=tc_rel.device_id)
        from task_service.infrastructure.persistence.models import Task, TaskCase
        from shared.utils.status_utils import derive_task_case_status
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
                row.execution_status = ExecutionStatus.FAILED
                row.status = derive_task_case_status(ExecutionStatus.FAILED, row.evaluation_status)
                row.error_message = error_msg
                session.commit()

                task = session.get(Task, task_id)
                if task is not None:
                    task.completed_cases = self._count_cases_by_status(task_id, session, TaskCaseStatus.COMPLETED)
                    task.failed_cases = self._count_cases_by_status(task_id, session, TaskCaseStatus.FAILED, use_filter_by=True)
                    session.commit()
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
        """E2E 执行失败处理"""
        if tc_rel.execution_status not in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED):
            tc_rel.execution_status = ExecutionStatus.FAILED
            tc_rel.evaluation_status = EvaluationStatus.COMPLETED
            tc_rel.status = derive_task_case_status(tc_rel.execution_status, tc_rel.evaluation_status)
            tc_rel.completed_at = datetime.now(self.utc_plus_8)
            tc_rel.error_message = tc_rel.error_message or 'E2E用例执行失败（gRPC返回失败或异常）'
        self._emit_alert(task_id, f"用例执行失败: {tc_rel.test_case_id}")
