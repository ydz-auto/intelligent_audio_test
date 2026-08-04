import json
import copy

from shared.utils.result_data_store import write_result_data_file


class FinalizationMixin:
    """阶段三：循环后聚合 + 评估 —— 构建最终 algo_result，提交整体评估，聚合维度分数"""

    def _finalize_rounds(self, task_id, tc_rel_id, data, case_config, case_name,
                         algorithm_type, test_case_id, result_id,
                         all_round_results, execution_success,
                         case_reference_params, last_adjusted_ref_params):
        """构建最终 algo_result，提交整体评估，聚合维度分数，更新 TaskCase 状态"""
        # 构建最终 algo_result
        final_algo_result = self._aggregator.build_algorithm_result(task_id, all_round_results, case_config, algorithm_type)

        # 持久化 raw_results 到文件，供重新评估时重新映射字段
        result_data_to_save = {
            'multi_round': True,
            'total_rounds': len(all_round_results),
            'raw_results_list': copy.deepcopy(all_round_results),
        }
        # 调整后的参考参数也一并存储
        if last_adjusted_ref_params:
            result_data_to_save['adjusted_reference_params'] = last_adjusted_ref_params
        device_sn = all_round_results[0].get('device_sn', '') if all_round_results else ''
        result_data_path = write_result_data_file(task_id, test_case_id, device_sn, result_data_to_save)

        latency_values = []
        for r in all_round_results:
            lat = r.get('response_time') or r.get('latency')
            if lat is not None:
                try:
                    latency_values.append(float(lat))
                except (ValueError, TypeError):
                    pass
        avg_response_time = round(sum(latency_values) / len(latency_values), 4) if latency_values else 0

        self._aggregator.update_test_result(
            result_id=result_id, algo_result=final_algo_result,
            execution_status='completed' if execution_success else 'failed',
            response_time=avg_response_time,
            error_message=None if execution_success else "多轮测试存在失败轮次",
            task_id=task_id,
            result_data_path=result_data_path or None,
        )
        # DEBUG: 确认 finalize 写入的 record_file 和 result_data_path
        _final_out = final_algo_result.get('rounds', [{}])[0].get('output', {})
        self._log(
            level='DEBUG',
            content=f"[_finalize_rounds] result_id={result_id}, result_data_path={result_data_path!r}, output_keys={list(_final_out.keys())}, record_file={_final_out.get('record_file', '<MISSING>')!r}",
            task_id=task_id, test_case_id=test_case_id,
        )

        # 整体评估
        # 检查是否有评估维度（从 rounds[].evaluation.dimensions 读单轮维度，从 config.dimensions 读多轮维度）
        _has_dims = False
        if case_config:
            rounds = case_config.get('rounds', [])
            if rounds and isinstance(rounds, list):
                for round_item in rounds:
                    if isinstance(round_item, dict):
                        evaluation = round_item.get('evaluation', {})
                        if isinstance(evaluation, dict) and evaluation.get('dimensions'):
                            _has_dims = True
                            break
            if not _has_dims and case_config.get('dimensions'):
                _has_dims = True

        if execution_success and _has_dims:
            _dims_log = json.dumps(
                case_config.get('rounds', [{}])[0].get('evaluation', {}).get('dimensions', []),
                ensure_ascii=False
            )[:200] if case_config.get('rounds') else json.dumps(case_config.get('dimensions', []), ensure_ascii=False)[:200]
            self._log(
                level='INFO',
                content=f"提交整体评估: result_id={result_id}, dimensions={_dims_log}",
                task_id=task_id, test_case_id=test_case_id,
            )
            self._evaluate_result(
                task_id=task_id, result_id=result_id, test_case_id=test_case_id,
                algo_result=final_algo_result, case_config=case_config or {},
                case_reference_params=case_reference_params,
                algorithm_type=algorithm_type, test_type='e2e',
                case_algorithm_params=data.get('case_algorithm_params'),
                round_number=None,
                reference_params_col=data.get('reference_params_col')
            )

        # 聚合各轮评估分数到 algo_result
        self._aggregator.update_algorithm_result_evaluation(task_id, result_id)

        # 更新 TaskCase 状态
        success = self._aggregator.process_results(
            task_id, case_name, tc_rel_id, test_case_id, all_round_results, case_config,
            case_reference_params=case_reference_params,
            case_algorithm_params=data.get('case_algorithm_params'),
            algorithm_type=algorithm_type,
            adjusted_case_reference_params=last_adjusted_ref_params,
            precreated_result_id=result_id,
            precomputed_execution_success=execution_success
        )

        return success

    def _process_results_base(self, **kwargs):
        """委托到 BaseExecutor._process_results，供 E2EAggregator 调用"""
        return super()._process_results(**kwargs)
