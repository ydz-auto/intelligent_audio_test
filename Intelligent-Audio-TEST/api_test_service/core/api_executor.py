# -*- coding: utf-8 -*-
"""API 执行器 — 编排层，持有并发管理器、任务执行器、结果处理器、会话执行器"""
import logging

from shared.utils.dto_utils import dto_to_dict
from shared.utils.status_constants import ExecutionStatus, EvaluationStatus, TaskCaseStatus
from shared.models.database import get_db_session
from shared.infrastructure.base_executor import BaseExecutor
from api_test_service.infrastructure.acl import (
    TaskDataAclRepositoryImpl,
    TestCaseConfigAclRepositoryImpl,
    AudioConfigAclRepositoryImpl,
    AlgorithmQueryAclRepositoryImpl,
    DeviceResultAclRepositoryImpl,
)
from api_test_service.infrastructure.persistence.models import API
from api_test_service.core.api_concurrency_manager import APIConcurrencyManager
from api_test_service.core.api_task_runner import APITaskRunner
from api_test_service.core.api_result_processor import APIResultProcessor
from api_test_service.core.api_session_executor import APISessionExecutor
from shared.utils.config_manager import config_manager

logger = logging.getLogger(__name__)

# 跨服务出站 gRPC 经 ACL 仓储（返回 DTO），不返回 raw dict
_task_data_acl = TaskDataAclRepositoryImpl()
_testcase_acl = TestCaseConfigAclRepositoryImpl()
_audio_acl = AudioConfigAclRepositoryImpl()
_algo_acl = AlgorithmQueryAclRepositoryImpl()


