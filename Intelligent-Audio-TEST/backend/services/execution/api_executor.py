# -*- coding: utf-8 -*-
"""API 执行器 — 编排层，持有并发管理器、任务执行器、结果处理器、会话执行器"""
import time
import json
import os
from datetime import datetime, timezone, timedelta

from backend.models.models import TaskAPI, Audio, TestCase, TaskCase, Task, API
from backend.models.database import db
from backend.utils.algorithm.field_mapper import get_field_mapper
from backend.utils.algorithm.reference_params_generator import ReferenceParamsGenerator
from backend.services.execution.base_executor import BaseExecutor
from backend.services.execution.api_concurrency_manager import APIConcurrencyManager
from backend.services.execution.api_task_runner import APITaskRunner
from backend.services.execution.api_result_processor import APIResultProcessor
from backend.services.execution.api_session_executor import APISessionExecutor


class APIExecutor(BaseExecutor):
    def __init__(self, execution_engine):
        super().__init__(execution_engine)
        self._concurrency = APIConcurrencyManager(self)
        self._task_runner = APITaskRunner(self)
        self._result_processor = APIResultProcessor(self)
        self._session_executor = APISessionExecutor(self)

    # ── 并发控制委托 ──
    @property
    def api_semaphores(self):
        return self._concurrency.api_semaphores

    @property
    def api_waiting_counts(self):
        return self._concurrency.api_waiting_counts

    def _get_task_lock(self, task_id):
        return self._concurrency.get_task_lock(task_id)

    def _cleanup_task_lock(self, task_id):
        self._concurrency.cleanup_task_lock(task_id)

    def mark_task_completed(self, task_id):
        self._concurrency.mark_task_completed(task_id)

    def cleanup_completed_tasks(self):
        self._concurrency.cleanup_completed_tasks()

    def acquire_api_execution_right(self, api_id, task_id, current_test_case_id, max_process=5, timeout=None):
        return self._concurrency.acquire(api_id, task_id, current_test_case_id, max_process, timeout)

    def release_api_execution_right(self, api_id, task_id):
        self._concurrency.release(api_id, task_id)

    # ── 入口方法 ──
    def execute_api_case(self, app, task_id, tc_rel_id):
        """执行 API 测试用例"""
        try:
            with app.app_context():
                self._log(level='DEBUG', content=f"开始执行测试用例: {tc_rel_id}", task_id=task_id)
                self._handle_control(task_id)

                if not self._claim_tc_rel_running(task_id, tc_rel_id):
                    return True

                task_lock = self._get_task_lock(task_id)
                with task_lock:
                    validate_result, data = self._validate_and_get_data(app, task_id, tc_rel_id)
                    if not validate_result:
                        self._handle_validation_failure(task_id, tc_rel_id, data)
                        return False

                    return self._execute_single_or_multi(app, task_id, tc_rel_id, data)

        except Exception as e:
            import traceback
            self._log(level='ERROR', category='execution',
                      content=f"API 用例执行失败: {str(e)}\n{traceback.format_exc()}",
                      task_id=task_id if 'task_id' in locals() else None)
            return False
        finally:
            try:
                self._thread_ctx.current_test_case_id = None
            except Exception:
                pass

    def _claim_tc_rel_running(self, task_id, tc_rel_id):
        """抢占 TaskCase 状态为 running，避免重复执行"""
        local_db_session = db.session()
        try:
            claimed = local_db_session.query(TaskCase).filter(
                TaskCase.id == tc_rel_id,
                TaskCase.task_id == task_id,
                TaskCase.execution_status.in_(['pending', 'queued'])
            ).update({TaskCase.execution_status: 'running'}, synchronize_session=False)
            if claimed != 1:
                local_db_session.rollback()
                self._log(level='DEBUG',
                          content=f"测试用例 {tc_rel_id} 已在执行或已完成，跳过",
                          task_id=task_id)
                return False
            local_db_session.commit()
            self.execution_engine._emit_progress(task_id, force=True)
            return True
        except Exception as e:
            self._log(level='WARNING', content=f"更新测试用例状态失败: {str(e)}", task_id=task_id)
            return False
        finally:
            local_db_session.close()

    def _handle_validation_failure(self, task_id, tc_rel_id, data):
        """验证失败时更新 TaskCase 统计信息"""
        local_db_session = db.session()
        try:
            task = local_db_session.query(Task).get(task_id)
            if task:
                success_count = local_db_session.query(TaskCase).filter(
                    TaskCase.task_id == task_id, TaskCase.status == 'completed'
                ).count()
                failed_count = local_db_session.query(TaskCase).filter_by(
                    task_id=task_id, status='failed'
                ).count()
                task.completed_cases = success_count
                task.failed_cases = failed_count
                local_db_session.commit()
                self.execution_engine._emit_progress(task, force=True)
        finally:
            local_db_session.close()

    def _execute_single_or_multi(self, app, task_id, tc_rel_id, data):
        """根据是否配置 rounds 分发到多轮会话或线性流程"""
        test_case_id = data['test_case_id']
        case_name = data['case_name']
        algorithm_type = data.get('algorithm_type', 'translation')
        case_algorithm_params = data.get('case_algorithm_params')

        case_config = self._load_case_config(test_case_id)

        rounds = case_config.get('rounds', [])
        if rounds and len(rounds) > 1:
            self._log(level='INFO',
                      content=f"用例 {case_name} 配置了 {len(rounds)} 轮，进入多轮会话模式",
                      task_id=task_id, test_case_id=test_case_id)
            return self._session_executor.execute(app, task_id, tc_rel_id, data, case_config)

        return self._execute_linear(task_id, tc_rel_id, data, case_config, algorithm_type, case_algorithm_params)

    def _execute_linear(self, task_id, tc_rel_id, data, case_config, algorithm_type, case_algorithm_params):
        """线性流程：遍历所有 API 配置，逐个执行"""
        test_case_id = data['test_case_id']
        case_name = data['case_name']
        api_configs = data['api_configs']
        audio = data['audio']
        api_specific_config = data['api_specific_config']
        current_app = data['current_app']
        total_audio_duration = data['total_audio_duration']

        local_db_session = db.session()
        try:
            tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
            if not tc_rel:
                self._log(level='ERROR', content=f"找不到 TaskCase: {tc_rel_id}", task_id=task_id)
                return False

            if tc_rel.execution_status in ['pending', 'queued']:
                utc_plus_8 = timezone(timedelta(hours=8))
                tc_rel.execution_status = 'running'
                if not tc_rel.started_at:
                    tc_rel.started_at = datetime.now(utc_plus_8)
                local_db_session.commit()
                self.execution_engine._emit_progress(task_id, force=True)

            for api_config in api_configs:
                self._handle_control(task_id)
                api_id = api_config.id

                max_process = getattr(api_config, 'default_max_process', 5) or 5
                if not self._concurrency.acquire(api_id, task_id, tc_rel_id, max_process=max_process):
                    self._log(level='ERROR', content=f"API {api_id} 执行权获取失败，跳过",
                              task_id=task_id, api_id=api_id)
                    continue

                try:
                    self._run_single_api(
                        task_id, tc_rel_id, test_case_id, case_name, algorithm_type,
                        api_config, api_specific_config, audio, current_app,
                        total_audio_duration, case_config, case_algorithm_params,
                        local_db_session, tc_rel
                    )
                except Exception as e:
                    import traceback
                    self._log(level='ERROR', category='execution',
                              content=f"API {api_config.id} 用例 {case_name} 执行失败: {str(e)}\n{traceback.format_exc()}",
                              task_id=task_id, api_id=api_config.id)
                    if tc_rel and tc_rel.execution_status not in ['stopped']:
                        tc_rel.execution_status = 'failed'
                    if tc_rel and tc_rel.evaluation_status in ['queued', 'pending']:
                        tc_rel.evaluation_status = 'completed'
                        tc_rel.status = 'failed'
                    local_db_session.commit()
                finally:
                    self._concurrency.release(api_id, task_id)
        finally:
            local_db_session.close()

        return True

    def _run_single_api(self, task_id, tc_rel_id, test_case_id, case_name, algorithm_type,
                        api_config, api_specific_config, audio, current_app,
                        total_audio_duration, case_config, case_algorithm_params,
                        local_db_session, tc_rel):
        """执行单个 API 的完整流程：健康检查 -> 创建任务 -> 等待 -> 结果 -> 评估"""
        api_paths, select_base_url, release_base_url = self._task_runner.setup_endpoints(
            task_id, tc_rel_id, case_name, api_config, current_app
        )
        if not api_paths:
            return

        self._task_runner.health_check(
            task_id, case_name, audio, api_config, api_specific_config,
            api_paths, select_base_url, release_base_url
        )

        api_task_id = self._task_runner.create_task(
            task_id, audio, api_config, api_specific_config,
            api_paths, select_base_url, release_base_url, algorithm_type
        )

        try:
            start_wait_time, task_success, task_error_msg = self._task_runner.wait_for_completion(
                task_id, api_task_id, api_config, api_specific_config,
                api_paths, select_base_url, release_base_url, current_app, total_audio_duration
            )

            if not task_success:
                success = False
                error_msg = task_error_msg
                algo_result_dict = {}
                latency = 0
                final_result_result = {}
                self._log(level='ERROR',
                          content=f"API {api_config.id} 用例 {case_name} 执行失败，错误: {error_msg}",
                          task_id=task_id, api_id=api_config.id)
            else:
                final_result_result = self._task_runner.get_final_result(
                    task_id, api_task_id, api_config, api_specific_config,
                    api_paths, select_base_url, release_base_url
                )
                self._task_runner.get_frame_results(
                    task_id, api_task_id, api_config, api_specific_config,
                    api_paths, select_base_url, release_base_url
                )
                algo_result_dict, latency = self._task_runner.extract_final_result(
                    task_id, final_result_result, algorithm_type
                )
                success = True
                error_msg = None
                self._log(level='INFO',
                          content=f"API {api_config.id} 用例 {case_name} 执行成功，API耗时: {latency}ms",
                          task_id=task_id, api_id=api_config.id)

            result_id = self._result_processor.create_test_result(
                task_id, test_case_id, api_config.id, success, error_msg,
                algo_result_dict, latency, final_result_result, algorithm_type
            )
        finally:
            if api_task_id:
                self._task_runner.delete_task(
                    task_id, api_task_id, api_config, api_specific_config,
                    api_paths, select_base_url, release_base_url
                )

        if success and result_id:
            self._evaluate_result(
                task_id=task_id, result_id=result_id, test_case_id=test_case_id,
                algo_result=algo_result_dict, case_config=case_config,
                algorithm_type=algorithm_type, test_type='api',
                case_algorithm_params=case_algorithm_params
            )
            self._log(level='INFO', category='evaluation',
                      content=f"API {api_config.id} 用例 {case_name} 采集完成，已提交评估队列",
                      task_id=task_id, api_id=api_config.id)

        self._log_single_api_result(task_id, case_name, success, algo_result_dict,
                                     case_config, case_algorithm_params,
                                     algorithm_type, test_case_id, api_config.id)

    def _log_single_api_result(self, task_id, case_name, success, algo_result_dict,
                                case_config, case_algorithm_params,
                                algorithm_type, test_case_id, api_config_id):
        """记录单个 API 结果日志"""
        ref_fields = {}
        if case_config:
            for key, value in case_config.items():
                if value is not None:
                    ref_fields[key] = value
        if case_algorithm_params and isinstance(case_algorithm_params, dict):
            for key, value in case_algorithm_params.items():
                if value is not None:
                    ref_fields[key] = value

        from backend.utils.algorithm.case_parameter_extractor import CaseParameterExtractor
        full_case_params = {
            'algorithm_params': case_algorithm_params or {},
            'reference_params': case_config.get('reference_params', {}) if case_config else {},
            'algorithm_type': algorithm_type
        }
        eval_params = CaseParameterExtractor.get_evaluation_params(
            case_config=full_case_params,
            algorithm_result=algo_result_dict if algo_result_dict else {},
            test_type='api'
        )
        for key, value in eval_params.items():
            if value is not None and key not in ref_fields:
                ref_fields[key] = value.get('text', '') if isinstance(value, dict) else value

        result_obj = {
            'device_id': None,
            'api_id': api_config_id,
            'success': success,
            'raw_results': {'success': success}
        }
        if algo_result_dict:
            for key, value in algo_result_dict.items():
                result_obj[key] = value

        self._log_case_result(task_id, case_name, result_obj, ref_fields,
                              algorithm_type=algorithm_type, test_case_id=test_case_id)

    def _load_case_config(self, test_case_id):
        """加载用例配置，注入 algorithm_params 和 reference_params"""
        local_db_session = db.session()
        try:
            case_obj = local_db_session.query(TestCase).get(test_case_id)
            if not case_obj:
                return {}
            case_config = case_obj.config or {}
            rounds = case_config.get('rounds', [])
            if rounds and isinstance(rounds[0], dict):
                first_round = rounds[0]
                ap_dict = first_round.get('algorithm_params', {})
                if ap_dict and isinstance(ap_dict, dict):
                    case_config = case_config.copy()
                    case_config['algorithm_params'] = ap_dict
                ref_path = first_round.get('reference_params_path')
                if ref_path:
                    ref_data = ReferenceParamsGenerator.load_from_file(ref_path)
                    if ref_data:
                        case_config['reference_params'] = ref_data
            return case_config
        finally:
            local_db_session.close()

    def _validate_and_get_data(self, app, task_id, tc_rel_id):
        """验证并获取执行数据"""
        if app is None:
            raise ValueError("app参数不能为空")

        self._handle_control(task_id)

        from flask import current_app

        local_db_session = db.session()
        try:
            tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
            if not tc_rel:
                raise ValueError(f"找不到测试用例关联记录，ID: {tc_rel_id}")

            task = local_db_session.query(Task).get(task_id)
            if not task:
                raise ValueError(f"找不到任务，ID: {task_id}")

            case = local_db_session.query(TestCase).get(tc_rel.test_case_id)
            if not case:
                raise ValueError(f"找不到测试用例，ID: {tc_rel.test_case_id}")

            self.current_test_case_id = case.id
            self._thread_ctx.current_test_case_id = case.id
            self._log('INFO', f"开始执行API用例: {case.name}", task_id)

            api_configs = self._get_api_configs(local_db_session, task_id)
            processed_api_configs = self._process_api_configs(api_configs)

            tc_rel_id_local = tc_rel.id
            tc_rel_test_case_id = tc_rel.test_case_id
            test_case_id = case.id
            case_name = case.name
            task_type = task.type if task else 'api'
            case_config = case.config or {}
            algorithm_type = self._get_algorithm_type(case, case_config)
        finally:
            local_db_session.close()

        if not processed_api_configs:
            error_msg = "找不到API配置"
            self._fail_tc_rel(tc_rel_id_local, error_msg)
            self._log('ERROR', f"API 用例 {case_name} 执行失败: {error_msg}", task_id)
            return False, None

        audio_data, total_audio_duration, error_msg = self._get_audio_data(
            tc_rel_test_case_id, task_type, case_name, task_id, tc_rel_id_local
        )
        if error_msg:
            return False, None

        local_db_session = db.session()
        try:
            case_obj = local_db_session.query(TestCase).get(tc_rel_test_case_id)
            case_config = case_obj.config or {} if case_obj else {}

            algorithm_params = {}
            rounds = case_config.get('rounds', [])
            if rounds and isinstance(rounds[0], dict):
                ap_dict = rounds[0].get('algorithm_params', {})
                if ap_dict and isinstance(ap_dict, dict):
                    algorithm_params = ap_dict

            api_specific_config = case_config.get('api', {})
            task_obj = local_db_session.query(Task).get(task_id)
            if task_obj and not api_specific_config and task_obj.type == 'api':
                api_specific_config = case_config

            return True, {
                'tc_rel_id': tc_rel_id_local,
                'task_id': task_id,
                'test_case_id': test_case_id,
                'case_name': case_name,
                'algorithm_type': algorithm_type,
                'api_configs': processed_api_configs,
                'audio': audio_data,
                'api_specific_config': api_specific_config,
                'current_app': current_app,
                'total_audio_duration': total_audio_duration,
                'case_algorithm_params': algorithm_params
            }
        finally:
            local_db_session.close()

    def _get_api_configs(self, local_db_session, task_id):
        """获取任务关联的所有 API 配置"""
        task_apis = local_db_session.query(TaskAPI).filter_by(task_id=task_id).all()
        if not task_apis:
            return []
        api_ids = [task_api.api_id for task_api in task_apis]
        return local_db_session.query(API).filter(API.id.in_(api_ids)).all()

    def _process_api_configs(self, api_configs):
        """将 API 配置转换为本地对象列表，避免分离对象问题"""
        processed = []
        for api_config in api_configs:
            class MockAPIConfig:
                def __init__(self, id, endpoint, api_endpoints, default_max_process, meta, max_timeout, vendor):
                    self.id = id
                    self.endpoint = endpoint
                    self.api_endpoints = api_endpoints
                    self.default_max_process = default_max_process
                    self.meta = meta
                    self.max_timeout = max_timeout
                    self.vendor = vendor

            processed.append(MockAPIConfig(
                id=api_config.id,
                endpoint=api_config.api_url,
                api_endpoints=api_config.api_endpoints or [],
                default_max_process=api_config.default_max_process or 5,
                meta=api_config.meta or {},
                max_timeout=api_config.max_timeout or 30,
                vendor=api_config.vendor or None
            ))
        return processed

    def _get_algorithm_type(self, case, case_config):
        """提取 algorithm_type"""
        algorithm_type = case.algorithm_type if hasattr(case, 'algorithm_type') and case.algorithm_type else None
        if not algorithm_type:
            algorithm_type = case_config.get('algorithm_type')
        if not algorithm_type:
            algorithm_type = 'translation'
        return algorithm_type

    def _get_audio_data(self, test_case_id, task_type, case_name, task_id, tc_rel_id):
        """获取音频数据，返回 (audio_data, total_duration, error_msg)"""
        local_db_session = db.session()
        try:
            case = local_db_session.query(TestCase).get(test_case_id)
            if not case:
                error_msg = "找不到测试用例"
                self._log('ERROR', f"API 用例执行失败: {error_msg}", task_id)
                self._fail_tc_rel(tc_rel_id, error_msg)
                return None, 0, error_msg

            config = case.config or {}
            audios = config.get('audios', [])
            if not audios:
                rounds = config.get('rounds', [])
                for round_item in rounds:
                    if isinstance(round_item, dict):
                        round_audios = round_item.get('audios', [])
                        if isinstance(round_audios, list):
                            audios.extend(round_audios)

            target_audios = [a for a in audios if a.get('audio_id')]
            expected_test_type = 'API' if task_type == 'api' else 'E2E'

            if not target_audios:
                error_msg = f"测试用例未配置有效的 {expected_test_type} 测试音频"
                self._log('ERROR', f"{expected_test_type} 用例 {case_name} 执行失败: {error_msg}", task_id)
                self._fail_tc_rel(tc_rel_id, error_msg)
                return None, 0, error_msg

            total_audio_duration = 0.0
            for audio_config in target_audios:
                audio_id = audio_config.get('audio_id')
                if audio_id:
                    audio_obj = local_db_session.query(Audio).get(audio_id)
                    if audio_obj:
                        total_audio_duration += audio_obj.duration

            audio_config = target_audios[0]
            audio_id = audio_config.get('audio_id')
            audio = local_db_session.query(Audio).get(audio_id) if audio_id else None

            if not audio:
                error_msg = f"找不到ID为 {audio_id} 的音频文件"
                self._log('ERROR', f"{expected_test_type} 用例 {case_name} 执行失败: {error_msg}", task_id)
                self._fail_tc_rel(tc_rel_id, error_msg)
                return None, 0, error_msg

            audio_data = {
                'id': audio.id,
                'name': audio.name,
                'asr_text': audio.asr_text or "",
                'file_path': audio.file_path
            }
            self._log('DEBUG', f"API用例音频总时长: {total_audio_duration}秒", task_id)
            return audio_data, total_audio_duration, None
        finally:
            local_db_session.close()

    def _fail_tc_rel(self, tc_rel_id, error_msg):
        """将 TaskCase 标记为失败"""
        utc_plus_8 = timezone(timedelta(hours=8))
        local_db_session = db.session()
        try:
            tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
            if tc_rel:
                tc_rel.status = 'failed'
                tc_rel.execution_status = 'failed'
                tc_rel.started_at = datetime.now(utc_plus_8)
                tc_rel.completed_at = datetime.now(utc_plus_8)
                tc_rel.error_message = error_msg
                local_db_session.commit()
        finally:
            local_db_session.close()
