# -*- coding: utf-8 -*-
"""忙等退避与评估挂起超时仲裁 Mixin（INT-120）。

执行引擎忙等循环的纵深防御（INT-95 复跑事故：评估挂起 → 主循环每轮刷屏
24.5 万行等待日志、任务永不收敛需手工 UPDATE）：

- 退避：等待执行中/评估中用例时按递增间隔轮询（间隔自 wait_initial_interval
  倍增至 wait_max_interval），事件通知到达或活跃集合变化（有进展）即重置，
  正常路径等待仍以事件驱动为主，无感知劣化；
- 仲裁：无进展达 evaluation_hang_timeout（默认 600s，配置化）且执行侧已无
  活跃用例时，将评估挂起用例按 INT-107 终态口径判 failed
  （evaluation_status=FAILED、status 推导 failed、原因写 error_message），
  逐用例发布 CASE_EVENTS/CASE_FAILED，任务级发布 TASK_EVENTS/TASK_FAILED，
  主循环下一轮即满足退出条件，任务由 _finalize_task_status 自然收敛，
  无需人工干预；
- 上限：无进展达 test_case_wait_time（执行等待上限）时，执行中挂起的用例
  一并判 failed 收敛（口径同 _finalize_task_status 未完成用例兜底与
  _finalize_dispatch_failure 的评估补写），忙等不再无限。
"""
import logging
import time
from datetime import datetime

from shared.models.database import get_db_session
from shared.utils.status_constants import (
    TaskStatus, ExecutionStatus, EvaluationStatus,
    ACTIVE_EXECUTION_STATUSES, ACTIVE_EVALUATION_STATUSES,
)
from shared.utils.status_utils import derive_task_case_status
from task_service.infrastructure.persistence.models import Task, TaskCase

logger = logging.getLogger(__name__)

# 仲裁原因标记（事件 payload 用，供消费方区分终态来源）
ARBITRATION_REASON_EVALUATION_HANG = 'evaluation_hang_timeout'
ARBITRATION_REASON_EXECUTION_HANG = 'execution_hang_timeout'

# 挂起判 failed 的原因话术（写入 task_case_relations.error_message）
EVALUATION_HANG_ERROR_MESSAGE = (
    '评估挂起超时：无进展 {silent_seconds}s 达到阈值 {timeout_seconds}s，'
    '执行引擎超时仲裁判定评估失败'
)
EXECUTION_HANG_ERROR_MESSAGE = (
    '执行挂起超时：无进展 {silent_seconds}s 达到阈值 {timeout_seconds}s，'
    '执行引擎超时仲裁判定执行失败'
)


