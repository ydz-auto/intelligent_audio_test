# -*- coding: utf-8 -*-
"""数据库操作相关方法"""
import json
from datetime import datetime
from sqlalchemy import text

from shared.algorithm.field_mapper import get_field_mapper
from shared.models.database import db, _engine_ref
from shared.models.models import utc8now, Task, TaskCase, TestCase


class DbMixin:
    """执行器基类数据库操作方法"""

    def _validate_and_get_data(self, task_id, tc_rel_id):
        local_db_session = db.session()
        try:
            task = local_db_session.get(Task, task_id)
            if not task:
                return {'success': False, 'error': "任务不存在"}
            tc_rel = local_db_session.get(TaskCase, tc_rel_id)
            if not tc_rel:
                return {'success': False, 'error': "找不到测试用例关联"}
            case = local_db_session.get(TestCase, tc_rel.test_case_id)
            if not case:
                return {'success': False, "error": "找不到测试用例"}

            case_config = case.config or {}
            algorithm_type = case.algorithm_type if hasattr(case, 'algorithm_type') and case.algorithm_type else None
            if not algorithm_type:
                algorithm_type = case_config.get('algorithm_type')
            if not algorithm_type:
                algorithm_type = 'translation'

            self._log(
                level='DEBUG',
                content=f"[_validate_and_get_data] case.algorithm_type={case.algorithm_type}, case_config.algorithm_type={case_config.get('algorithm_type')}, final algorithm_type={algorithm_type}",
                task_id=task_id,
                test_case_id=tc_rel.test_case_id
            )

            field_mapper = get_field_mapper()
            case_fields = field_mapper.get_case_fields(algorithm_type)

            from shared.algorithm.case_parameter_extractor import _get_round_algo_params, _normalize_algorithm_params
            algorithm_params_col = getattr(case, 'algorithm_params', None)

            case_config = case_config.copy() if case_config else {}
            rounds = case_config.get('rounds', [])
            for round_item in rounds:
                if isinstance(round_item, dict):
                    rn = round_item.get('round_number', 1)
                    round_params = _get_round_algo_params(algorithm_params_col, rn)
                    if round_params:
                        round_item['algorithm_params'] = round_params

            first_round = rounds[0] if rounds else {}
            case_algorithm_params = _normalize_algorithm_params(
                first_round.get('algorithm_params', {}) if isinstance(first_round, dict) else {}
            )

            from shared.algorithm.reference_params_generator import ReferenceParamsGenerator
            reference_params_col = getattr(case, 'reference_params', None)
            all_reference_params = []

            if reference_params_col and isinstance(reference_params_col, list):
                for ref_entry in reference_params_col:
                    if isinstance(ref_entry, dict):
                        ref_path = ref_entry.get('reference_params_path')
                        if ref_path:
                            round_refs = ReferenceParamsGenerator.load_from_file(ref_path)
                            if round_refs:
                                all_reference_params.extend(round_refs)
            else:
                for round_item in rounds:
                    if isinstance(round_item, dict):
                        ref_path = round_item.get('reference_params_path')
                        if ref_path:
                            round_refs = ReferenceParamsGenerator.load_from_file(ref_path)
                            if round_refs:
                                all_reference_params.extend(round_refs)

            case_reference_params = all_reference_params if all_reference_params else {}

            if case_algorithm_params:
                case_config['algorithm_params'] = case_algorithm_params

            result_data = {
                'case_name': case.name,
                'case_config': case_config,
                'case_reference_params': case_reference_params,
                'reference_params_col': reference_params_col if isinstance(reference_params_col, list) else None,
                'case_algorithm_params': case_algorithm_params,
                'test_case_id': tc_rel.test_case_id,
                'tc_rel_id': tc_rel_id,
                'algorithm_type': algorithm_type,
                'task_name': task.name if task else None,
            }

            for config_key, case_field in case_fields.items():
                result_data[config_key] = getattr(case, case_field, None)

            return {'success': True, 'data': result_data}
        finally:
            local_db_session.close()

    def _update_tc_rel_status(self, tc_rel_id, **kwargs):
        local_db_session = db.session()
        try:
            tc_rel = local_db_session.get(TaskCase, tc_rel_id)
            if tc_rel:
                for key, value in kwargs.items():
                    setattr(tc_rel, key, value)
                if 'execution_status' in kwargs:
                    if kwargs['execution_status'] == 'running':
                        tc_rel.started_at = datetime.now(self.utc_plus_8)
                        tc_rel.evaluation_status = 'queued'
                    elif kwargs['execution_status'] in ['completed', 'failed']:
                        tc_rel.completed_at = datetime.now(self.utc_plus_8)
                        if tc_rel.evaluation_status in ['queued', 'pending']:
                            tc_rel.evaluation_status = 'completed'
                local_db_session.commit()

                task_id = tc_rel.task_id
                if task_id and self.execution_engine:
                    self.execution_engine._emit_progress(task_id, force=True)
        finally:
            local_db_session.close()

    def _save_result(self, task_id, test_case_id, result_data, algo_result, algorithm_type,
                     device_id=None, api_id=None, execution_status='completed', response_time=0,
                     error_message=None, extra_data=None, result_data_path=None):
        """保存测试结果到数据库"""
        insert_sql = text("""
            INSERT INTO test_results (task_id, test_case_id, device_id, api_id, algorithm_type, execution_status, response_time, algorithm_result, execution_steps, result_data, result_data_path, error_message, created_at)
            VALUES (:task_id, :test_case_id, :device_id, :api_id, :algorithm_type, :execution_status, :response_time, :algorithm_result, :execution_steps, :result_data, :result_data_path, :error_message, :created_at)
            RETURNING id
        """)

        params = {
            'task_id': task_id,
            'test_case_id': test_case_id,
            'device_id': device_id,
            'api_id': api_id,
            'algorithm_type': algorithm_type,
            'execution_status': execution_status,
            'response_time': response_time,
            'algorithm_result': json.dumps(algo_result) if algo_result else None,
            'execution_steps': '[]',
            'result_data': json.dumps(result_data) if result_data else None,
            'result_data_path': result_data_path or None,
            'error_message': error_message,
            'created_at': utc8now()
        }

        with _engine_ref[0].connect() as conn:
            result = conn.execute(insert_sql, params)
            result_id = result.scalar()
            conn.commit()

        return result_id
