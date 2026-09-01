import time
import logging
from datetime import datetime, timezone, timedelta
from shared.models.database import get_db_session
from shared.models.common_enums import TestType
from shared.utils.event_manager._common import get_socketio
from shared.utils.status_constants import (
    ACTIVE_EXECUTION_STATUSES,
    ExecutionStatus,
    EvaluationStatus,
    TaskCaseStatus,
    TaskStatus,
)

logger = logging.getLogger(__name__)

# 缓存策略：使用 shared.utils.task_data_cache 的 TTL 缓存减少 DB 往返。
# gRPC GetTaskProgress 现已返回完整进度数据（test_cases 列表/计数/api_resource_status），
# 优先走 gRPC 缓存；PO 直连仅用于 gRPC 不可用时的回退，以及内存态数据
#（execution_engine.round_progress_cache / load_balancer.url_status）。
from shared.utils.task_data_cache import get_task_progress_via_grpc


class ProgressMixin:
    def emit_progress(self, task, force=False):
        task_id = None

        if isinstance(task, (str, int)):
            task_id = str(task)
        elif hasattr(task, '__class__') and task.__class__.__name__ == 'Task':
            try:
                task_id = str(task.id)
            except:
                try:
                    from sqlalchemy.orm import object_state
                    state = object_state(task)
                    if state.persistent:
                        task_id = str(state.identity[0]) if state.identity else None
                except:
                    import re
                    match = re.search(r'\d+', str(task))
                    if match:
                        task_id = match.group()
        elif isinstance(task, dict):
            task_id = str(task.get('id'))
        else:
            try:
                task_id = str(getattr(task, 'id', None))
            except Exception:
                logger.debug("从任务对象获取 task_id 失败", exc_info=True)

        if not task_id:
            self._log(level='WARNING', content=f"无法获取任务ID，跳过进度更新", task_id=task_id)
            return

        current_time = time.time()

        # 如果不是强制更新，执行初步节流
        if not force:
            last_time = self._last_progress_time.get(task_id, 0)
            if current_time - last_time < self._progress_throttle_interval:
                return

            cached_progress = self._progress_cache.get(task_id)
            if cached_progress and current_time - cached_progress['timestamp'] < 0.1:
                progress_data = cached_progress['data']
                try:
                    _socketio = get_socketio()
                    if _socketio:
                        _socketio.emit_sync('task_progress', progress_data)
                        self._log(level='DEBUG', content=f"使用缓存发送进度更新，task_id={task_id}", task_id=task_id)
                except Exception as emit_error:
                    self._log(level='WARNING', content=f"使用缓存发送进度更新失败: {str(emit_error)}", task_id=task_id)
                return

        self._last_progress_time[task_id] = current_time
        min_interval = min(self._min_update_interval, 0.1)

        local_db_session = None
        current_case_data = None
        progress_data = None

        try:
            # 优先通过 gRPC 缓存获取完整进度数据
            # gRPC GetTaskProgress 返回 task_id/status/type/total/completed/failed/progress/
            # current_case/test_cases/in_progress_count/actual_total/actual_completed/
            # execution_failed/evaluation_failed/api_resource_status/started_at/completed_at/updated_at
            task_id_int = int(task_id) if isinstance(task_id, str) else task_id
            grpc_progress = get_task_progress_via_grpc(task_id_int)

            if grpc_progress is not None:
                # ---- gRPC 路径：使用远端进度数据，无 PO 直连 ----
                self._log(level='DEBUG', content=f"使用 gRPC 进度数据，task_id={task_id}, force={force}", task_id=task_id)

                task_status = grpc_progress.get('status', 'unknown')
                task_type = grpc_progress.get('type', '')
                actual_total_cases = grpc_progress.get('actual_total_cases', grpc_progress.get('total_cases', 0))
                actual_completed_cases = grpc_progress.get('actual_completed_cases', grpc_progress.get('completed_cases', 0))
                in_progress_count = grpc_progress.get('in_progress_count', 0)
                execution_failed_count = grpc_progress.get('execution_failed_count', 0)
                evaluation_failed_count = grpc_progress.get('evaluation_failed_count', 0)

                # current_case: 转换字段名以匹配前端格式
                cc = grpc_progress.get('current_case')
                if cc:
                    current_case_data = {
                        "caseId": str(cc.get('case_id', cc.get('caseId', ''))),
                        "name": cc.get('name', '未知用例'),
                        "step": cc.get('step', 'playing' if task_type == TestType.E2E.value else 'evaluating'),
                        "startTime": int(datetime.fromisoformat(cc['started_at']).timestamp() * 1000) if cc.get('started_at') else int(time.time() * 1000),
                    }
                else:
                    self._log(level='DEBUG', content=f"没有正在执行的用例", task_id=task_id)

                # test_cases: 转换字段名以匹配前端格式
                raw_test_cases = grpc_progress.get('test_cases', [])
                test_cases_data = []
                for tc in raw_test_cases:
                    test_cases_data.append({
                        "id": str(tc.get('id', '')),
                        "status": tc.get('status', ''),
                        "executionStatus": tc.get('execution_status', tc.get('executionStatus', '')),
                        "evaluationStatus": tc.get('evaluation_status', tc.get('evaluationStatus', '')),
                        "duration": tc.get('duration', 0),
                        "errorMessage": tc.get('error_message', tc.get('errorMessage', '')),
                    })

                    # Multi-round progress: read from execution_engine in-memory cache
                    if self.execution_engine is not None:
                        # round_progress_cache 使用 TaskCase 的整数 id 作为 key
                        # gRPC 只返回了 test_case_id，我们需要 case 的真实 id
                        # 这个数据只能从内存获取，gRPC 无法提供
                        pass

                # 补充 roundProgress（内存态数据，gRPC 无法提供）
                if self.execution_engine is not None:
                    rpc_cache = getattr(self.execution_engine, 'round_progress_cache', {})
                    # round_progress_cache 的 key 是 TaskCase.id (数据库自增ID)
                    # gRPC 只返回了 test_case_id，无法直接匹配
                    # 遍历所有 round_progress 条目
                    for tc_id, rp in rpc_cache.items():
                        # 找到对应的 test_case 并补充 roundProgress
                        # 这里 tc_id 是 TaskCase.id，与 test_case_id 不同
                        # 简单处理：如果只有一个 round_progress 条目，补充到当前用例
                        if len(rpc_cache) == 1 and test_cases_data:
                            test_cases_data[0]['roundProgress'] = {
                                'current': rp.get('current', 0),
                                'total': rp.get('total', 0),
                            }
                        break

                self._log(level='DEBUG', content=f"用例总数: {actual_total_cases}, 已完成: {actual_completed_cases}, 进行中: {in_progress_count}", task_id=task_id)

                # 通过 gRPC 查询最近日志
                try:
                    from shared.clients.grpc_clients import list_logs
                    log_resp = list_logs(task_id=task_id_int, page=1, per_page=20)
                    recent_log_items = log_resp.get('items', [])
                except Exception:
                    recent_log_items = []
                logs_data = [{
                    "id": log_item.get('id', 0),
                    "level": (log_item.get('level') or 'info').lower(),
                    "message": log_item.get('content') or '',
                    "timestamp": int(datetime.fromisoformat(log_item['time']).timestamp() * 1000) if log_item.get('time') else int(time.time() * 1000)
                } for log_item in reversed(recent_log_items)]

                # API 资源状态：gRPC 提供 pending_cases/completed_cases/avg_response_time，
                # 但 currentConcurrent 和 maxConcurrent 需要从 in-memory load_balancer 补充
                api_resources_status = []
                if task_type == TestType.API.value:
                    raw_api_status = grpc_progress.get('api_resource_status', [])
                    for api_info in raw_api_status:
                        # 从内存态 load_balancer 补充 currentConcurrent
                        current_concurrent = 0
                        if self.execution_engine is not None:
                            load_balancer = getattr(self.execution_engine, 'load_balancer', None)
                            if load_balancer:
                                url_status = load_balancer.get_url_status()
                                # 取所有 URL 的并发总和
                                current_concurrent = sum(s.get('concurrent', 0) for s in url_status.values())

                        api_resources_status.append({
                            "id": api_info.get('id', ''),
                            "name": api_info.get('name', ''),
                            "currentConcurrent": current_concurrent,
                            "queueLength": api_info.get('pending_cases', 0),
                            "avgResponseTime": api_info.get('avg_response_time', 0),
                            "maxConcurrent": api_info.get('default_max_process', 5),
                        })

                # 时间计算
                now = datetime.now(timezone(timedelta(hours=8)))
                started_at_str = grpc_progress.get('started_at')
                elapsed_seconds_for_display = 0.0
                if started_at_str:
                    started_at = datetime.fromisoformat(started_at_str)
                    if started_at.tzinfo is None:
                        started_at = started_at.replace(tzinfo=timezone(timedelta(hours=8)))
                    end_reference = started_at
                    completed_at_str = grpc_progress.get('completed_at')
                    if completed_at_str:
                        completed_at = datetime.fromisoformat(completed_at_str)
                        if completed_at.tzinfo is None:
                            completed_at = completed_at.replace(tzinfo=timezone(timedelta(hours=8)))
                        end_reference = completed_at
                    elif task_status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                        updated_at_str = grpc_progress.get('updated_at')
                        if updated_at_str:
                            updated_at = datetime.fromisoformat(updated_at_str)
                            if updated_at.tzinfo is None:
                                updated_at = updated_at.replace(tzinfo=timezone(timedelta(hours=8)))
                            end_reference = updated_at
                    else:
                        end_reference = now
                    elapsed_seconds_for_display = max(0.0, (end_reference - started_at).total_seconds())

                progress_percentage = round(actual_completed_cases / actual_total_cases * 100, 2) if actual_total_cases > 0 else 0
                progress_percentage = min(progress_percentage, 100.0)

                progress_data = {
                    "taskId": str(task_id_int),
                    "totalProgress": progress_percentage,
                    "status": task_status,
                    "completedCount": actual_completed_cases,
                    "inProgressCount": in_progress_count,
                    "executionFailedCount": execution_failed_count,
                    "evaluationFailedCount": evaluation_failed_count,
                    "totalCount": actual_total_cases,
                    "currentCase": current_case_data,
                    "testCases": test_cases_data,
                    "logs": logs_data,
                    "apiResources": api_resources_status,
                    "expectedCompleteTime": None,
                    "expectedTotalTime": None,
                    "usedTime": self._format_duration(elapsed_seconds_for_display) if started_at_str else "0分钟"
                }

                # 用于时间预估的 task 伪对象（只包含 calculate_time_estimate 需要的字段）
                class _TaskProxy:
                    pass
                db_task = _TaskProxy()
                db_task.id = task_id_int
                db_task.type = task_type
                db_task.status = task_status
                db_task.total_cases = actual_total_cases
                db_task.completed_cases = actual_completed_cases
                db_task.failed_cases = grpc_progress.get('failed_cases', 0)
                db_task.started_at = datetime.fromisoformat(started_at_str) if started_at_str else None
                completed_at_str = grpc_progress.get('completed_at')
                db_task.completed_at = datetime.fromisoformat(completed_at_str) if completed_at_str else None
                updated_at_str = grpc_progress.get('updated_at')
                db_task.updated_at = datetime.fromisoformat(updated_at_str) if updated_at_str else None

            else:
                # ---- PO 回退路径：gRPC 不可用时直连 DB ----
                local_db_session = get_db_session()

                from task_service.infrastructure.persistence.models import Task, TaskCase, TestCase, TestResult
                db_task = local_db_session.get(Task, task_id_int)
                if not db_task:
                    self._log(level='WARNING', content=f"找不到任务，跳过进度更新，task_id={task_id}", task_id=task_id)
                    return

                self._log(level='DEBUG', content=f"使用 PO 回退路径生成进度数据，task_id={task_id}, force={force}", task_id=task_id)

                current_tc = local_db_session.query(TaskCase).filter_by(task_id=db_task.id, execution_status=ExecutionStatus.RUNNING).first()
                if current_tc:
                    case_info = local_db_session.get(TestCase, current_tc.test_case_id)
                    current_case_data = {
                        "caseId": str(current_tc.test_case_id),
                        "name": case_info.name if case_info else "未知用例",
                        "step": "playing" if db_task.type == TestType.E2E.value else "evaluating",
                        "startTime": int(current_tc.started_at.timestamp() * 1000) if current_tc.started_at else int(time.time() * 1000)
                    }
                    self._log(level='DEBUG', content=f"当前执行用例: {current_case_data.get('name', '未知')} (ID: {current_case_data.get('caseId', '未知')})", task_id=task_id)
                else:
                    self._log(level='DEBUG', content=f"没有正在执行的用例", task_id=task_id)

                all_task_cases = local_db_session.query(TaskCase).filter_by(task_id=db_task.id).all()
                test_cases_data = []

                for tc in all_task_cases:
                    evaluation_status = tc.evaluation_status
                    duration = 0
                    if tc.started_at and tc.completed_at:
                        utc_plus_8 = timezone(timedelta(hours=8))
                        started_at = tc.started_at
                        completed_at = tc.completed_at
                        if started_at.tzinfo is None:
                            started_at = started_at.replace(tzinfo=utc_plus_8)
                        if completed_at.tzinfo is None:
                            completed_at = completed_at.replace(tzinfo=utc_plus_8)
                        duration = int((completed_at - started_at).total_seconds())

                    test_cases_data.append({
                        "id": str(tc.test_case_id),
                        "status": tc.status,
                        "executionStatus": tc.execution_status,
                        "evaluationStatus": evaluation_status,
                        "duration": duration,
                        "errorMessage": tc.error_message
                    })

                    if self.execution_engine is not None:
                        round_progress = getattr(self.execution_engine, 'round_progress_cache', {}).get(tc.id)
                        if round_progress:
                            test_cases_data[-1]['roundProgress'] = {
                                'current': round_progress.get('current', 0),
                                'total': round_progress.get('total', 0),
                            }

                # 通过 gRPC 查询最近日志
                try:
                    from shared.clients.grpc_clients import list_logs
                    log_resp = list_logs(task_id=db_task.id, page=1, per_page=20)
                    recent_log_items = log_resp.get('items', [])
                except Exception:
                    recent_log_items = []
                logs_data = [{
                    "id": log_item.get('id', 0),
                    "level": (log_item.get('level') or 'info').lower(),
                    "message": log_item.get('content') or '',
                    "timestamp": int(datetime.fromisoformat(log_item['time']).timestamp() * 1000) if log_item.get('time') else int(time.time() * 1000)
                } for log_item in reversed(recent_log_items)]

                in_progress_count = local_db_session.query(TaskCase).filter(
                    TaskCase.task_id == db_task.id,
                    (TaskCase.execution_status.in_(ACTIVE_EXECUTION_STATUSES)) | (TaskCase.evaluation_status == EvaluationStatus.RUNNING) |
                    (TaskCase.evaluation_status == EvaluationStatus.CALCULATING)
                ).count()

                api_resources_status = []
                if db_task.type == TestType.API.value:
                    from task_service.infrastructure.persistence.models import TaskAPI
                    from api_test_service.infrastructure.persistence.models import API
                    task_api = local_db_session.query(TaskAPI).filter_by(task_id=db_task.id).first()
                    if task_api:
                        api = local_db_session.get(API, task_api.api_id)
                        if api:
                            api_executor = getattr(self.execution_engine, 'api_executors', {}).get(str(db_task.id)) if self.execution_engine is not None else None
                            if api_executor:
                                load_balancer = getattr(self.execution_engine, 'load_balancer', None) if self.execution_engine is not None else None
                                if load_balancer:
                                    url_status = load_balancer.get_url_status()
                                    for url, status in url_status.items():
                                        pending_cases = local_db_session.query(TaskCase).filter(
                                            TaskCase.task_id == db_task.id,
                                            TaskCase.execution_status == ExecutionStatus.PENDING
                                        ).count()
                                        avg_response_time = 0
                                        completed_cases = local_db_session.query(TaskCase).filter(
                                            TaskCase.task_id == db_task.id,
                                            TaskCase.execution_status == ExecutionStatus.COMPLETED
                                        ).count()
                                        if completed_cases > 0:
                                            total_response_time = 0
                                            completed_results = local_db_session.query(TestResult).filter(
                                                TestResult.task_id == db_task.id,
                                                TestResult.execution_status == ExecutionStatus.COMPLETED
                                            ).all()
                                            for result in completed_results:
                                                if result.response_time:
                                                    total_response_time += result.response_time
                                            if total_response_time > 0:
                                                avg_response_time = round(total_response_time / len(completed_results))

                                        api_resources_status.append({
                                            "id": str(api.id),
                                            "name": api.name,
                                            "currentConcurrent": status.get('concurrent', 0),
                                            "queueLength": pending_cases,
                                            "avgResponseTime": avg_response_time,
                                            "maxConcurrent": api.default_max_process if hasattr(api, 'default_max_process') else 5
                                        })

                now = datetime.now(timezone(timedelta(hours=8)))
                started_at = db_task.started_at
                elapsed_seconds_for_display = 0.0
                if started_at:
                    if not started_at.tzinfo:
                        started_at = started_at.replace(tzinfo=timezone(timedelta(hours=8)))
                    end_reference = started_at
                    if db_task.completed_at:
                        completed_at = db_task.completed_at
                        if not completed_at.tzinfo:
                            completed_at = completed_at.replace(tzinfo=timezone(timedelta(hours=8)))
                        end_reference = completed_at
                    elif db_task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                        updated_at = db_task.updated_at
                        if updated_at:
                            if not updated_at.tzinfo:
                                updated_at = updated_at.replace(tzinfo=timezone(timedelta(hours=8)))
                            end_reference = updated_at
                    else:
                        end_reference = now
                    elapsed_seconds_for_display = max(0.0, (end_reference - started_at).total_seconds())

                actual_total_cases = local_db_session.query(TaskCase).filter_by(task_id=db_task.id).count()
                if actual_total_cases != db_task.total_cases:
                    db_task.total_cases = actual_total_cases
                    local_db_session.commit()
                actual_completed_cases = local_db_session.query(TaskCase).filter(
                    TaskCase.task_id == db_task.id,
                    TaskCase.execution_status == ExecutionStatus.COMPLETED,
                    TaskCase.status == TaskCaseStatus.COMPLETED
                ).count()
                progress_percentage = round(actual_completed_cases / actual_total_cases * 100, 2) if actual_total_cases > 0 else 0
                progress_percentage = min(progress_percentage, 100.0)

                execution_failed_count = sum(
                    1 for tc in test_cases_data if tc.get("executionStatus") == ExecutionStatus.FAILED
                )
                evaluation_failed_count = sum(
                    1 for tc in test_cases_data if tc.get("evaluationStatus") == EvaluationStatus.FAILED
                )

                progress_data = {
                    "taskId": str(db_task.id),
                    "totalProgress": progress_percentage,
                    "status": db_task.status,
                    "completedCount": actual_completed_cases,
                    "inProgressCount": in_progress_count,
                    "executionFailedCount": execution_failed_count,
                    "evaluationFailedCount": evaluation_failed_count,
                    "totalCount": actual_total_cases,
                    "currentCase": current_case_data,
                    "testCases": test_cases_data,
                    "logs": logs_data,
                    "apiResources": api_resources_status,
                    "expectedCompleteTime": None,
                    "expectedTotalTime": None,
                    "usedTime": self._format_duration(elapsed_seconds_for_display) if started_at else "0分钟"
                }

            # 默认值，防止 started_at 为 None 时变量未定义
            elapsed_seconds = elapsed_seconds_for_display
            expected_total_seconds = 60
            expected_complete_time_str = ''

            if db_task.started_at:
                started_at = db_task.started_at
                if not started_at.tzinfo:
                    started_at = started_at.replace(tzinfo=timezone(timedelta(hours=8)))

                # 已结束任务使用 completed_at/updated_at - started_at 作为已用时长，避免持续推送导致增长
                end_reference = now
                if db_task.completed_at:
                    completed_at = db_task.completed_at
                    if not completed_at.tzinfo:
                        completed_at = completed_at.replace(tzinfo=timezone(timedelta(hours=8)))
                    end_reference = completed_at
                elif db_task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                    updated_at = db_task.updated_at
                    if updated_at:
                        if not updated_at.tzinfo:
                            updated_at = updated_at.replace(tzinfo=timezone(timedelta(hours=8)))
                        end_reference = updated_at

                elapsed_seconds = max(0.0, (end_reference - started_at).total_seconds())

                self._log(level='DEBUG', content=f"任务 {task_id}: 开始计算时间预估，已用时间={elapsed_seconds:.2f}秒", task_id=task_id)

                estimate_result = self.calculate_time_estimate(db_task)
                expected_total_seconds = estimate_result.get('expected_total_time', 60)
                expected_complete_time_str = estimate_result.get('expected_complete_time', '')

                self._log(level='DEBUG', content=f"任务 {task_id}: calculate_time_estimate返回，预计总时长={expected_total_seconds}秒", task_id=task_id)

                estimated_remaining_seconds = max(0, expected_total_seconds - elapsed_seconds)

                self._log(level='DEBUG', content=f"任务 {task_id}: 计算剩余时间={estimated_remaining_seconds:.2f}秒", task_id=task_id)

            # 缓存预计总时长，避免频繁变化导致UI闪烁
            last_expected_total = self._last_progress.get(task_id, {}).get('expected_total', None)
            self._log(level='DEBUG', content=f"任务 {task_id}: 预计总时长计算值={expected_total_seconds}秒, 缓存值={last_expected_total}", task_id=task_id)

            if last_expected_total is not None:
                # 如果变化超过10%或者从None变为有值，才认为需要更新
                expected_diff_ratio = abs(expected_total_seconds - last_expected_total) / (last_expected_total or 1)
                self._log(level='DEBUG', content=f"任务 {task_id}: 预计总时长变化比例={expected_diff_ratio:.2%}", task_id=task_id)

                if expected_diff_ratio < 0.1:
                    # 变化小于10%，使用缓存的值，避免闪烁
                    expected_total_seconds = last_expected_total
                    self._log(level='DEBUG', content=f"任务 {task_id}: 使用缓存的预计总时长={expected_total_seconds}秒", task_id=task_id)
                else:
                    # 变化大于10%，使用新值
                    self._log(level='DEBUG', content=f"任务 {task_id}: 使用新计算的预计总时长={expected_total_seconds}秒", task_id=task_id)
            # 更新缓存
            if task_id not in self._last_progress:
                self._last_progress[task_id] = {}
            self._last_progress[task_id]['expected_total'] = expected_total_seconds

            self._log(level='DEBUG', content=f"任务 {task_id}: 最终使用的预计总时长={expected_total_seconds}秒", task_id=task_id)

            progress_data["expectedCompleteTime"] = expected_complete_time_str
            progress_data["expectedTotalTime"] = self._format_duration(expected_total_seconds)
            progress_data["usedTime"] = self._format_duration(elapsed_seconds)

            last_progress_info = self._last_progress.get(task_id, {})
            last_time = last_progress_info.get('time', 0)
            last_completed = last_progress_info.get('completed', -1)
            last_status = last_progress_info.get('status', '')
            last_current_case = last_progress_info.get('current_case', None)

            need_update = False

            if force:
                need_update = True
                self._log(level='DEBUG', content=f"强制更新进度，task_id={task_id}", task_id=task_id)
            elif min_interval <= 0:
                need_update = True
                self._log(level='DEBUG', content=f"最小更新间隔为0，更新进度，task_id={task_id}", task_id=task_id)
            elif db_task.status == TaskStatus.RUNNING and last_status != TaskStatus.RUNNING:
                need_update = True
                self._log(level='DEBUG', content=f"任务开始执行，更新进度，task_id={task_id}", task_id=task_id)
            elif db_task.status == TaskStatus.COMPLETED and last_status != TaskStatus.COMPLETED:
                need_update = True
                self._log(level='DEBUG', content=f"任务完成，更新进度，task_id={task_id}", task_id=task_id)
            elif db_task.status == TaskStatus.FAILED and last_status != TaskStatus.FAILED:
                need_update = True
                self._log(level='DEBUG', content=f"任务失败，更新进度，task_id={task_id}", task_id=task_id)
            elif current_time - last_time >= min_interval:
                need_update = True
                self._log(level='DEBUG', content=f"达到最小更新间隔，更新进度，task_id={task_id}, elapsed={current_time - last_time:.3f}s", task_id=task_id)
            elif db_task.completed_cases != last_completed:
                need_update = True
                self._log(level='DEBUG', content=f"完成用例数变化，更新进度，task_id={task_id}, last={last_completed}, current={db_task.completed_cases}", task_id=task_id)
            elif current_case_data != last_current_case:
                need_update = True
                self._log(level='DEBUG', content=f"当前执行用例变化，更新进度，task_id={task_id}", task_id=task_id)

            if not need_update:
                self._log(level='DEBUG', content=f"跳过进度更新（节流），task_id={task_id}, last_time={last_time}, last_completed={last_completed}, last_status={last_status}", task_id=task_id)
                return

            self._last_progress[task_id] = {
                'time': current_time,
                'completed': db_task.completed_cases,
                'status': db_task.status,
                'current_case': current_case_data
            }

            self._progress_cache[task_id] = {
                'data': progress_data,
                'timestamp': current_time
            }

            try:
                _socketio = get_socketio()
                if _socketio:
                    _socketio.emit_sync('task_progress', progress_data)
                    self._log(level='DEBUG', content=f"成功发送 task_progress 事件，task_id={task_id}, progress={progress_data.get('totalProgress', 0)}%", task_id=task_id)
                    self._log(level='DEBUG', content=f"成功发送 task_progress 事件，task_id={task_id}, progress={progress_data.get('totalProgress', 0)}%", task_id=task_id)
            except Exception as emit_error:
                self._log(level='ERROR', content=f"发送 task_progress 事件失败: {str(emit_error)}", task_id=task_id)
                raise
        except Exception as e:
            self._log(level='ERROR', content=f"emit_progress 异常: {str(e)}", task_id=task_id, category='error')
            raise
        finally:
            if local_db_session is not None:
                local_db_session.close()
