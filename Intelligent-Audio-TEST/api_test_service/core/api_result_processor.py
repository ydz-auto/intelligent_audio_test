"""API 结果处理：TestResult 创建/保存、评估提交、用例结果日志"""
import json
import logging
from datetime import datetime, timezone, timedelta

from shared.utils.dto_utils import dto_to_dict
from shared.utils.result_data_store import write_result_data_file, split_result_data
from shared.utils.status_constants import ExecutionStatus, TaskCaseStatus, EvaluationStatus
from api_test_service.infrastructure.acl import (
    TaskDataAclRepositoryImpl,
    AlgorithmQueryAclRepositoryImpl,
    EvaluationAclRepositoryImpl,
)

logger = logging.getLogger(__name__)

# 跨服务出站 gRPC 经 ACL 仓储（返回 DTO），不返回 raw dict
_task_data_acl = TaskDataAclRepositoryImpl()
_algo_acl = AlgorithmQueryAclRepositoryImpl()
_evaluation_acl = EvaluationAclRepositoryImpl()


class APIResultProcessor:
    """API 结果处理器"""

    def __init__(self, executor):
        self._executor = executor

    @property
    def _log(self):
        return self._executor._log

    def create_test_result(self, task_id, test_case_id, api_config_id, success, error_msg,
                           algo_result_dict, latency, final_result_result, algorithm_type='translation'):
        """创建测试结果记录"""
        self._log(level='DEBUG', category='database',
                  content=f"开始创建测试结果记录: task_id={task_id}, test_case_id={test_case_id}, "
                          f"api_config_id={api_config_id}, success={success}",
                  task_id=task_id, test_case_id=test_case_id, api_id=api_config_id)

        response_data = {
            "status_code": 200,
            "latency": latency,
            "raw_response": final_result_result.get('raw_response', '') if isinstance(final_result_result, dict) else '',
            "is_sentence_end": True,
            "is_session_end": True
        }

        try:
            response_time = int(latency) if latency is not None else None
        except (ValueError, TypeError):
            response_time = None

        algorithm_result = algo_result_dict if algo_result_dict else {}

        result_data_path = write_result_data_file(task_id, test_case_id, 'api', response_data)
        lightweight_data, _ = split_result_data(response_data)

        algo_result = algorithm_result
        result_data = {
            'test_case_id': test_case_id,
            'device_id': None,
            'api_id': api_config_id,
            'algorithm_type': algorithm_type,
            'execution_status': ExecutionStatus.COMPLETED if success else ExecutionStatus.FAILED,
            'response_time': response_time,
            'algorithm_result': json.dumps(algo_result, ensure_ascii=False) if algo_result else None,
            'execution_steps': '[]',
            'result_data': json.dumps(lightweight_data, ensure_ascii=False),
            'result_data_path': result_data_path or None,
            'error_message': error_msg,
        }

        result_id = None
        try:
            result_id = _task_data_acl.submit_result(task_id, result_data)
            self._log(level='DEBUG', category='database',
                      content=f"gRPC写入TestResult成功，result_id={result_id}",
                      task_id=task_id, test_case_id=test_case_id)
        except Exception as grpc_error:
            import traceback
            self._log(level='ERROR', category='database',
                      content=f"gRPC写入TestResult失败: {str(grpc_error)}\n{traceback.format_exc()}",
                      task_id=task_id, test_case_id=test_case_id)

        # 同步更新 TaskCase 状态
        try:
            _task_data_acl.update_task_case_status(
                task_id=task_id,
                case_id=test_case_id,
                execution_status=ExecutionStatus.COMPLETED if success else ExecutionStatus.FAILED,
            )
            if self._executor.execution_engine:
                self._executor.execution_engine._emit_progress(task_id, force=True)
                self._executor.execution_engine.notify_case_completed(task_id)
        except Exception as e:
            self._log(level='WARNING', category='database',
                      content=f"更新 TaskCase 状态失败: {e}",
                      task_id=task_id, test_case_id=test_case_id)

        # 发布用例执行完成事件到事件总线（异步通知 task_service）
        from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
        EventBus().publish(
            EventChannel.CASE_EVENTS,
            EventType.CASE_EXECUTION_COMPLETED if success else EventType.CASE_FAILED,
            {
                'task_id': str(task_id),
                'test_case_id': str(test_case_id),
                'result_id': str(result_id) if result_id else None,
                'success': success,
            }
        )

        return result_id

    def evaluate_test_result(self, task_id, result_id, test_case_id, case_name, case_config,
                             algo_result_dict, algorithm_type='translation', test_type='api'):
        """评估测试结果 — 使用统一字段映射

        迁移后通过 gRPC 调用 task_service 的 ExecutionService.EvaluateCase。
        """
        self._log(level='INFO', category='evaluation',
                  content=f"开始评估API用例: {case_name}",
                  task_id=task_id, test_case_id=test_case_id)

        self._executor._handle_control(task_id)

        algorithm_result = algo_result_dict if algo_result_dict else {}
        case_params = case_config or {}
        algorithm_params = case_params.get('algorithm_params', case_params)
        reference_params = case_params.get('reference_params', {})

        full_case_params = {
            'algorithm_params': algorithm_params,
            'reference_params': reference_params
        }

        all_params = dto_to_dict(_algo_acl.extract_case_all_params(full_case_params)) or {}
        eval_params = all_params.get('evaluation', {}) if isinstance(all_params, dict) else {}

        # 通过 ACL 仓储调用 evaluation_service 的 EvaluateCase
        _evaluation_acl.submit_evaluate_case(
            task_id=task_id,
            result_id=result_id,
            test_case_id=test_case_id,
            algorithm_result=algorithm_result,
            eval_params={**eval_params, 'algorithm_type': algorithm_type, 'test_type': test_type},
        )

        self._log(level='INFO', category='evaluation',
                  content=f"评估API用例已入队: {case_name}",
                  task_id=task_id, test_case_id=test_case_id)
        return True

    def create_multi_round_test_result(self, task_id, test_case_id, api_config_id,
                                       algorithm_type, aggregated, success):
        """为多轮会话创建单条测试结果记录"""
        total_latency = aggregated.get('total_latency', 0)
        response_data = {
            "status_code": 200,
            "latency": total_latency,
            "raw_response": json.dumps(aggregated.get('session_summary', {})),
            "is_sentence_end": True,
            "is_session_end": True,
            "multi_round": True,
            "round_count": aggregated.get('round_count', 0)
        }

        try:
            response_time = int(total_latency * 1000)
        except (ValueError, TypeError):
            response_time = None

        result_data_path = write_result_data_file(task_id, test_case_id, 'api', response_data)
        lightweight_data, _ = split_result_data(response_data)

        algo_result = aggregated.get('algorithm_result', {})

        error_msg = None
        if not success:
            failed_rounds = [r for r in algo_result.get('rounds', []) if not r.get('success')]
            error_msg = f"{len(failed_rounds)} 轮失败"

        result_data = {
            'test_case_id': test_case_id,
            'device_id': None,
            'api_id': api_config_id,
            'algorithm_type': algorithm_type,
            'execution_status': ExecutionStatus.COMPLETED if success else ExecutionStatus.FAILED,
            'response_time': response_time,
            'algorithm_result': json.dumps(algo_result, ensure_ascii=False) if algo_result else None,
            'execution_steps': json.dumps(algo_result.get('rounds', []), ensure_ascii=False),
            'result_data': json.dumps(lightweight_data, ensure_ascii=False),
            'result_data_path': result_data_path or None,
            'error_message': error_msg,
        }

        try:
            result_id = _task_data_acl.submit_result(task_id, result_data)
            self._log(level='INFO',
                      content=f"多轮会话测试结果已保存: result_id={result_id}, "
                              f"rounds={aggregated.get('round_count')}, success={success}",
                      task_id=task_id, test_case_id=test_case_id, api_id=api_config_id)
            return result_id
        except Exception as e:
            self._log(level='ERROR', content=f"保存多轮会话测试结果失败: {e}",
                      task_id=task_id, test_case_id=test_case_id)
            return None

    def update_task_case_failure(self, task_id, tc_rel_id, error_msg, utc_plus_8=None):
        """更新 TaskCase 为失败状态

        通过 ACL 仓储调用 task_service.TaskDataService：
        1. get_task_case_by_ids 查询 TaskCase（按 tc_rel_id 即主键匹配）
        2. 若未停止，则 update_task_case_status 更新为失败
        """
        if utc_plus_8 is None:
            utc_plus_8 = timezone(timedelta(hours=8))
        try:
            tcs = [dto_to_dict(d) for d in _task_data_acl.get_task_case_by_ids(task_id)]
            tc_rel = next((tc for tc in tcs if tc.get('id') == tc_rel_id), None)
            if not tc_rel:
                self._log(level='WARNING', content=f"找不到 TaskCase: {tc_rel_id}",
                          task_id=task_id)
                return
            if tc_rel.get('execution_status') in [ExecutionStatus.STOPPED]:
                return

            test_case_id = tc_rel.get('test_case_id')
            if not test_case_id:
                self._log(level='WARNING', content=f"TaskCase {tc_rel_id} 无 test_case_id",
                          task_id=task_id)
                return

            _task_data_acl.update_task_case_status(
                task_id=task_id,
                case_id=str(test_case_id),
                status=TaskCaseStatus.FAILED,
                execution_status=ExecutionStatus.FAILED,
                evaluation_status=EvaluationStatus.COMPLETED,
                error_message=error_msg,
            )
        except Exception as e:
            self._log(level='WARNING', content=f"更新 TaskCase 失败状态失败: {e}",
                      task_id=task_id)
