import time
from datetime import datetime, timezone, timedelta
from shared.models.models import Task, TaskCase, TestCase, Log, TestResult
from shared.models.database import db
from shared.utils.event_manager._common import get_socketio


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
            except:
                pass

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

        local_db_session = db.session()
        current_case_data = None
        progress_data = None

        try:
            task_id_int = int(task_id) if isinstance(task_id, str) else task_id
            db_task = local_db_session.get(Task, task_id_int)
            if not db_task:
                self._log(level='WARNING', content=f"找不到任务，跳过进度更新，task_id={task_id}", task_id=task_id)
                return

            self._log(level='DEBUG', content=f"开始生成进度数据，task_id={task_id}, force={force}", task_id=task_id)

            current_tc = local_db_session.query(TaskCase).filter_by(task_id=db_task.id, execution_status='running').first()
            if current_tc:
                case_info = local_db_session.get(TestCase, current_tc.test_case_id)
                current_case_data = {
                    "caseId": str(current_tc.test_case_id),
                    "name": case_info.name if case_info else "未知用例",
                    "step": "playing" if db_task.type == 'e2e' else "evaluating",
                    "startTime": int(current_tc.started_at.timestamp() * 1000) if current_tc.started_at else int(time.time() * 1000)
                }
                self._log(level='DEBUG', content=f"当前执行用例: {current_case_data.get('name', '未知')} (ID: {current_case_data.get('caseId', '未知')})", task_id=task_id)
            else:
                self._log(level='DEBUG', content=f"没有正在执行的用例", task_id=task_id)

            all_task_cases = local_db_session.query(TaskCase).filter_by(task_id=db_task.id).all()
            test_cases_data = []
            pending_count = 0
            running_count = 0
            completed_count = 0
            failed_count = 0

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

                # Multi-round progress: read from execution_engine in-memory cache
                if self.execution_engine is not None:
                    round_progress = getattr(self.execution_engine, 'round_progress_cache', {}).get(tc.id)
                    if round_progress:
                        test_cases_data[-1]['roundProgress'] = {
                            'current': round_progress.get('current', 0),
                            'total': round_progress.get('total', 0),
                        }

                if tc.execution_status in ['pending', 'queued']:
                    pending_count += 1
                elif tc.execution_status == 'running':
                    running_count += 1
                elif tc.execution_status == 'completed':
                    completed_count += 1
                elif tc.execution_status == 'failed':
                    failed_count += 1

            self._log(level='DEBUG', content=f"用例统计: pending={pending_count}, running={running_count}, completed={completed_count}, failed={failed_count}", task_id=task_id)

            recent_logs = local_db_session.query(Log).filter_by(task_id=db_task.id).order_by(Log.time.desc()).limit(20).all()
            logs_data = [{
                "id": l.id,
                "level": l.level.lower() if l.level else 'info',
                "message": l.content,
                "timestamp": int(l.time.timestamp() * 1000) if l.time else int(time.time() * 1000)
            } for l in reversed(recent_logs)]

            in_progress_count = local_db_session.query(TaskCase).filter(
                TaskCase.task_id == db_task.id,
                (TaskCase.execution_status.in_(['running', 'queued'])) | (TaskCase.evaluation_status == 'running') |
                (TaskCase.evaluation_status == 'calculating')
            ).count()

            api_resources_status = []
            if db_task.type == 'api':
                from shared.models.models import TaskAPI, API
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
                                        TaskCase.execution_status == 'pending'
                                    ).count()
                                    avg_response_time = 0
                                    completed_cases = local_db_session.query(TaskCase).filter(
                                        TaskCase.task_id == db_task.id,
                                        TaskCase.execution_status == 'completed'
                                    ).count()
                                    if completed_cases > 0:
                                        total_response_time = 0
                                        completed_results = local_db_session.query(TestResult).filter(
                                            TestResult.task_id == db_task.id,
                                            TestResult.execution_status == 'completed'
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
                # 任务已结束（completed/failed）时，使用 completed_at - started_at 作为已用时长，
                # 避免持续推送导致 usedTime 不断增长
                end_reference = started_at
                if db_task.completed_at:
                    completed_at = db_task.completed_at
                    if not completed_at.tzinfo:
                        completed_at = completed_at.replace(tzinfo=timezone(timedelta(hours=8)))
                    end_reference = completed_at
                elif db_task.status in ('completed', 'failed'):
                    # 状态已结束但 completed_at 缺失时，退而使用 updatedAt
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
                TaskCase.execution_status == 'completed',
                TaskCase.status == 'completed'
            ).count()
            progress_percentage = round(actual_completed_cases / actual_total_cases * 100, 2) if actual_total_cases > 0 else 0
            progress_percentage = min(progress_percentage, 100.0)

            execution_failed_count = sum(
                1 for tc in test_cases_data if tc.get("executionStatus") == "failed"
            )
            evaluation_failed_count = sum(
                1 for tc in test_cases_data if tc.get("evaluationStatus") == "failed"
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
                elif db_task.status in ('completed', 'failed'):
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
            elif db_task.status == 'running' and last_status != 'running':
                need_update = True
                self._log(level='DEBUG', content=f"任务开始执行，更新进度，task_id={task_id}", task_id=task_id)
            elif db_task.status == 'completed' and last_status != 'completed':
                need_update = True
                self._log(level='DEBUG', content=f"任务完成，更新进度，task_id={task_id}", task_id=task_id)
            elif db_task.status == 'failed' and last_status != 'failed':
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
            local_db_session.close()