class APIExecutor(BaseExecutor):
    def __init__(self, execution_engine):
        super().__init__(execution_engine)
        self._concurrency = APIConcurrencyManager(self)
        self._task_runner = APITaskRunner(self)
        self._result_processor = APIResultProcessor(self)
        self._session_executor = APISessionExecutor(self)

    def _get_result_mapper(self):
        """返回 DeviceResult ACL 仓储，供 ResultsMixin 使用"""
        return DeviceResultAclRepositoryImpl()

    def _get_algorithm_acl(self):
        """返回 algorithm_service ACL 仓储，供 DbMixin 使用"""
        return _algo_acl

    def _get_task_data_acl(self):
        """返回 task_service ACL 仓储，供 DbMixin 使用"""
        return _task_data_acl

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
        return self._concurrency.cleanup_task_lock(task_id)

    def mark_task_completed(self, task_id):
        self._concurrency.mark_task_completed(task_id)

    def cleanup_completed_tasks(self):
        self._concurrency.cleanup_completed_tasks()

    def acquire_api_execution_right(self, api_id, task_id, current_test_case_id, max_process=None, timeout=None):
        # 并发参数配置化：max_process 缺省时从 config_manager 取默认值
        if max_process is None:
            max_process = config_manager.get_value('api_executor', 'default_max_process', 5)
        return self._concurrency.acquire(api_id, task_id, current_test_case_id, max_process, timeout)

    def release_api_execution_right(self, api_id, task_id):
        return self._concurrency.release(api_id, task_id)

    # ── 入口方法 ──
    def execute_api_case(self, task_id, tc_rel_id):
        """执行 API 测试用例"""
        try:
            self._log(level='DEBUG', content=f"开始执行测试用例: {tc_rel_id}", task_id=task_id)
            self._handle_control(task_id)

            if not self._claim_tc_rel_running(task_id, tc_rel_id):
                return True

            task_lock = self._get_task_lock(task_id)
            with task_lock:
                validate_result, data = self._validate_and_get_data(task_id, tc_rel_id)
                if not validate_result:
                    self._handle_validation_failure(task_id, tc_rel_id, data)
                    return False

                return self._execute_single_or_multi(task_id, tc_rel_id, data)

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
                logger.debug("清理 current_test_case_id 失败", exc_info=True)

    def _claim_tc_rel_running(self, task_id, tc_rel_id):
        """抢占 TaskCase 状态为 running，避免重复执行

        通过 ACL 仓储查询 TaskCase，检查 execution_status 是否为 pending/queued，
        若是则通过 update_task_case_status 更新为 running。
        """
        try:
            tcs = [dto_to_dict(d) for d in _task_data_acl.get_task_case_by_ids(task_id)]
            tc_rel = next((tc for tc in tcs if tc.get('id') == tc_rel_id), None)
            if not tc_rel:
                self._log(level='DEBUG',
                          content=f"测试用例 {tc_rel_id} 不存在，跳过",
                          task_id=task_id)
                return False
            if tc_rel.get('execution_status') not in [ExecutionStatus.PENDING, ExecutionStatus.QUEUED]:
                self._log(level='DEBUG',
                          content=f"测试用例 {tc_rel_id} 已在执行或已完成，跳过",
                          task_id=task_id)
                return False

            test_case_id = tc_rel.get('test_case_id')
            if not test_case_id:
                self._log(level='WARNING', content=f"TaskCase {tc_rel_id} 无 test_case_id", task_id=task_id)
                return False

            _task_data_acl.update_task_case_status(
                task_id=task_id,
                case_id=str(test_case_id),
                execution_status=ExecutionStatus.RUNNING,
            )
            self.execution_engine._emit_progress(task_id, force=True)
            return True
        except Exception as e:
            self._log(level='WARNING', content=f"更新测试用例状态失败: {str(e)}", task_id=task_id)
            return False

    def _handle_validation_failure(self, task_id, tc_rel_id, data):
        """验证失败时更新 TaskCase 统计信息

        通过 ACL 仓储查询 TaskCase 统计 completed/failed 数量，
        然后触发进度更新（计数刷新由 task_service 端负责）。
        """
        try:
            tcs = [dto_to_dict(d) for d in _task_data_acl.get_task_case_by_ids(task_id)]
            completed = sum(1 for tc in tcs if tc.get('status') == TaskCaseStatus.COMPLETED)
            failed = sum(1 for tc in tcs if tc.get('status') == TaskCaseStatus.FAILED)
            self._log(level='DEBUG',
                      content=f"任务 {task_id} 统计: completed={completed}, failed={failed}",
                      task_id=task_id)
        except Exception as e:
            self._log(level='WARNING', content=f"查询任务统计失败: {str(e)}", task_id=task_id)
        finally:
            self.execution_engine._emit_progress(task_id, force=True)

    def _execute_single_or_multi(self, task_id, tc_rel_id, data):
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
            return self._session_executor.execute(task_id, tc_rel_id, data, case_config)

        return self._execute_linear(task_id, tc_rel_id, data, case_config, algorithm_type, case_algorithm_params)

    def _execute_linear(self, task_id, tc_rel_id, data, case_config, algorithm_type, case_algorithm_params):
        """线性流程：遍历所有 API 配置，逐个执行"""
        test_case_id = data['test_case_id']
        case_name = data['case_name']
        api_configs = data['api_configs']
        audio = data['audio']
        api_specific_config = data['api_specific_config']
        total_audio_duration = data['total_audio_duration']

        # 通过 ACL 仓储查询 TaskCase 状态
        tc_rel = None
        try:
            tcs = [dto_to_dict(d) for d in _task_data_acl.get_task_case_by_ids(task_id)]
            tc_rel = next((tc for tc in tcs if tc.get('id') == tc_rel_id), None)
            if not tc_rel:
                self._log(level='ERROR', content=f"找不到 TaskCase: {tc_rel_id}", task_id=task_id)
                return False

            if tc_rel.get('execution_status') in [ExecutionStatus.PENDING, ExecutionStatus.QUEUED]:
                _task_data_acl.update_task_case_status(
                    task_id=task_id,
                    case_id=str(tc_rel.get('test_case_id', test_case_id)),
                    execution_status=ExecutionStatus.RUNNING,
                )
                self.execution_engine._emit_progress(task_id, force=True)
        except Exception as e:
            self._log(level='WARNING', content=f"查询/更新 TaskCase 状态失败: {e}", task_id=task_id)

        for api_config in api_configs:
            self._handle_control(task_id)
            api_id = api_config.id

            # 并发参数配置化：api_config 未配置时回退到 config_manager 默认值
            max_process = getattr(api_config, 'default_max_process', None) or config_manager.get_value('api_executor', 'default_max_process', 5)
            if not self._concurrency.acquire(api_id, task_id, tc_rel_id, max_process=max_process):
                self._log(level='ERROR', content=f"API {api_id} 执行权获取失败，跳过",
                          task_id=task_id, api_id=api_id)
                continue

            try:
                self._run_single_api(
                    task_id, tc_rel_id, test_case_id, case_name, algorithm_type,
                    api_config, api_specific_config, audio,
                    total_audio_duration, case_config, case_algorithm_params
                )
            except Exception as e:
                import traceback
                self._log(level='ERROR', category='execution',
                          content=f"API {api_config.id} 用例 {case_name} 执行失败: {str(e)}\n{traceback.format_exc()}",
                          task_id=task_id, api_id=api_config.id)
                # 通过 ACL 仓储更新 TaskCase 为失败状态
                try:
                    tc_status = tc_rel.get('execution_status') if tc_rel else None
                    if tc_status and tc_status not in [ExecutionStatus.STOPPED]:
                        _task_data_acl.update_task_case_status(
                            task_id=task_id,
                            case_id=str(tc_rel.get('test_case_id', test_case_id)),
                            execution_status=ExecutionStatus.FAILED,
                        )
                    eval_status = tc_rel.get('evaluation_status') if tc_rel else None
                    if eval_status and eval_status in [EvaluationStatus.QUEUED, EvaluationStatus.PENDING]:
                        _task_data_acl.update_task_case_status(
                            task_id=task_id,
                            case_id=str(tc_rel.get('test_case_id', test_case_id)),
                            status=TaskCaseStatus.FAILED,
                            evaluation_status=EvaluationStatus.COMPLETED,
                        )
                except Exception as ue:
                    self._log(level='WARNING', content=f"更新 TaskCase 失败状态失败: {ue}", task_id=task_id)
            finally:
                self._concurrency.release(api_id, task_id)

        return True

    def _run_single_api(self, task_id, tc_rel_id, test_case_id, case_name, algorithm_type,
                        api_config, api_specific_config, audio,
                        total_audio_duration, case_config, case_algorithm_params):
        """执行单个 API 的完整流程：健康检查 -> 创建任务 -> 等待 -> 结果 -> 评估"""
        api_paths, select_base_url, release_base_url = self._task_runner.setup_endpoints(
            task_id, tc_rel_id, case_name, api_config
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
                api_paths, select_base_url, release_base_url, total_audio_duration
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

        full_case_params = {
            'algorithm_params': case_algorithm_params or {},
            'reference_params': case_config.get('reference_params', {}) if case_config else {},
            'algorithm_type': algorithm_type
        }
        all_params = dto_to_dict(_algo_acl.extract_case_all_params(full_case_params)) or {}
        eval_params = all_params.get('evaluation', {}) if isinstance(all_params, dict) else {}
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
        try:
            case_data = dto_to_dict(_testcase_acl.get_test_case_detail(test_case_id)) or {}
            if not case_data:
                return {}
            case_config = case_data.get('config', {}) or {}
            rounds = case_config.get('rounds', [])
            if rounds and isinstance(rounds[0], dict):
                first_round = rounds[0]
                ap_dict = first_round.get('algorithm_params', {})
                if ap_dict and isinstance(ap_dict, dict):
                    case_config = case_config.copy()
                    case_config['algorithm_params'] = ap_dict
                ref_path = first_round.get('reference_params_path')
                if ref_path:
                    ref_data = _algo_acl.load_reference_params_file(ref_path)
                    if ref_data:
                        case_config['reference_params'] = ref_data
            return case_config
        except Exception as e:
            self._log(level='WARNING', content=f"加载用例配置失败: {e}", test_case_id=test_case_id)
            return {}

    def _validate_and_get_data(self, task_id, tc_rel_id):
        """验证并获取执行数据"""
        self._handle_control(task_id)

        # 通过 ACL 仓储查询 TaskCase
        tc_rel = None
        try:
            tcs = [dto_to_dict(d) for d in _task_data_acl.get_task_case_by_ids(task_id)]
            tc_rel = next((tc for tc in tcs if tc.get('id') == tc_rel_id), None)
        except Exception as e:
            self._log(level='WARNING', content=f"查询 TaskCase 失败: {e}", task_id=task_id)
        if not tc_rel:
            raise ValueError(f"找不到测试用例关联记录，ID: {tc_rel_id}")

        # 通过 ACL 仓储查询 Task
        task = None
        try:
            task = dto_to_dict(_task_data_acl.get_task_by_id(task_id)) or {}
        except Exception as e:
            self._log(level='WARNING', content=f"查询 Task 失败: {e}", task_id=task_id)
        if not task:
            raise ValueError(f"找不到任务，ID: {task_id}")

        # 通过 ACL 仓储查询 TestCase 详情
        tc_rel_test_case_id = tc_rel.get('test_case_id')
        case = None
        try:
            case = dto_to_dict(_testcase_acl.get_test_case_detail(tc_rel_test_case_id)) or {}
        except Exception as e:
            self._log(level='WARNING', content=f"查询 TestCase 失败: {e}", task_id=task_id)
        if not case:
            raise ValueError(f"找不到测试用例，ID: {tc_rel_test_case_id}")

        self.current_test_case_id = case.get('id')
        self._thread_ctx.current_test_case_id = case.get('id')
        self._log('INFO', f"开始执行API用例: {case.get('name')}", task_id)

        api_configs = self._get_api_configs(task_id)
        processed_api_configs = self._process_api_configs(api_configs)

        tc_rel_id_local = tc_rel.get('id')
        test_case_id = case.get('id')
        case_name = case.get('name')
        task_type = task.get('type') if task else 'api'
        case_config = case.get('config', {}) or {}
        algorithm_type = self._get_algorithm_type(case, case_config)

        if not processed_api_configs:
            error_msg = "找不到API配置"
            self._fail_tc_rel(tc_rel_id_local, error_msg, task_id=task_id)
            self._log('ERROR', f"API 用例 {case_name} 执行失败: {error_msg}", task_id)
            return False, None

        audio_data, total_audio_duration, error_msg = self._get_audio_data(
            tc_rel_test_case_id, task_type, case_name, task_id, tc_rel_id_local
        )
        if error_msg:
            return False, None

        # 重新加载 case_config 以获取 algorithm_params
        case_config2 = case_config
        algorithm_params = {}
        rounds = case_config2.get('rounds', [])
        if rounds and isinstance(rounds[0], dict):
            ap_dict = rounds[0].get('algorithm_params', {})
            if ap_dict and isinstance(ap_dict, dict):
                algorithm_params = ap_dict

        api_specific_config = case_config2.get('api', {})
        task_type_val = task.get('type') if task else 'api'
        if not api_specific_config and task_type_val == 'api':
            api_specific_config = case_config2

        return True, {
            'tc_rel_id': tc_rel_id_local,
            'task_id': task_id,
            'test_case_id': test_case_id,
            'case_name': case_name,
            'algorithm_type': algorithm_type,
            'api_configs': processed_api_configs,
            'audio': audio_data,
            'api_specific_config': api_specific_config,
            'total_audio_duration': total_audio_duration,
            'case_algorithm_params': algorithm_params
        }

    def _get_api_configs(self, task_id):
        """获取任务关联的所有 API 配置

        通过 gRPC GetTaskApis 获取 task_id 关联的 api_id 列表，
        再通过本地 DB 查询 API（本服务 PO）配置。
        """
        # 通过 ACL 仓储获取 TaskAPI 关联
        api_ids = []
        try:
            api_ids = [ta.api_id for ta in _task_data_acl.get_task_apis(task_id) if ta.api_id]
        except Exception as e:
            self._log(level='WARNING', content=f"查询 TaskApis 失败: {e}", task_id=task_id)
            return []

        if not api_ids:
            return []

        # 查询本地 API PO
        local_db_session = get_db_session()
        try:
            return local_db_session.query(API).filter(API.id.in_(api_ids)).all()
        finally:
            local_db_session.close()

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
                default_max_process=api_config.default_max_process or config_manager.get_value('api_executor', 'default_max_process', 5),
                meta=api_config.meta or {},
                max_timeout=api_config.max_timeout or 30,
                vendor=api_config.vendor or None
            ))
        return processed

    def _get_algorithm_type(self, case, case_config):
        """提取 algorithm_type"""
        algorithm_type = None
        if isinstance(case, dict):
            algorithm_type = case.get('algorithm_type')
        else:
            algorithm_type = getattr(case, 'algorithm_type', None)
        if not algorithm_type:
            algorithm_type = case_config.get('algorithm_type')
        if not algorithm_type:
            algorithm_type = 'translation'
        return algorithm_type

    def _get_audio_data(self, test_case_id, task_type, case_name, task_id, tc_rel_id):
        """获取音频数据，返回 (audio_data, total_duration, error_msg)

        通过 gRPC 查询 TestCase 配置和 Audio 信息。
        """
        # 通过 ACL 仓储查询 TestCase 配置
        try:
            case = dto_to_dict(_testcase_acl.get_test_case_detail(test_case_id)) or {}
            if not case:
                error_msg = "找不到测试用例"
                self._log('ERROR', f"API 用例执行失败: {error_msg}", task_id)
                self._fail_tc_rel(tc_rel_id, error_msg, task_id=task_id)
                return None, 0, error_msg
        except Exception as e:
            error_msg = f"查询测试用例失败: {e}"
            self._log('ERROR', f"API 用例执行失败: {error_msg}", task_id)
            self._fail_tc_rel(tc_rel_id, error_msg, task_id=task_id)
            return None, 0, error_msg

        config = case.get('config', {}) or {}
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
            self._fail_tc_rel(tc_rel_id, error_msg, task_id=task_id)
            return None, 0, error_msg

        # 通过 ACL 仓储查询 Audio 信息
        total_audio_duration = 0.0
        for audio_config in target_audios:
            audio_id = audio_config.get('audio_id')
            if audio_id:
                try:
                    a_data = dto_to_dict(_audio_acl.get_audio(audio_id)) or {}
                    total_audio_duration += a_data.get('duration', 0) or 0
                except Exception as e:
                    self._log(level='WARNING', content=f"查询 Audio {audio_id} 失败: {e}", task_id=task_id)

        audio_config = target_audios[0]
        audio_id = audio_config.get('audio_id')
        audio = None
        if audio_id:
            try:
                audio = dto_to_dict(_audio_acl.get_audio(audio_id)) or {}
            except Exception as e:
                self._log(level='WARNING', content=f"查询 Audio {audio_id} 失败: {e}", task_id=task_id)

        if not audio:
            error_msg = f"找不到ID为 {audio_id} 的音频文件"
            self._log('ERROR', f"{expected_test_type} 用例 {case_name} 执行失败: {error_msg}", task_id)
            self._fail_tc_rel(tc_rel_id, error_msg, task_id=task_id)
            return None, 0, error_msg

        audio_data = {
            'id': audio.get('id'),
            'name': audio.get('name'),
            'asr_text': audio.get('asr_text') or "",
            'file_path': audio.get('file_path')
        }
        self._log('DEBUG', f"API用例音频总时长: {total_audio_duration}秒", task_id)
        return audio_data, total_audio_duration, None

    def _fail_tc_rel(self, tc_rel_id, error_msg, task_id=None):
        """将 TaskCase 标记为失败

        通过 ACL 仓储查询 TaskCase（需要 task_id）后更新状态。
        若 task_id 未提供，则仅记录日志。
        """
        if not task_id:
            self._log(level='WARNING', content=f"无法更新 TaskCase {tc_rel_id} 失败状态: 缺少 task_id")
            return

        try:
            tcs = [dto_to_dict(d) for d in _task_data_acl.get_task_case_by_ids(task_id)]
            tc_rel = next((tc for tc in tcs if tc.get('id') == tc_rel_id), None)
            if not tc_rel:
                self._log(level='WARNING', content=f"找不到 TaskCase: {tc_rel_id}", task_id=task_id)
                return

            test_case_id = tc_rel.get('test_case_id')
            if not test_case_id:
                self._log(level='WARNING', content=f"TaskCase {tc_rel_id} 无 test_case_id", task_id=task_id)
                return

            _task_data_acl.update_task_case_status(
                task_id=task_id,
                case_id=str(test_case_id),
                status=TaskCaseStatus.FAILED,
                execution_status=ExecutionStatus.FAILED,
                error_message=error_msg,
            )
        except Exception as e:
            self._log(level='WARNING', content=f"更新 TaskCase {tc_rel_id} 失败状态失败: {e}", task_id=task_id)
