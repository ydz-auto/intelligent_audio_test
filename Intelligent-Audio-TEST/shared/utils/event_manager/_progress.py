# -*- coding: utf-8 -*-
"""任务进度 Socket 推送（task_progress 事件）

职责拆分：
- emit_progress：节流/缓存编排（唯一入口）
- _build_progress_from_grpc / _build_progress_from_po：两条数据源路径构造 TaskProgressPayload
- _finalize_and_emit：时间预估、变更检测、缓存与发射

payload 契约见 shared/schemas/socket_payloads.py（snake_case，
前端由 infrastructure/adapters/taskProgressAdapter.ts 统一转 camelCase）。
"""
import re
import time
import logging
from datetime import datetime
from typing import Optional, Tuple

from shared.models.database import get_db_session
from shared.models.common_enums import TestType
from shared.schemas.socket_payloads import (
    ProgressApiResource,
    ProgressCaseItem,
    ProgressCurrentCase,
    ProgressLogItem,
    RoundProgress,
    TaskProgressPayload,
)
from shared.utils.event_manager._common import get_socketio
from shared.utils.status_constants import (
    ACTIVE_EXECUTION_STATUSES,
    ExecutionStatus,
    EvaluationStatus,
    TaskCaseStatus,
    TaskStatus,
)
from shared.utils.time_utils import UTC8

logger = logging.getLogger(__name__)

# 缓存策略：使用 shared.utils.task_data_cache 的 TTL 缓存减少 DB 往返。
# gRPC GetTaskProgress 现已返回完整进度数据（test_cases 列表/计数/api_resource_status），
# 优先走 gRPC 缓存；PO 直连仅用于 gRPC 不可用时的回退，以及内存态数据
#（execution_engine.round_progress_cache / load_balancer.url_status）。
from shared.utils.task_data_cache import get_task_progress_via_grpc

# 当前执行中用例的 step 默认值：按任务类型区分
STEP_PLAYING = 'playing'
STEP_EVALUATING = 'evaluating'

# 预计总时长防闪烁阈值：变化小于 10% 沿用缓存值
EXPECTED_TOTAL_SMOOTHING_RATIO = 0.1

# 时间预估兜底值（秒）
DEFAULT_EXPECTED_TOTAL_SECONDS = 60


def _extract_task_id(task) -> str:
    """从各类任务表示（id/Task PO/dict/任意对象）中提取 task_id 字符串。"""
    if isinstance(task, (str, int)):
        return str(task)
    if isinstance(task, dict):
        return str(task.get('id') or '')
    if hasattr(task, '__class__') and task.__class__.__name__ == 'Task':
        try:
            return str(task.id)
        except Exception:
            pass
        try:
            from sqlalchemy.orm import object_state
            state = object_state(task)
            if state.persistent and state.identity:
                return str(state.identity[0])
        except Exception:
            pass
        match = re.search(r'\d+', str(task))
        if match:
            return match.group()
    try:
        return str(getattr(task, 'id', None) or '')
    except Exception:
        logger.debug("从任务对象获取 task_id 失败", exc_info=True)
        return ''


def _parse_dt(dt_value) -> Optional[datetime]:
    """ISO 字符串/datetime → datetime，空值返回 None。"""
    if dt_value is None:
        return None
    if isinstance(dt_value, str):
        try:
            return datetime.fromisoformat(dt_value)
        except ValueError:
            return None
    return dt_value


def _ts_ms(dt_value) -> int:
    """datetime/ISO字符串 → 毫秒时间戳（东八区），空值返回当前时间。"""
    dt = _parse_dt(dt_value)
    if dt is None:
        return int(time.time() * 1000)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC8)
    return int(dt.timestamp() * 1000)


def _to_utc8(dt_value):
    """naive datetime 补东八区时区。"""
    if dt_value is not None and dt_value.tzinfo is None:
        return dt_value.replace(tzinfo=UTC8)
    return dt_value


