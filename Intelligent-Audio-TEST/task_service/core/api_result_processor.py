"""API 结果处理：TestResult 创建/保存、评估提交、用例结果日志"""
import json
from datetime import datetime, timezone, timedelta

from sqlalchemy import text
from shared.models.models import TaskCase, TestResult, utc8now
from shared.models.database import db
from shared.utils.result_data_store import write_result_data_file, split_result_data
from task_service.algorithm.field_mapper import get_field_mapper


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
        insert_sql = text("""
            INSERT INTO test_results (task_id, test_case_id, device_id, api_id, algorithm_type,
                                     execution_status, response_time, algorithm_result,
                                     execution_steps, result_data, result_data_path, error_message, created_at)
            VALUES (:task_id, :test_case_id, :device_id, :api_id, :algorithm_type,
                    :execution_status, :response_time, :algorithm_result,
                    :execution_steps, :result_data, :result_data_path, :error_message, :created_at)
            RETURNING id
        """)

        params = {
            'task_id': task_id,
            'test_case_id': test_case_id,
            'device_id': None,
            'api_id': api_config_id,
            'algorithm_type': algorithm_type,
            'execution_status': 'completed' if success else 'failed',
            'response_time': response_time,
            'algorithm_result': json.dumps(algo_result, ensure_ascii=False) if algo_result else None,
            'execution_steps': '[]',
            'result_data': json.dumps(lightweight_data, ensure_ascii=False),
            'result_data_path': result_data_path or None,
            'error_message': error_msg,
            'created_at': utc8now()
        }

        result_id = None
        try:
            with db.engine.connect() as conn:
                result = conn.execute(insert_sql, params)
                result_id = result.scalar()
                conn.commit()
                self._log(level='DEBUG', category='database',
                          content=f"SQL插入成功，result_id={result_id}",
                          task_id=task_id, test_case_id=test_case_id)
        except Exception as sql_error:
            import traceback
            self._log(level='ERROR', category='database',
                      content=f"SQL插入失败: {str(sql_error)}\n{traceback.format_exc()}",
                      task_id=task_id, test_case_id=test_case_id)

        # 同步更新 TaskCase 状态
        update_session = db.session()
        try:
            tc_rel = update_session.query(TaskCase).filter_by(task_id=task_id, test_case_id=test_case_id).first()
            if tc_rel and tc_rel.execution_status not in ['stopped']:
                tc_rel.execution_status = 'completed' if success else 'failed'
                update_session.commit()
                if self._executor.execution_engine:
                    self._executor.execution_engine._emit_progress(task_id, force=True)
                    self._executor.execution_engine.notify_case_completed(task_id)
        finally:
            update_session.close()

        return result_id

    def evaluate_test_result(self, task_id, result_id, test_case_id, case_name, case_config,
                             algo_result_dict, algorithm_type='translation', test_type='api'):
        """评估测试结果 — 使用统一字段映射"""
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

        from task_service.algorithm.case_parameter_extractor import CaseParameterExtractor
        eval_params = CaseParameterExtractor.get_evaluation_params(
            case_config=full_case_params,
            algorithm_result=algorithm_result,
            test_type=test_type
        )

        from task_service.evaluation.evaluation_service import evaluation_service
        evaluation_service.evaluate_case(
            task_id, result_id, test_case_id,
            algorithm_result,
            algorithm_type=algorithm_type,
            **eval_params
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
        insert_sql = text("""
            INSERT INTO test_results (task_id, test_case_id, device_id, api_id, algorithm_type,
                                     execution_status, response_time, algorithm_result,
                                     execution_steps, result_data, result_data_path, error_message, created_at)
            VALUES (:task_id, :test_case_id, :device_id, :api_id, :algorithm_type,
                    :execution_status, :response_time, :algorithm_result,
                    :execution_steps, :result_data, :result_data_path, :error_message, :created_at)
            RETURNING id
        """)

        error_msg = None
        if not success:
            failed_rounds = [r for r in algo_result.get('rounds', []) if not r.get('success')]
            error_msg = f"{len(failed_rounds)} 轮失败"

        params = {
            'task_id': task_id,
            'test_case_id': test_case_id,
            'device_id': None,
            'api_id': api_config_id,
            'algorithm_type': algorithm_type,
            'execution_status': 'completed' if success else 'failed',
            'response_time': response_time,
            'algorithm_result': json.dumps(algo_result, ensure_ascii=False) if algo_result else None,
            'execution_steps': json.dumps(algo_result.get('rounds', []), ensure_ascii=False),
            'result_data': json.dumps(lightweight_data, ensure_ascii=False),
            'result_data_path': result_data_path or None,
            'error_message': error_msg,
            'created_at': utc8now()
        }

        try:
            with db.engine.connect() as conn:
                result = conn.execute(insert_sql, params)
                result_id = result.scalar()
                conn.commit()
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
        """更新 TaskCase 为失败状态"""
        if utc_plus_8 is None:
            utc_plus_8 = timezone(timedelta(hours=8))
        local_db_session = db.session()
        try:
            tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
            if tc_rel and tc_rel.execution_status not in ['stopped']:
                tc_rel.execution_status = 'failed'
                tc_rel.evaluation_status = 'completed'
                tc_rel.status = 'failed'
                tc_rel.completed_at = datetime.now(utc_plus_8)
                tc_rel.error_message = error_msg
                local_db_session.commit()
        except Exception:
            local_db_session.rollback()
        finally:
            local_db_session.close()
