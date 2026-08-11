"""E2E 结果聚合：algorithm_result 构建、评估分数回填、DB 更新、TaskCase 状态

领域计算委托给 domain/services/E2ECalculationService，
gRPC 读写委托给 infrastructure/acl/TaskDataAclRepositoryImpl。
"""
import json
import logging

from shared.utils.grpc_json import loads as _loads, dumps as _dumps
from e2e_test_service.domain.services import E2ECalculationService
from e2e_test_service.infrastructure.acl import TaskDataAclRepositoryImpl

logger = logging.getLogger(__name__)


class E2EAggregator:
    """E2E 结果聚合器"""

    def __init__(self, executor):
        self._executor = executor
        self._task_data_repo = TaskDataAclRepositoryImpl()

    @property
    def _log(self):
        return self._executor._log

    def build_algorithm_result(self, task_id, all_round_results, case_config, algorithm_type):
        """从多轮原始结果构建 algo_result 结构（rounds[] + aggregated）"""
        return E2ECalculationService.build_algorithm_result(
            all_round_results, case_config, algorithm_type
        )

    def update_algorithm_result_evaluation(self, task_id, result_id):
        """从 DB 查各轮评估分数，回填到 rounds[].evaluation，并计算 aggregated 汇总值

        此方法在所有轮次评估完成后调用，聚合各维度分数到 algo_result。
        """
        try:
            test_result = self._task_data_repo.get_test_result_by_id(int(result_id))
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

            # 通过 ACL 仓储获取维度评估结果（含 dimension_name）
            dim_results = self._task_data_repo.get_dimension_results_by_result_ids([int(result_id)])

            round_evals = {}
            for dr in dim_results:
                rn = dr.round_number
                if rn is None:
                    continue
                dim_name = dr.dimension_name or str(dr.dimension_id)
                dim_key_lower = dim_name.lower().replace(' ', '_').replace('-', '_')
                if rn not in round_evals:
                    round_evals[rn] = {}
                if dr.evaluation_status == 'completed' and dr.score is not None:
                    round_evals[rn][dim_key_lower] = dr.score

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

            # 通过 ACL 仓储更新 TestResult.algorithm_result
            self._task_data_repo.update_test_result_algorithm_result(
                int(result_id), _dumps(algo_result)
            )

            self._log(
                level='INFO',
                content=f"[aggregate] 更新完成: result_id={result_id}, avg_wer={aggregated.get('avg_wer')}, avg_llm_judge={aggregated.get('avg_llm_judge')}",
                task_id=task_id
            )
        except Exception as e:
            self._log(
                level='ERROR',
                content=f"[aggregate] 更新失败: result_id={result_id}, error={str(e)}",
                task_id=task_id
            )

    def update_test_result(self, result_id, algo_result, execution_status, response_time=0,
                           error_message=None, task_id=None, result_data_path=None):
        """更新已存在的 TestResult 记录"""
        # DEBUG: 记录写入前的 algo_result 状态
        _rounds_dbg = algo_result.get('rounds', []) if isinstance(algo_result, dict) else []
        _out_keys_dbg = [list(r.get('output', {}).keys()) for r in _rounds_dbg]
        _rf_dbg = [r.get('output', {}).get('record_file', '<MISSING>') for r in _rounds_dbg]
        self._log(
            level='DEBUG',
            content=f"[update_test_result] result_id={result_id}, exec_status={execution_status}, output_keys={_out_keys_dbg}, record_file={_rf_dbg}, has_path={result_data_path is not None}",
            task_id=task_id
        )
        # 通过 ACL 仓储更新 algorithm_result
        self._task_data_repo.update_test_result_algorithm_result(
            int(result_id), _dumps(algo_result) if algo_result else ''
        )
        # 通过 ACL 仓储更新 execution_status
        self._task_data_repo.update_test_result_status(
            int(result_id), execution_status or ''
        )

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

        try:
            # 通过 ACL 仓储查询 TaskCase
            tc_list = self._task_data_repo.get_task_case_by_ids(task_id, [str(test_case_id)])
            if not tc_list:
                return False

            if not all_results:
                # 没有采集到设备结果，更新 TaskCase 状态为 failed
                self._task_data_repo.update_task_case_status(
                    task_id, str(test_case_id),
                    status='failed', execution_status='failed',
                    evaluation_status='failed',
                    error_message='没有采集到设备结果',
                )
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

                if execution_success:
                    self._task_data_repo.update_task_case_status(
                        task_id, str(test_case_id),
                        status='pending', execution_status='completed',
                    )
                else:
                    self._task_data_repo.update_task_case_status(
                        task_id, str(test_case_id),
                        status='failed', execution_status='failed',
                        evaluation_status='failed',
                    )

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

                # 通过 ACL 仓储更新 TaskCase 状态
                if execution_success:
                    eval_status = 'completed' if not all_eval_items else ''
                    self._task_data_repo.update_task_case_status(
                        task_id, str(test_case_id),
                        status='pending', execution_status='completed',
                        evaluation_status=eval_status,
                    )
                else:
                    self._task_data_repo.update_task_case_status(
                        task_id, str(test_case_id),
                        status='failed', execution_status='failed',
                        evaluation_status='failed',
                    )

                if execution_success and all_eval_items:
                    ref_fields = E2ECalculationService.build_ref_fields(kwargs)

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
        except Exception as e:
            self._log(
                level='ERROR',
                content=f"[process_results] gRPC 调用失败: error={str(e)}",
                task_id=task_id
            )
            return False

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