def _compute_elapsed_seconds(started_at, completed_at, updated_at, status) -> float:
    """计算已用时长。

    已结束任务（completed_at 或终态时的 updated_at）使用结束时间作为参照，
    避免持续推送导致已用时长增长。
    """
    start = _to_utc8(started_at)
    if start is None:
        return 0.0
    end_reference = start
    if completed_at:
        end_reference = _to_utc8(completed_at)
    elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED) and updated_at:
        end_reference = _to_utc8(updated_at)
    return max(0.0, (end_reference - start).total_seconds())


def _collect_round_progress(round_progress_cache, task_case_id=None) -> Optional[RoundProgress]:
    """从内存态 round_progress_cache 提取多轮进度。

    gRPC 路径无法用 test_case_id 匹配 TaskCase.id，仅在缓存只有一个条目时
    补充到当前用例；PO 路径按 task_case_id 精确匹配。
    """
    if not round_progress_cache:
        return None
    if task_case_id is not None:
        rp = round_progress_cache.get(task_case_id)
        return RoundProgress(current=rp.get('current', 0), total=rp.get('total', 0)) if rp else None
    if len(round_progress_cache) == 1:
        rp = next(iter(round_progress_cache.values()))
        return RoundProgress(current=rp.get('current', 0), total=rp.get('total', 0))
    return None


def _current_concurrent_from_load_balancer(execution_engine) -> int:
    """从内存态 load_balancer 取所有 URL 的并发总和。"""
    if execution_engine is None:
        return 0
    load_balancer = getattr(execution_engine, 'load_balancer', None)
    if not load_balancer:
        return 0
    url_status = load_balancer.get_url_status()
    return sum(s.get('concurrent', 0) for s in url_status.values())


def _build_logs_via_grpc(task_id_int) -> list:
    """通过 gRPC 查询最近日志并转为 ProgressLogItem 列表。"""
    try:
        from shared.clients.grpc_clients import list_logs
        log_resp = list_logs(task_id=task_id_int, page=1, per_page=20)
        recent_log_items = log_resp.get('items', [])
    except Exception:
        recent_log_items = []
    return [
        ProgressLogItem(
            id=log_item.get('id', 0),
            level=(log_item.get('level') or 'info').lower(),
            message=log_item.get('content') or '',
            timestamp=_ts_ms(log_item.get('time')),
        )
        for log_item in reversed(recent_log_items)
    ]


class _TaskProxy:
    """用于时间预估的 task 伪对象（只包含 calculate_time_estimate 需要的字段）。"""

    def __init__(self, task_id, task_type, task_status, total_cases, completed_cases,
                 failed_cases, started_at, completed_at, updated_at):
        self.id = task_id
        self.type = task_type
        self.status = task_status
        self.total_cases = total_cases
        self.completed_cases = completed_cases
        self.failed_cases = failed_cases
        self.started_at = started_at
        self.completed_at = completed_at
        self.updated_at = updated_at


