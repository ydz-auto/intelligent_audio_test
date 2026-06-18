import time
from datetime import datetime, timezone, timedelta
from backend.models.models import Task, TaskCase, TestCase, Log, TestResult, TestResultDimension, Audio
from backend.models.database import db
from backend.controllers.log_controller import LogController
from backend.app import socketio

class EventManager:
    def _log(self, level, content, task_id=None, test_case_id=None, api_id=None, category='execution', module='EventManager', **kwargs):
        kwargs_to_use = kwargs.copy()
        kwargs_to_use.pop('source', None)
        LogController.log_and_emit(
            level=level,
            module=module,
            category=category,
            content=content,
            task_id=task_id,
            api_id=api_id,
            test_case_id=test_case_id,
            source='backend',
            **kwargs_to_use
        )

    def _format_duration(self, seconds_value):
        try:
            seconds = float(seconds_value or 0)
        except Exception:
            return None
        if seconds <= 0:
            return "0分钟"
        seconds_int = int(seconds)
        if seconds_int < 60:
            return f"{seconds_int}秒"
        if seconds_int < 3600:
            minutes = seconds_int // 60
            remain_seconds = seconds_int % 60
            if remain_seconds > 0:
                return f"{minutes}分钟{remain_seconds}秒"
            return f"{minutes}分钟"
        hours = seconds_int // 3600
        minutes = (seconds_int % 3600) // 60
        if minutes > 0:
            return f"{hours}小时{minutes}分钟"
        return f"{hours}小时"

    def __init__(self, execution_engine):
        self.execution_engine = execution_engine
        self._last_progress = {}
        try:
            from backend.config.config import config
            from flask import current_app
            if current_app and hasattr(current_app, 'config'):
                self._min_update_interval = current_app.config.get('WEBSOCKET_MIN_UPDATE_INTERVAL', 0.1)
            else:
                self._min_update_interval = config['default'].WEBSOCKET_MIN_UPDATE_INTERVAL
        except Exception as e:
            self._min_update_interval = 0.1

        self._progress_throttle_interval = 0.05
        self._last_progress_time = {}
        self._progress_cache = {}  # 进度缓存，减少数据库查询
    
    def calculate_time_estimate(self, task):
        """
        计算任务的时间预估
        
        Args:
            task: Task对象
            
        Returns:
            dict: 包含expected_total_time和expected_complete_time的字典
        """
        from datetime import datetime, timezone, timedelta
        utc_plus_8 = timezone(timedelta(hours=8))
        now = datetime.now(utc_plus_8)
        
        self._log(level='DEBUG', content=f"开始计算任务 {task.id} 的时间预估，任务类型: {task.type}", task_id=str(task.id))
        
        # 计算预计总时长（秒）
        estimated_total_seconds = 0
        
        try:
            local_db_session = db.session()
            actual_total_cases = local_db_session.query(TaskCase).filter_by(task_id=task.id).count()
            self._log(level='DEBUG', content=f"任务 {task.id}: 总用例数={actual_total_cases}", task_id=str(task.id))
            
            if task.type == 'api':
                # API测试任务：优先基于历史用例执行时间
                from backend.models.models import Task as TaskModel
                # 查询最近完成的API测试任务
                recent_api_tasks = local_db_session.query(TaskModel).filter(
                    TaskModel.type == 'api',
                    TaskModel.status == 'completed',
                    TaskModel.total_cases > 0,
                    TaskModel.actual_duration > 0,
                    TaskModel.id != task.id
                ).order_by(TaskModel.completed_at.desc()).limit(3).all()
                
                self._log(level='DEBUG', content=f"任务 {task.id}: 找到 {len(recent_api_tasks)} 个历史API任务", task_id=str(task.id))
                
                # 计算历史用例的平均执行时间
                total_historical_case_time = 0
                total_historical_cases = 0
                
                for hist_task in recent_api_tasks:
                    # 查询该任务的所有用例执行时间
                    hist_task_cases = local_db_session.query(TaskCase).filter_by(
                        task_id=hist_task.id
                    ).all()
                    for tc in hist_task_cases:
                        if tc.duration and tc.duration > 0:
                            total_historical_case_time += tc.duration
                            total_historical_cases += 1
                
                self._log(level='DEBUG', content=f"任务 {task.id}: 历史用例数={total_historical_cases}, 总时间={total_historical_case_time}秒", task_id=str(task.id))
                
                # 如果有足够的历史数据，直接基于历史数据计算
                if total_historical_cases >= 5:
                    # 平均每个用例的执行时间
                    avg_case_execution_time = total_historical_case_time / total_historical_cases
                    # 总预估时间 = 平均用例执行时间 × 用例数
                    estimated_total_seconds = avg_case_execution_time * actual_total_cases
                    self._log(level='DEBUG', content=f"任务 {task.id}: 基于历史数据计算，平均执行时间={avg_case_execution_time:.2f}秒，总预估={estimated_total_seconds}秒", task_id=str(task.id))
                else:
                    # 基于API实际执行流程的时间消耗分析
                    avg_health_check_time = 2.0  # 健康检查 ~2秒/API
                    avg_task_creation_time = 1.0  # 创建任务 ~1秒/API
                    avg_status_polling_time = 0.5  # 状态轮询 ~0.5秒/次
                    avg_result_retrieval_time = 1.0  # 获取结果 ~1秒/API
                    avg_task_cleanup_time = 1.0  # 清理任务 ~1秒/API
                    
                    from backend.models.models import TaskAPI
                    api_count = local_db_session.query(TaskAPI).filter_by(task_id=task.id).count()
                    if api_count == 0:
                        api_count = 1
                    
                    # 计算实际音频总时长
                    estimated_api_processing = 0.0
                    task_case_records = local_db_session.query(TaskCase).filter_by(task_id=task.id).all()
                    for tc in task_case_records:
                        test_case = local_db_session.query(TestCase).filter_by(id=tc.test_case_id).first()
                        if test_case and test_case.config and 'audios' in test_case.config:
                            for audio_cfg in test_case.config.get('audios', []):
                                audio_id = audio_cfg.get('audio_id')
                                if audio_id:
                                    audio = local_db_session.query(Audio).filter_by(id=audio_id).first()
                                    if audio and audio.duration:
                                        estimated_api_processing += audio.duration
                    if estimated_api_processing == 0.0:
                        estimated_api_processing = 3.0 * actual_total_cases

                    # 计算总执行时间
                    total_api_calls = actual_total_cases * api_count
                    estimated_health_check = avg_health_check_time * api_count  # 每个API只检查一次
                    estimated_task_creation = avg_task_creation_time * total_api_calls
                    estimated_status_polling = avg_status_polling_time * total_api_calls * 2  # 每个任务轮询2次
                    estimated_result_retrieval = avg_result_retrieval_time * total_api_calls
                    estimated_task_cleanup = avg_task_cleanup_time * total_api_calls

                    # 总预估时间
                    estimated_total_seconds = (
                        estimated_health_check +
                        estimated_task_creation +
                        estimated_status_polling +
                        estimated_api_processing +
                        estimated_result_retrieval +
                        estimated_task_cleanup
                    )
                    
                    self._log(level='DEBUG', content=f"任务 {task.id}: 基于公式计算，API数={api_count}，总预估={estimated_total_seconds}秒", task_id=str(task.id))
            else:
                # E2E测试任务：优先基于历史用例执行时间
                from backend.models.models import Task as TaskModel
                # 查询最近完成的E2E测试任务
                recent_e2e_tasks = local_db_session.query(TaskModel).filter(
                    TaskModel.type == 'e2e',
                    TaskModel.status == 'completed',
                    TaskModel.total_cases > 0,
                    TaskModel.actual_duration > 0,
                    TaskModel.id != task.id
                ).order_by(TaskModel.completed_at.desc()).limit(3).all()
                
                # 计算历史用例的平均执行时间
                total_historical_case_time = 0
                total_historical_cases = 0
                
                for hist_task in recent_e2e_tasks:
                    # 查询该任务的所有用例执行时间
                    hist_task_cases = local_db_session.query(TaskCase).filter_by(
                        task_id=hist_task.id
                    ).all()
                    for tc in hist_task_cases:
                        if tc.duration and tc.duration > 0:
                            total_historical_case_time += tc.duration
                            total_historical_cases += 1
                
                # 如果有足够的历史数据，直接基于历史数据计算
                if total_historical_cases >= 5:
                    # 平均每个用例的执行时间
                    avg_case_execution_time = total_historical_case_time / total_historical_cases
                    # 总预估时间 = 平均用例执行时间 × 用例数
                    estimated_total_seconds = avg_case_execution_time * actual_total_cases
                else:
                    # 基于E2E实际执行流程的时间消耗分析
                    avg_device_preprocess_time = 10.0  # 设备预处理 ~1秒/设备
                    avg_prompt_audio_time = 20.0  # 提示音播放 ~2秒/设备
                    avg_background_noise_setup = 10.0  # 背景噪声设置 ~1秒
                    avg_device_postprocess_time = 10.0  # 设备后处理 ~1秒/设备
                    avg_system_overhead = 1.0  # 系统开销 ~1秒/用例

                    # 计算设备数量
                    from backend.models.models import TaskDevice
                    device_count = local_db_session.query(TaskDevice).filter_by(task_id=task.id).count()
                    if device_count == 0:
                        device_count = 1

                    # 计算实际音频总时长
                    estimated_total_audio = 0.0
                    task_case_records = local_db_session.query(TaskCase).filter_by(task_id=task.id).all()
                    for tc in task_case_records:
                        test_case = local_db_session.query(TestCase).filter_by(id=tc.test_case_id).first()
                        if test_case and test_case.config and 'audios' in test_case.config:
                            for audio_cfg in test_case.config.get('audios', []):
                                audio_id = audio_cfg.get('audio_id')
                                if audio_id:
                                    audio = local_db_session.query(Audio).filter_by(id=audio_id).first()
                                    if audio and audio.duration:
                                        estimated_total_audio += audio.duration
                    if estimated_total_audio == 0.0:
                        estimated_total_audio = 5.0 * actual_total_cases

                    estimated_device_preprocess = avg_device_preprocess_time * device_count  # 每个设备只预处理一次
                    estimated_prompt_audio = avg_prompt_audio_time * device_count  # 每个设备播放一次提示音
                    estimated_background_noise = avg_background_noise_setup  # 只设置一次背景噪声
                    estimated_device_operation = 3.0 * actual_total_cases * device_count  # 每个设备每个用例的操作时间
                    estimated_device_postprocess = avg_device_postprocess_time * device_count  # 每个设备只后处理一次
                    estimated_system_overhead = avg_system_overhead * actual_total_cases

                    # 总预估时间
                    estimated_total_seconds = (
                        estimated_total_audio +
                        estimated_device_preprocess +
                        estimated_prompt_audio +
                        estimated_background_noise +
                        estimated_device_operation +
                        estimated_device_postprocess +
                        estimated_system_overhead
                    )
            
            # 确保预估时间合理
            min_estimated_time = actual_total_cases * 2  # 每个用例至少2秒
            estimated_total_seconds = max(estimated_total_seconds, min_estimated_time)
            
            # 计算预计完成时间
            expected_complete_time = now + timedelta(seconds=estimated_total_seconds)
            
            return {
                "expected_total_time": int(estimated_total_seconds),
                "expected_complete_time": expected_complete_time.strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            # 发生异常时返回默认值
            return {
                "expected_total_time": 60,  # 默认1分钟
                "expected_complete_time": (now + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
            }
        finally:
            try:
                local_db_session.close()
            except:
                pass

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
                    socketio.emit('task_progress', progress_data)
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
            db_task = local_db_session.query(Task).get(task_id_int)
            if not db_task:
                self._log(level='WARNING', content=f"找不到任务，跳过进度更新，task_id={task_id}", task_id=task_id)
                return
            
            self._log(level='DEBUG', content=f"开始生成进度数据，task_id={task_id}, force={force}", task_id=task_id)
            
            current_tc = local_db_session.query(TaskCase).filter_by(task_id=db_task.id, execution_status='running').first()
            if current_tc:
                case_info = local_db_session.query(TestCase).get(current_tc.test_case_id)
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
                from backend.services.execution.execution_engine import execution_engine
                round_progress = execution_engine.round_progress_cache.get(tc.id)
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
                from backend.models.models import TaskAPI, API
                task_api = local_db_session.query(TaskAPI).filter_by(task_id=db_task.id).first()
                if task_api:
                    api = local_db_session.query(API).get(task_api.api_id)
                    if api:
                        from backend.services.execution.execution_engine import execution_engine
                        api_executor = getattr(execution_engine, 'api_executors', {}).get(str(db_task.id))
                        if api_executor:
                            from backend.utils.clients.load_balancer import LoadBalancer
                            load_balancer = getattr(execution_engine, 'load_balancer', None)
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
                elapsed_seconds_for_display = max(0.0, (now - started_at).total_seconds())
            
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

            if db_task.started_at:
                started_at = db_task.started_at
                if not started_at.tzinfo:
                    started_at = started_at.replace(tzinfo=timezone(timedelta(hours=8)))

                elapsed_seconds = max(0.0, (now - started_at).total_seconds())

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
                socketio.emit('task_progress', progress_data)
                self._log(level='DEBUG', content=f"成功发送 task_progress 事件，task_id={task_id}, progress={progress_data.get('totalProgress', 0)}%", task_id=task_id)
            except Exception as emit_error:
                self._log(level='ERROR', content=f"发送 task_progress 事件失败: {str(emit_error)}", task_id=task_id)
                raise
        except Exception as e:
            self._log(level='ERROR', content=f"emit_progress 异常: {str(e)}", task_id=task_id, category='error')
            raise
        finally:
            local_db_session.close()
    
    def emit_alert(self, task_id, message, level='error'):
        try:
            utc_plus_8 = timezone(timedelta(hours=8))
            alert_data = {
                "task_id": task_id,
                "message": message,
                "level": level,
                "time": datetime.now(utc_plus_8).isoformat()
            }
            socketio.emit('error_alert', alert_data)
        except Exception:
            pass
