"""E2E 结果聚合：algorithm_result 构建、评估分数回填、DB 更新、TaskCase 状态"""
import json

from sqlalchemy import text
from backend.models.models import TaskCase, TestResult, TestResultDimension, Dimension, utc8now
from backend.models.database import db


class E2EAggregator:
    """E2E 结果聚合器"""

    def __init__(self, executor):
        self._executor = executor

    @property
    def _log(self):
        return self._executor._log

    def build_algorithm_result(self, task_id, all_round_results, case_config, algorithm_type):
        """从多轮原始结果构建 algo_result 结构（rounds[] + aggregated）"""
        from backend.utils.algorithm.field_mapper import get_field_mapper

        # 获取映射后的设备输出字段（含 source_param → target_param 映射关系）
        mapped_output_fields = get_field_mapper().get_mapped_device_output_fields(algorithm_type)

        rounds_by_index = {}
        for r in all_round_results:
            rn = r.get('round_number', 0)
            if rn not in rounds_by_index:
                rounds_by_index[rn] = []
            rounds_by_index[rn].append(r)

        case_rounds = case_config.get('rounds', [])
        rounds_list = []
        latency_values = []

        for round_idx in sorted(rounds_by_index.keys()):
            round_results = rounds_by_index[round_idx]
            primary = round_results[0] if round_results else {}

            round_config = case_rounds[round_idx] if round_idx < len(case_rounds) else {}
            audios = round_config.get('audios', [])
            first_audio = audios[0] if audios else {}

            audio_name = first_audio.get('audio_name') or first_audio.get('name', '')
            audio_path = first_audio.get('audio_path') or first_audio.get('path', '')

            # primary 中已包含映射后的 target 字段（由 convert_results 写入），直接用 target 取值
            # 同时保留维度专属 key（target__dim_N），供评估阶段按维度取值
            round_output = {}
            if isinstance(mapped_output_fields, list):
                for f in mapped_output_fields:
                    target = f.get('code')
                    dim_id = f.get('dimension_id')
                    # 维度专属 key
                    if dim_id is not None:
                        dim_key = f'{target}__dim_{dim_id}'
                        dim_val = primary.get(dim_key)
                        if dim_val is not None:
                            round_output[dim_key] = dim_val
                    # 通用 key（第一个有效值优先）
                    val = primary.get(target)
                    if val is not None:
                        if target not in round_output or not round_output[target]:
                            round_output[target] = val
            else:
                for target, f in mapped_output_fields.items():
                    dim_id = f.get('dimension_id') if isinstance(f, dict) else None
                    if dim_id is not None:
                        dim_key = f'{target}__dim_{dim_id}'
                        dim_val = primary.get(dim_key)
                        if dim_val is not None:
                            round_output[dim_key] = dim_val
                    val = primary.get(target)
                    if val is not None:
                        if target not in round_output or not round_output[target]:
                            round_output[target] = val

            latency = primary.get('response_time') or primary.get('latency')
            if latency is not None:
                try:
                    latency_values.append(float(latency))
                except (ValueError, TypeError):
                    pass

            wait_time = round_config.get('waitTime', 5000)
            if wait_time is None:
                wait_time = 5000

            rounds_list.append({
                'round': round_idx,
                'input': {
                    'audio_name': audio_name,
                    'audio_path': audio_path,
                    'type': 'audio',
                },
                'output': round_output,
                'latency': latency,
                'wait_time': wait_time,
                'evaluation': {},
            })

        avg_latency = None
        if latency_values:
            avg_latency = round(sum(latency_values) / len(latency_values), 4)

        aggregated = {
            'avg_latency': avg_latency,
            'avg_wer': None,
            'avg_llm_judge': None,
        }

        result = {
            'test_type': 'e2e',
            'algorithm_type': algorithm_type,
            'total_rounds': len(rounds_list),
            'rounds': rounds_list,
            'aggregated': aggregated,
        }

        self._log(
            level='DEBUG',
            content=f"[build_algorithm_result] 构建 E2E 算法结果: total_rounds={len(rounds_list)}, avg_latency={avg_latency}",
            task_id=task_id
        )

        return result

    def update_algorithm_result_evaluation(self, task_id, result_id):
        """从 DB 查各轮评估分数，回填到 rounds[].evaluation，并计算 aggregated 汇总值

        此方法在所有轮次评估完成后调用，聚合各维度分数到 algo_result。
        """
        local_db_session = db.session()
        try:
            test_result = local_db_session.query(TestResult).filter(
                TestResult.id == result_id
            ).first()
            if not test_result:
                self._log(
                    level='ERROR',
                    content=f"[aggregate] TestResult 不存在: result_id={result_id}",
                    task_id=task_id
                )
                return

            algo_result = test_result.algorithm_result
            # 循环反序列化，处理可能的双重序列化旧数据
            while isinstance(algo_result, str):
                try:
                    algo_result = json.loads(algo_result)
                except (json.JSONDecodeError, TypeError):
                    algo_result = {}

            # DEBUG: 检查 record_file 是否存在
            _rounds_debug = algo_result.get('rounds', []) if isinstance(algo_result, dict) else []
            _output_keys_debug = [list(r.get('output', {}).keys()) for r in _rounds_debug] if isinstance(_rounds_debug, list) else []
            _rf_debug = [r.get('output', {}).get('record_file', '<MISSING>') for r in _rounds_debug] if isinstance(_rounds_debug, list) else []
            self._log(
                level='DEBUG',
                content=f"[update_algorithm_result_evaluation READ] result_id={result_id}, rounds_count={len(_rounds_debug)}, output_keys={_output_keys_debug}, record_file={_rf_debug}",
                task_id=task_id
            )
            if not isinstance(algo_result, dict):
                algo_result = {}

            dim_results = local_db_session.query(TestResultDimension).filter(
                TestResultDimension.test_result_id == result_id
            ).all()

            round_evals = {}
            for dr in dim_results:
                if dr.round_number is None:
                    continue
                dim_obj = local_db_session.query(Dimension).get(dr.dimension_id) if dr.dimension_id else None
                dim_key = dim_obj.name if dim_obj else str(dr.dimension_id)
                dim_key_lower = dim_key.lower().replace(' ', '_').replace('-', '_')
                if dr.round_number not in round_evals:
                    round_evals[dr.round_number] = {}
                if dr.evaluation_status == 'completed' and dr.score is not None:
                    round_evals[dr.round_number][dim_key_lower] = dr.score

            rounds_list = algo_result.get('rounds', [])
            for round_idx, eval_data in round_evals.items():
                if round_idx < len(rounds_list):
                    rounds_list[round_idx]['evaluation'] = eval_data

            all_wer = []
            all_llm_judge = []
            for rd in rounds_list:
                ev = rd.get('evaluation', {})
                if 'wer' in ev and ev['wer'] is not None:
                    try:
                        all_wer.append(float(ev['wer']))
                    except (ValueError, TypeError):
                        pass
                if 'llm_judge' in ev and ev['llm_judge'] is not None:
                    try:
                        all_llm_judge.append(float(ev['llm_judge']))
                    except (ValueError, TypeError):
                        pass

            aggregated = algo_result.get('aggregated', {})
            aggregated['avg_wer'] = round(sum(all_wer) / len(all_wer), 4) if all_wer else None
            aggregated['avg_llm_judge'] = round(sum(all_llm_judge) / len(all_llm_judge), 4) if all_llm_judge else None

            algo_result['rounds'] = rounds_list
            algo_result['aggregated'] = aggregated
            # DEBUG: 写回前检查 record_file
            _rf_write_dbg = [r.get('output', {}).get('record_file', '<MISSING>') for r in rounds_list]
            self._log(
                level='DEBUG',
                content=f"[update_algorithm_result_evaluation WRITE] result_id={result_id}, record_file={_rf_write_dbg}",
                task_id=task_id
            )
            test_result.algorithm_result = algo_result
            local_db_session.commit()

            self._log(
                level='INFO',
                content=f"[aggregate] 更新完成: result_id={result_id}, avg_wer={aggregated.get('avg_wer')}, avg_llm_judge={aggregated.get('avg_llm_judge')}",
                task_id=task_id
            )
        except Exception as e:
            local_db_session.rollback()
            self._log(
                level='ERROR',
                content=f"[aggregate] 更新失败: result_id={result_id}, error={str(e)}",
                task_id=task_id
            )
        finally:
            local_db_session.close()

    def update_test_result(self, result_id, algo_result, execution_status, response_time=0,
                           error_message=None, task_id=None, result_data_path=None):
        """更新已存在的 TestResult 记录"""
        if result_data_path is not None:
            update_sql = text("""
                UPDATE test_results
                SET algorithm_result = :algorithm_result,
                    execution_status = :execution_status,
                    response_time = :response_time,
                    error_message = :error_message,
                    result_data_path = :result_data_path
                WHERE id = :result_id
            """)
        else:
            update_sql = text("""
                UPDATE test_results
                SET algorithm_result = :algorithm_result,
                    execution_status = :execution_status,
                    response_time = :response_time,
                    error_message = :error_message
                WHERE id = :result_id
            """)
        params = {
            'algorithm_result': json.dumps(algo_result, ensure_ascii=False) if algo_result else None,
            'execution_status': execution_status,
            'response_time': response_time,
            'error_message': error_message,
            'result_id': result_id,
        }
        if result_data_path is not None:
            params['result_data_path'] = result_data_path
        # DEBUG: 记录写入前的 algo_result 状态
        _rounds_dbg = algo_result.get('rounds', []) if isinstance(algo_result, dict) else []
        _out_keys_dbg = [list(r.get('output', {}).keys()) for r in _rounds_dbg]
        _rf_dbg = [r.get('output', {}).get('record_file', '<MISSING>') for r in _rounds_dbg]
        self._log(
            level='DEBUG',
            content=f"[update_test_result] result_id={result_id}, exec_status={execution_status}, output_keys={_out_keys_dbg}, record_file={_rf_dbg}, has_path={result_data_path is not None}",
            task_id=task_id
        )
        with db.engine.connect() as conn:
            conn.execute(update_sql, params)
            conn.commit()

    def process_results(self, task_id, case_name, tc_rel_id, test_case_id, all_results, case_config=None,
                        case_reference_params=None, case_algorithm_params=None,
                        adjusted_case_reference_params=None, **kwargs):
        """处理 E2E 测试结果 — 更新 TaskCase 状态，提交非多轮场景的评估"""
        algorithm_type = kwargs.get('algorithm_type', 'translation')
        precreated_result_id = kwargs.get('precreated_result_id')
        precomputed_execution_success = kwargs.get('precomputed_execution_success')

        if adjusted_case_reference_params:
            self._log(
                level='DEBUG',
                content=f"[process_results] using adjusted_case_reference_params: type={type(adjusted_case_reference_params)}",
                task_id=task_id
            )
            if isinstance(adjusted_case_reference_params, list):
                adjusted_ref_dict = {}
                for item in adjusted_case_reference_params:
                    if isinstance(item, dict):
                        code = item.get('code')
                        if code:
                            adjusted_ref_dict[code] = item
                self._log(
                    level='DEBUG',
                    content=f"[process_results] adjusted_ref_dict keys: {list(adjusted_ref_dict.keys())}",
                    task_id=task_id
                )
                case_reference_params = adjusted_ref_dict
            else:
                case_reference_params = adjusted_case_reference_params

        is_multi_round = any(r.get('round_number') is not None for r in all_results) if all_results else False
        self._log(level='DEBUG', content=f"[process_results] is_multi_round={is_multi_round}", task_id=task_id)

        local_db_session = db.session()
        try:
            tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
            if not tc_rel:
                return False

            if not all_results:
                tc_rel.execution_status = 'failed'
                tc_rel.evaluation_status = 'failed'
                tc_rel.status = 'failed'
                tc_rel.error_message = "没有采集到设备结果"
                tc_rel.completed_at = utc8now()
                local_db_session.commit()
                return False

            extra_params = self._executor._execute_extra_params(algorithm_type, kwargs, include_format_strings=True)
            kwargs.update(extra_params)

            if is_multi_round:
                # 多轮场景：algo_result 和 TestResult 已在循环后更新，整体评估已提交
                # 此处仅更新 TaskCase 状态
                execution_success = precomputed_execution_success if precomputed_execution_success is not None else all(
                    r.get('raw_results', {}).get('success', False) for r in all_results
                )

                result_id = precreated_result_id

                self._log(
                    level='DEBUG',
                    content=f"[process_results] 多轮 TaskCase 状态更新: result_id={result_id}, execution_success={execution_success}",
                    task_id=task_id,
                    test_case_id=test_case_id
                )

                tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
                tc_rel.execution_status = 'completed' if execution_success else 'failed'
                if not execution_success:
                    tc_rel.evaluation_status = 'failed'
                    tc_rel.status = 'failed'
                    tc_rel.completed_at = utc8now()
                else:
                    tc_rel.status = 'pending'
                local_db_session.commit()

                return execution_success
            else:
                result = self._executor._process_results_base(
                    task_id=task_id,
                    test_case_id=test_case_id,
                    all_results=all_results,
                    case_config=case_config,
                    case_reference_params=case_reference_params,
                    algorithm_type=algorithm_type,
                    device_id_field='device_id',
                    api_id_field='api_id'
                )

                execution_success = result['execution_success']
                all_eval_items = result['all_eval_items']
                case_params = result['case_params']

                # super()._process_results() 同样会调用 db.session().close()，
                # 重新查询 tc_rel 确保它重新进入 identity map
                tc_rel = local_db_session.query(TaskCase).get(tc_rel_id)
                tc_rel.execution_status = 'completed' if execution_success else 'failed'
                if not execution_success:
                    tc_rel.evaluation_status = 'failed'
                    tc_rel.status = 'failed'
                    tc_rel.completed_at = utc8now()
                else:
                    tc_rel.status = 'pending'
                    if not all_eval_items:
                        tc_rel.evaluation_status = 'completed'
                local_db_session.commit()

                if execution_success and all_eval_items:
                    def extract_value(val):
                        if isinstance(val, dict) and 'value' in val:
                            return val.get('value', '')
                        return val

                    ref_fields = {}
                    for field_key, field_value in kwargs.items():
                        if field_value:
                            ref_fields[field_key] = extract_value(field_value)

                    for item in all_eval_items:
                        self.log_case_result(
                            task_id, case_name, item['res'], ref_fields,
                            algorithm_type=algorithm_type, test_case_id=item['test_case_id']
                        )

                    for item in all_eval_items:
                        algo_result = item['res']

                        self._executor._evaluate_result(
                            task_id=task_id,
                            result_id=item['result_id'],
                            test_case_id=item['test_case_id'],
                            algo_result=algo_result,
                            case_config=case_params,
                            case_reference_params=case_reference_params,
                            algorithm_type=algorithm_type,
                            test_type='e2e',
                            case_algorithm_params=case_algorithm_params,
                            round_number=item.get('round_number')
                        )

                return execution_success
        finally:
            local_db_session.close()

    def log_case_result(self, task_id, case_name, res, ref_fields, **kwargs):
        """记录用例结果日志"""
        algorithm_type = kwargs.pop('algorithm_type', 'translation')

        log_content = f"E2E 用例 {case_name}: " + \
                      self._executor._get_result_mapper().build_case_result_log(algorithm_type, res, ref_fields, **kwargs)

        self._log(
            level='INFO' if res.get('success', res.get('raw_results', {}).get('success', False)) else 'WARNING',
            content=log_content,
            task_id=task_id,
            test_case_id=kwargs.pop('test_case_id', None),
            device_id=res.get('device_id')
        )