class ProgressMixin:
    # ────────────────────────── 入口与编排 ──────────────────────────

    def emit_progress(self, task, force=False):
        task_id = _extract_task_id(task)

        if not task_id:
            self._log(level='WARNING', content=f"无法获取任务ID，跳过进度更新", task_id=task_id)
            return

        current_time = time.time()

        if not force and self._throttled(task_id, current_time):
            return

        self._last_progress_time[task_id] = current_time
        min_interval = min(self._min_update_interval, 0.1)

        local_db_session = None

        try:
            task_id_int = int(task_id) if isinstance(task_id, str) else task_id
            grpc_progress = get_task_progress_via_grpc(task_id_int)

            if grpc_progress is not None:
                self._log(level='DEBUG', content=f"使用 gRPC 进度数据，task_id={task_id}, force={force}", task_id=task_id)
                db_task, progress = self._build_progress_from_grpc(task_id, task_id_int, grpc_progress)
            else:
                # PO 回退路径：gRPC 不可用时直连 DB
                local_db_session = get_db_session()
                db_task, progress = self._build_progress_from_po(local_db_session, task_id, task_id_int)
                if db_task is None:
                    self._log(level='WARNING', content=f"找不到任务，跳过进度更新，task_id={task_id}", task_id=task_id)
                    return
                self._log(level='DEBUG', content=f"使用 PO 回退路径生成进度数据，task_id={task_id}, force={force}", task_id=task_id)

            self._finalize_and_emit(
                task_id=task_id,
                db_task=db_task,
                progress=progress,
                min_interval=min_interval,
                force=force,
                current_time=current_time,
            )
        except Exception as e:
            self._log(level='ERROR', content=f"emit_progress 异常: {str(e)}", task_id=task_id, category='error')
            raise
        finally:
            if local_db_session is not None:
                local_db_session.close()

    def _throttled(self, task_id: str, current_time: float) -> bool:
        """初步节流：间隔不足直接跳过；缓存新鲜则直接重发缓存数据。"""
        last_time = self._last_progress_time.get(task_id, 0)
        if current_time - last_time < self._progress_throttle_interval:
            return True

        cached_progress = self._progress_cache.get(task_id)
        if cached_progress and current_time - cached_progress['timestamp'] < 0.1:
            try:
                _socketio = get_socketio()
                if _socketio:
                    _socketio.emit_sync('task_progress', cached_progress['data'])
                    self._log(level='DEBUG', content=f"使用缓存发送进度更新，task_id={task_id}", task_id=task_id)
            except Exception as emit_error:
                self._log(level='WARNING', content=f"使用缓存发送进度更新失败: {str(emit_error)}", task_id=task_id)
            return True
        return False

    # ────────────────────────── gRPC 数据源路径 ──────────────────────────

    def _build_progress_from_grpc(self, task_id, task_id_int, grpc_progress) -> Tuple[_TaskProxy, TaskProgressPayload]:
        """gRPC 路径：使用远端进度数据构造 payload，无 PO 直连。"""
        task_type = grpc_progress.get('type', '')
        current_case = self._build_current_case_from_grpc(task_id, task_type, grpc_progress.get('current_case'))
        test_cases = self._build_test_cases_from_grpc(grpc_progress.get('test_cases', []))
        logs = _build_logs_via_grpc(task_id_int)
        api_resources = self._build_api_resources_from_grpc(task_type, grpc_progress.get('api_resource_status', []))

        started_at = _parse_dt(grpc_progress.get('started_at'))
        completed_at = _parse_dt(grpc_progress.get('completed_at'))
        updated_at = _parse_dt(grpc_progress.get('updated_at'))
        task_status = grpc_progress.get('status', 'unknown')
        actual_total_cases = grpc_progress.get('actual_total_cases', grpc_progress.get('total_cases', 0))
        actual_completed_cases = grpc_progress.get('actual_completed_cases', grpc_progress.get('completed_cases', 0))

        self._log(level='DEBUG',
                  content=f"用例总数: {actual_total_cases}, 已完成: {actual_completed_cases}, 进行中: {grpc_progress.get('in_progress_count', 0)}",
                  task_id=task_id)

        progress = TaskProgressPayload(
            task_id=str(task_id_int),
            status=task_status,
            total_progress=self._calc_progress_percentage(actual_completed_cases, actual_total_cases),
            completed_count=actual_completed_cases,
            in_progress_count=grpc_progress.get('in_progress_count', 0),
            execution_failed_count=grpc_progress.get('execution_failed_count', 0),
            evaluation_failed_count=grpc_progress.get('evaluation_failed_count', 0),
            total_count=actual_total_cases,
            current_case=current_case,
            test_cases=test_cases,
            logs=logs,
            api_resources=api_resources,
            used_time=self._format_duration(
                _compute_elapsed_seconds(started_at, completed_at, updated_at, task_status)
            ) if started_at else "0分钟",
        )

        db_task = _TaskProxy(
            task_id=task_id_int,
            task_type=task_type,
            task_status=task_status,
            total_cases=actual_total_cases,
            completed_cases=actual_completed_cases,
            failed_cases=grpc_progress.get('failed_cases', 0),
            started_at=started_at,
            completed_at=completed_at,
            updated_at=updated_at,
        )
        return db_task, progress

    def _build_current_case_from_grpc(self, task_id, task_type, cc) -> Optional[ProgressCurrentCase]:
        """构造当前执行用例（内存态 step 缺省按任务类型推断）。"""
        if not cc:
            self._log(level='DEBUG', content=f"没有正在执行的用例", task_id=task_id)
            return None
        return ProgressCurrentCase(
            case_id=str(cc.get('case_id', cc.get('caseId', ''))),
            name=cc.get('name', '未知用例'),
            step=cc.get('step', STEP_PLAYING if task_type == TestType.E2E.value else STEP_EVALUATING),
            start_time=_ts_ms(cc.get('started_at')),
        )

    def _build_test_cases_from_grpc(self, raw_test_cases) -> list:
        """构造用例进度列表，并补充内存态多轮进度。"""
        rpc_cache = getattr(self.execution_engine, 'round_progress_cache', {}) if self.execution_engine is not None else {}
        items = []
        for tc in raw_test_cases:
            items.append(ProgressCaseItem(
                id=str(tc.get('id', '')),
                status=tc.get('status', ''),
                execution_status=tc.get('execution_status', tc.get('executionStatus', '')),
                evaluation_status=tc.get('evaluation_status', tc.get('evaluationStatus', '')),
                duration=tc.get('duration', 0),
                error_message=tc.get('error_message', tc.get('errorMessage', '')),
                round_progress=_collect_round_progress(rpc_cache) if items == [] else None,
            ))
        return items

    def _build_api_resources_from_grpc(self, task_type, raw_api_status) -> list:
        """构造 API 资源状态：gRPC 提供排队/耗时，并发量从内存态 load_balancer 补充。"""
        if task_type != TestType.API.value:
            return []
        current_concurrent = _current_concurrent_from_load_balancer(self.execution_engine)
        return [
            ProgressApiResource(
                id=api_info.get('id', ''),
                name=api_info.get('name', ''),
                current_concurrent=current_concurrent,
                queue_length=api_info.get('pending_cases', 0),
                avg_response_time=api_info.get('avg_response_time', 0),
                max_concurrent=api_info.get('default_max_process', 5),
            )
            for api_info in raw_api_status
        ]

    # ────────────────────────── PO 回退数据源路径 ──────────────────────────

    def _build_progress_from_po(self, session, task_id, task_id_int) -> Tuple[Optional[object], TaskProgressPayload]:
        """PO 回退路径：直连 DB 构造 payload（gRPC 不可用时）。"""
        from task_service.infrastructure.persistence.models import Task, TaskCase, TestCase

        db_task = session.get(Task, task_id_int)
        if not db_task:
            return None, TaskProgressPayload(task_id=str(task_id_int), status='unknown')

        current_case = self._build_current_case_from_po(session, task_id, db_task, TaskCase, TestCase)
        test_cases = self._build_test_cases_from_po(session, db_task, TaskCase)
        logs = _build_logs_via_grpc(db_task.id)
        api_resources = self._build_api_resources_from_po(session, db_task)
        in_progress_count = session.query(TaskCase).filter(
            TaskCase.task_id == db_task.id,
            (TaskCase.execution_status.in_(ACTIVE_EXECUTION_STATUSES)) | (TaskCase.evaluation_status == EvaluationStatus.RUNNING) |
            (TaskCase.evaluation_status == EvaluationStatus.CALCULATING)
        ).count()

        actual_total_cases = session.query(TaskCase).filter_by(task_id=db_task.id).count()
        if actual_total_cases != db_task.total_cases:
            db_task.total_cases = actual_total_cases
            session.commit()
        actual_completed_cases = session.query(TaskCase).filter(
            TaskCase.task_id == db_task.id,
            TaskCase.execution_status == ExecutionStatus.COMPLETED,
            TaskCase.status == TaskCaseStatus.COMPLETED
        ).count()

        execution_failed_count = sum(
            1 for tc in test_cases if tc.execution_status == ExecutionStatus.FAILED
        )
        evaluation_failed_count = sum(
            1 for tc in test_cases if tc.evaluation_status == EvaluationStatus.FAILED
        )

        progress = TaskProgressPayload(
            task_id=str(db_task.id),
            status=db_task.status,
            total_progress=self._calc_progress_percentage(actual_completed_cases, actual_total_cases),
            completed_count=actual_completed_cases,
            in_progress_count=in_progress_count,
            execution_failed_count=execution_failed_count,
            evaluation_failed_count=evaluation_failed_count,
            total_count=actual_total_cases,
            current_case=current_case,
            test_cases=test_cases,
            logs=logs,
            api_resources=api_resources,
            used_time=self._format_duration(
                _compute_elapsed_seconds(db_task.started_at, db_task.completed_at, db_task.updated_at, db_task.status)
            ) if db_task.started_at else "0分钟",
        )
        return db_task, progress

    def _build_current_case_from_po(self, session, task_id, db_task, TaskCase, TestCase) -> Optional[ProgressCurrentCase]:
        """构造当前执行用例（PO 直查 RUNNING 状态的 TaskCase）。"""
        current_tc = session.query(TaskCase).filter_by(
            task_id=db_task.id, execution_status=ExecutionStatus.RUNNING
        ).first()
        if not current_tc:
            self._log(level='DEBUG', content=f"没有正在执行的用例", task_id=task_id)
            return None
        case_info = session.get(TestCase, current_tc.test_case_id)
        current_case = ProgressCurrentCase(
            case_id=str(current_tc.test_case_id),
            name=case_info.name if case_info else "未知用例",
            step=STEP_PLAYING if db_task.type == TestType.E2E.value else STEP_EVALUATING,
            start_time=_ts_ms(current_tc.started_at),
        )
        self._log(level='DEBUG',
                  content=f"当前执行用例: {current_case.name} (ID: {current_case.case_id})",
                  task_id=task_id)
        return current_case

    def _build_test_cases_from_po(self, session, db_task, TaskCase) -> list:
        """构造用例进度列表（含执行时长与内存态多轮进度）。"""
        rpc_cache = getattr(self.execution_engine, 'round_progress_cache', {}) if self.execution_engine is not None else {}
        all_task_cases = session.query(TaskCase).filter_by(task_id=db_task.id).all()
        items = []
        for tc in all_task_cases:
            items.append(ProgressCaseItem(
                id=str(tc.test_case_id),
                status=tc.status,
                execution_status=tc.execution_status,
                evaluation_status=tc.evaluation_status,
                duration=self._calc_case_duration(tc),
                error_message=tc.error_message or '',
                round_progress=_collect_round_progress(rpc_cache, task_case_id=tc.id),
            ))
        return items

    @staticmethod
    def _calc_case_duration(tc) -> int:
        """用例执行时长（秒）：completed_at - started_at。"""
        if not (tc.started_at and tc.completed_at):
            return 0
        started_at = _to_utc8(tc.started_at)
        completed_at = _to_utc8(tc.completed_at)
        return int((completed_at - started_at).total_seconds())

    def _build_api_resources_from_po(self, session, db_task) -> list:
        """构造 API 资源状态（PO 回退：按 load_balancer 每个 URL 一条）。"""
        if db_task.type != TestType.API.value:
            return []

        from task_service.infrastructure.persistence.models import TaskAPI, TestResult
        from api_test_service.infrastructure.persistence.models import API

        task_api = session.query(TaskAPI).filter_by(task_id=db_task.id).first()
        if not task_api:
            return []
        api = session.get(API, task_api.api_id)
        if not api:
            return []

        api_executor = getattr(self.execution_engine, 'api_executors', {}).get(str(db_task.id)) if self.execution_engine is not None else None
        load_balancer = getattr(self.execution_engine, 'load_balancer', None) if self.execution_engine is not None else None
        if not (api_executor and load_balancer):
            return []

        pending_cases = session.query(TaskCase).filter(
            TaskCase.task_id == db_task.id,
            TaskCase.execution_status == ExecutionStatus.PENDING
        ).count()
        avg_response_time = self._calc_avg_response_time(session, db_task, TestResult)

        return [
            ProgressApiResource(
                id=str(api.id),
                name=api.name,
                current_concurrent=status.get('concurrent', 0),
                queue_length=pending_cases,
                avg_response_time=avg_response_time,
                max_concurrent=api.default_max_process if hasattr(api, 'default_max_process') else 5,
            )
            for url, status in load_balancer.get_url_status().items()
        ]

    @staticmethod
    def _calc_avg_response_time(session, db_task, TestResult) -> int:
        """已完成用例的平均响应时间（毫秒）。"""
        completed_cases = session.query(TaskCase).filter(
            TaskCase.task_id == db_task.id,
            TaskCase.execution_status == ExecutionStatus.COMPLETED
        ).count()
        if completed_cases <= 0:
            return 0
        completed_results = session.query(TestResult).filter(
            TestResult.task_id == db_task.id,
            TestResult.execution_status == ExecutionStatus.COMPLETED
        ).all()
        total_response_time = sum(result.response_time for result in completed_results if result.response_time)
        if total_response_time <= 0 or not completed_results:
            return 0
        return round(total_response_time / len(completed_results))

    # ────────────────────────── 收尾：预估/变更检测/发射 ──────────────────────────

    def _finalize_and_emit(self, task_id, db_task, progress, min_interval, force, current_time):
        """时间预估、防闪烁平滑、变更检测、缓存与最终发射。"""
        elapsed_seconds, expected_total_seconds, expected_complete_time_str = \
            self._compute_time_estimate(task_id, db_task)

        progress.expected_complete_time = expected_complete_time_str
        progress.expected_total_time = self._format_duration(expected_total_seconds)
        progress.used_time = self._format_duration(elapsed_seconds)

        if self._should_skip_update(task_id, db_task, progress, min_interval, force, current_time):
            return

        self._cache_progress(task_id, db_task, progress, current_time)
        self._emit(task_id, progress)

    def _compute_time_estimate(self, task_id, db_task):
        """计算已用时长与预计总时长（带防闪烁平滑）。"""
        elapsed_seconds = _compute_elapsed_seconds(
            db_task.started_at, db_task.completed_at, db_task.updated_at, db_task.status
        )
        expected_total_seconds = DEFAULT_EXPECTED_TOTAL_SECONDS
        expected_complete_time_str = ''

        if db_task.started_at:
            self._log(level='DEBUG', content=f"任务 {task_id}: 开始计算时间预估，已用时间={elapsed_seconds:.2f}秒", task_id=task_id)
            estimate_result = self.calculate_time_estimate(db_task)
            expected_total_seconds = estimate_result.get('expected_total_time', DEFAULT_EXPECTED_TOTAL_SECONDS)
            expected_complete_time_str = estimate_result.get('expected_complete_time', '')
            self._log(level='DEBUG', content=f"任务 {task_id}: calculate_time_estimate返回，预计总时长={expected_total_seconds}秒", task_id=task_id)

        expected_total_seconds = self._smooth_expected_total(task_id, expected_total_seconds)
        return elapsed_seconds, expected_total_seconds, expected_complete_time_str

    def _smooth_expected_total(self, task_id, expected_total_seconds) -> int:
        """预计总时长防闪烁：变化小于阈值时沿用缓存值。"""
        last_expected_total = self._last_progress.get(task_id, {}).get('expected_total')
        if last_expected_total is not None:
            expected_diff_ratio = abs(expected_total_seconds - last_expected_total) / (last_expected_total or 1)
            if expected_diff_ratio < EXPECTED_TOTAL_SMOOTHING_RATIO:
                self._log(level='DEBUG', content=f"任务 {task_id}: 使用缓存的预计总时长={last_expected_total}秒", task_id=task_id)
                return last_expected_total
        if task_id not in self._last_progress:
            self._last_progress[task_id] = {}
        self._last_progress[task_id]['expected_total'] = expected_total_seconds
        return expected_total_seconds

    def _should_skip_update(self, task_id, db_task, progress, min_interval, force, current_time) -> bool:
        """变更检测：状态/完成数/当前用例/最小间隔均无变化时跳过发射。"""
        last_progress_info = self._last_progress.get(task_id, {})
        last_time = last_progress_info.get('time', 0)
        last_completed = last_progress_info.get('completed', -1)
        last_status = last_progress_info.get('status', '')
        last_current_case = last_progress_info.get('current_case')

        reasons = []
        if force:
            reasons.append("强制更新进度")
        elif min_interval <= 0:
            reasons.append("最小更新间隔为0")
        elif db_task.status == TaskStatus.RUNNING and last_status != TaskStatus.RUNNING:
            reasons.append("任务开始执行")
        elif db_task.status == TaskStatus.COMPLETED and last_status != TaskStatus.COMPLETED:
            reasons.append("任务完成")
        elif db_task.status == TaskStatus.FAILED and last_status != TaskStatus.FAILED:
            reasons.append("任务失败")
        elif current_time - last_time >= min_interval:
            reasons.append(f"达到最小更新间隔, elapsed={current_time - last_time:.3f}s")
        elif db_task.completed_cases != last_completed:
            reasons.append(f"完成用例数变化, last={last_completed}, current={db_task.completed_cases}")
        elif progress.current_case != last_current_case:
            reasons.append("当前执行用例变化")

        if not reasons:
            self._log(level='DEBUG',
                      content=f"跳过进度更新（节流），task_id={task_id}, last_time={last_time}, last_completed={last_completed}, last_status={last_status}",
                      task_id=task_id)
            return True

        self._log(level='DEBUG', content=f"{reasons[0]}，更新进度，task_id={task_id}", task_id=task_id)
        return False

    def _cache_progress(self, task_id, db_task, progress, current_time):
        """记录上次发射状态与 payload 缓存。"""
        self._last_progress[task_id] = {
            'time': current_time,
            'completed': db_task.completed_cases,
            'status': db_task.status,
            'current_case': progress.current_case,
        }
        self._progress_cache[task_id] = {
            'data': progress.model_dump(),
            'timestamp': current_time,
        }

    def _emit(self, task_id, progress):
        """发射 task_progress 事件（snake_case payload）。"""
        payload = progress.model_dump()
        try:
            _socketio = get_socketio()
            if _socketio:
                _socketio.emit_sync('task_progress', payload)
                self._log(level='DEBUG',
                          content=f"成功发送 task_progress 事件，task_id={task_id}, progress={progress.total_progress}%",
                          task_id=task_id)
        except Exception as emit_error:
            self._log(level='ERROR', content=f"发送 task_progress 事件失败: {str(emit_error)}", task_id=task_id)
            raise

    @staticmethod
    def _calc_progress_percentage(completed, total) -> float:
        """完成度百分比（上限 100）。"""
        percentage = round(completed / total * 100, 2) if total > 0 else 0
        return min(percentage, 100.0)