class EvaluationArbiterMixin:
    """忙等退避与评估挂起超时仲裁

    依赖 ExecutionEngine 实例上的共享属性：
    - evaluation_hang_timeout / wait_initial_interval / wait_max_interval /
      test_case_wait_time（config_manager 加载，秒）
    - task_wait_states = {}（每任务等待状态，__new__ 初始化、清理时弹出）
    - _log / _emit_progress / _emit_alert / _wait_completion_event
    """

    # ---- 等待状态管理 ----

    def _get_wait_state(self, task_id):
        """获取（或惰性创建）任务的等待退避状态"""
        state = self.task_wait_states.get(task_id)
        if state is None:
            state = {
                'interval': self.wait_initial_interval,
                'progress_at': time.time(),
                'last_log_at': 0.0,
                'snapshot': None,
            }
            self.task_wait_states[task_id] = state
        return state

    def _reset_wait_state(self, task_id):
        """清除任务等待状态（任务收尾/恢复派发时）"""
        self.task_wait_states.pop(task_id, None)

    def _reset_wait_interval(self, state):
        """仲裁或进展后重置退避间隔与挂起计时起点"""
        state['interval'] = self.wait_initial_interval
        state['progress_at'] = time.time()

    # ---- 活跃集合快照（进展检测） ----

    def _active_cases_snapshot(self, task_id):
        """当前活跃用例快照：(id, execution_status, evaluation_status) 有序元组。

        任一用例完成或状态推进都会改变快照 → 视为有进展，重置挂起计时；
        快照恒定（含状态字段）超过阈值即判定挂起。
        """
        session = get_db_session()
        try:
            rows = session.query(
                TaskCase.id, TaskCase.execution_status, TaskCase.evaluation_status,
            ).filter(
                TaskCase.task_id == task_id,
                (TaskCase.execution_status.in_(ACTIVE_EXECUTION_STATUSES))
                | (TaskCase.evaluation_status.in_(ACTIVE_EVALUATION_STATUSES)),
            ).all()
            return tuple(sorted(rows))
        finally:
            session.close()

    @staticmethod
    def _count_snapshot_actives(snapshot):
        """从快照统计执行侧/评估侧活跃用例数"""
        exec_active = sum(
            1 for _, exec_st, _ in snapshot if exec_st in ACTIVE_EXECUTION_STATUSES)
        eval_active = sum(
            1 for _, _, eval_st in snapshot if eval_st in ACTIVE_EVALUATION_STATUSES)
        return exec_active, eval_active

    # ---- 主循环等待路径（task_dispatch._handle_no_pending_case 调用） ----

    def _wait_active_cases_with_backoff(self, task_id):
        """主循环等待执行中/评估中用例：退避轮询 + 挂起仲裁（INT-120）。

        替代原先每轮固定日志 + 固定间隔的忙等：日志跟随 wait_max_interval
        节流（挂起场景同 logger 5 分钟 < 20 条），间隔倍增封顶；事件通知
        到达时等待提前返回，正常路径不受影响。
        """
        state = self._get_wait_state(task_id)
        snapshot = self._active_cases_snapshot(task_id)
        if snapshot != state['snapshot']:
            state['snapshot'] = snapshot
            self._reset_wait_interval(state)

        exec_active, eval_active = self._count_snapshot_actives(snapshot)
        silent_seconds = time.time() - state['progress_at']

        if self._arbitrate_on_hang(task_id, exec_active, eval_active, silent_seconds):
            self._reset_wait_interval(state)
            return

        self._log_active_wait(task_id, exec_active, eval_active, silent_seconds, state)
        self._wait_completion_event(task_id, timeout=state['interval'])
        state['interval'] = min(state['interval'] * 2, self.wait_max_interval)

    def _arbitrate_on_hang(self, task_id, exec_active, eval_active, silent_seconds):
        """按无进展时长触发两级仲裁，返回是否发生了仲裁"""
        if exec_active == 0 and eval_active > 0 and silent_seconds >= self.evaluation_hang_timeout:
            # 评估挂起：执行侧已全部完成，评估侧无进展达阈值
            return self._arbitrate_hung_cases(
                task_id, include_execution_stuck=False, silent_seconds=silent_seconds)
        if (exec_active > 0 or eval_active > 0) and silent_seconds >= self.test_case_wait_time:
            # 执行等待上限：执行中/评估中挂起用例一并收敛，忙等有上限
            return self._arbitrate_hung_cases(
                task_id, include_execution_stuck=True, silent_seconds=silent_seconds)
        return False

    def _log_active_wait(self, task_id, exec_active, eval_active, silent_seconds, state):
        """等待日志：跟随 wait_max_interval 节流输出，不再每轮刷屏"""
        now = time.time()
        if now - state['last_log_at'] < self.wait_max_interval:
            return
        state['last_log_at'] = now
        self._log(level='DEBUG', content=(
            f"等待 {exec_active + eval_active} 个执行中/评估中的用例完成 "
            f"(执行中: {exec_active}, 评估中: {eval_active})，"
            f"已 {int(silent_seconds)}s 无进展..."), task_id=task_id)

    # ---- 等待循环辅助（task_finalize._wait_for_cases_completion 每拍调用） ----

    def _register_wait_tick(self, task_id):
        """等待循环每拍：刷新活跃快照并登记进展，返回 (state, snapshot)"""
        state = self._get_wait_state(task_id)
        snapshot = self._active_cases_snapshot(task_id)
        if snapshot != state['snapshot']:
            state['snapshot'] = snapshot
            self._reset_wait_interval(state)
        return state, snapshot

    def _log_throttled(self, state, log_callable, *args, **kwargs):
        """按 wait_max_interval 节流的周期日志"""
        now = time.time()
        if now - state['last_log_at'] < self.wait_max_interval:
            return
        state['last_log_at'] = now
        log_callable(*args, **kwargs)

    # ---- 仲裁核心 ----

    def _arbitrate_hung_cases(self, task_id, include_execution_stuck, silent_seconds):
        """挂起超时仲裁：挂起用例判 failed 终态并发布收敛事件（INT-120）。

        用例终态口径见 _finalize_hung_case；事件口径见 _publish_arbitration_events。
        仲裁后主循环下一轮即满足退出条件（无活跃用例），任务由
        _finalize_task_status 自然收敛为 failed，无需人工 UPDATE。

        Args:
            include_execution_stuck: False 仅仲裁评估挂起（执行已完成）；
                True 连执行中挂起的用例一并收敛（执行等待上限路径）
            silent_seconds: 已无进展时长（秒）

        Returns:
            bool: 是否发生了仲裁（有挂起用例且写库成功）
        """
        session = get_db_session()
        try:
            query = session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                TaskCase.evaluation_status.in_(ACTIVE_EVALUATION_STATUSES)
                | TaskCase.execution_status.in_(ACTIVE_EXECUTION_STATUSES),
            )
            if not include_execution_stuck:
                query = session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    TaskCase.execution_status == ExecutionStatus.COMPLETED,
                    TaskCase.evaluation_status.in_(ACTIVE_EVALUATION_STATUSES),
                )
            hung_cases = query.all()
            if not hung_cases:
                return False

            finalized = [(tc, self._finalize_hung_case(tc, silent_seconds))
                         for tc in hung_cases]
            session.commit()

            self._publish_arbitration_events(task_id, finalized, include_execution_stuck)
            self.refresh_task_counts_atomic(task_id)

            task = session.get(Task, task_id)
            if task is not None:
                # 计数已由 refresh_task_counts_atomic 原子刷新，此处仅取对象发事件
                self._emit_alert(
                    task_id,
                    f"任务 {task_id} 检测到 {len(hung_cases)} 个用例挂起超时"
                    f"（无进展 {int(silent_seconds)}s），已仲裁为 failed 并收敛任务")
                self._emit_progress(task)
            self._log(level='WARNING', content=(
                f"挂起超时仲裁：任务 {task_id} {len(hung_cases)} 个用例无进展 "
                f"{int(silent_seconds)}s 达到阈值，已判 failed 并发布收敛事件"), task_id=task_id)
            return True
        except Exception as e:
            try:
                session.rollback()
            except Exception:
                logger.debug("仲裁回滚失败 task_id=%s", task_id, exc_info=True)
            self._log(level='ERROR', content=f"挂起超时仲裁失败 task_id={task_id}: {e}", task_id=task_id)
            return False
        finally:
            session.close()

    def _finalize_hung_case(self, tc, silent_seconds):
        """单个挂起用例判 failed 终态，返回仲裁原因标记（纯逻辑，便于单测）。

        - 执行挂起：execution_status=FAILED（口径同 _finalize_task_status
          未完成用例兜底）；评估未启动（pending/queued）补写 COMPLETED
          （失败由执行侧承载，同 _finalize_dispatch_failure 口径），评估已
          启动置 FAILED，保证两个过程状态都落终态、主循环可退出；
        - 评估挂起（执行已完成）：按 INT-107 终态口径 evaluation_status=FAILED、
          status 由 derive_task_case_status 推导为 failed、原因写 error_message
          （执行侧 completed_at/duration 不动）。
        """
        if tc.execution_status in ACTIVE_EXECUTION_STATUSES:
            tc.execution_status = ExecutionStatus.FAILED
            tc.completed_at = datetime.now(self.utc_plus_8)
            tc.duration = 0
            if (tc.evaluation_status or EvaluationStatus.PENDING) in (
                    EvaluationStatus.PENDING, EvaluationStatus.QUEUED):
                tc.evaluation_status = EvaluationStatus.COMPLETED
            elif tc.evaluation_status in ACTIVE_EVALUATION_STATUSES:
                tc.evaluation_status = EvaluationStatus.FAILED
            tc.error_message = EXECUTION_HANG_ERROR_MESSAGE.format(
                silent_seconds=int(silent_seconds),
                timeout_seconds=int(self.test_case_wait_time))
            reason = ARBITRATION_REASON_EXECUTION_HANG
        else:
            tc.evaluation_status = EvaluationStatus.FAILED
            tc.error_message = EVALUATION_HANG_ERROR_MESSAGE.format(
                silent_seconds=int(silent_seconds),
                timeout_seconds=int(self.evaluation_hang_timeout))
            reason = ARBITRATION_REASON_EVALUATION_HANG
        tc.status = derive_task_case_status(tc.execution_status, tc.evaluation_status)
        return reason

    def _publish_arbitration_events(self, task_id, finalized, include_execution_stuck):
        """发布仲裁收敛事件：逐用例 CASE_FAILED + 任务级 TASK_FAILED

        payload 对齐 evaluation_service._apply_final_status /
        _update_task_status_and_notify 的既有字段，保持查询侧一致。
        EventBus 在 Redis 不可用时内部降级只打日志，不影响写侧主流程。

        Args:
            finalized: [(TaskCase, reason)] 仲裁后的用例与原因标记
            include_execution_stuck: 是否含执行挂起（决定任务级事件原因标记）
        """
        from shared.utils.redis_pubsub import EventBus, EventChannel, EventType

        event_bus = EventBus()
        for tc, reason in finalized:
            event_bus.publish(
                EventChannel.CASE_EVENTS,
                EventType.CASE_FAILED,
                {
                    'task_id': str(task_id),
                    'test_case_id': str(tc.test_case_id),
                    'evaluation_status': tc.evaluation_status,
                    'case_status': tc.status,
                    'success': False,
                    'reason': reason,
                },
            )
        event_bus.publish(
            EventChannel.TASK_EVENTS,
            EventType.TASK_FAILED,
            {
                'task_id': str(task_id),
                'status': TaskStatus.FAILED,
                'reason': (ARBITRATION_REASON_EXECUTION_HANG if include_execution_stuck
                           else ARBITRATION_REASON_EVALUATION_HANG),
            },
        )
