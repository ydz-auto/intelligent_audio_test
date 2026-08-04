from datetime import datetime, timezone, timedelta
from shared.models.models import TaskCase, TestCase, Audio
from shared.models.database import db


class TimeEstimateMixin:
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
                from shared.models.models import Task as TaskModel
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

                    from shared.models.models import TaskAPI
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
                from shared.models.models import Task as TaskModel
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
                    from shared.models.models import TaskDevice
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
