import json
import copy

from shared.utils.result_data_store import write_result_data_file
from e2e_test_service.domain.services import E2ECalculationService
from e2e_test_service.infrastructure.acl import DeviceAclRepositoryImpl
from shared.utils.dto_utils import dto_to_dict


class FinalizationMixin:
    """阶段三：循环后聚合 + 评估 —— 构建最终 algo_result，提交整体评估，聚合维度分数"""

    def _finalize_rounds(self, task_id, tc_rel_id, data, case_config, case_name,
                         algorithm_type, test_case_id, result_id,
                         all_round_results, execution_success,
                         case_reference_params, last_adjusted_ref_params,
                         device_info_list=None):
        """构建最终 algo_result，提交整体评估，聚合维度分数，更新 TaskCase 状态"""
        # 多轮且有配置多轮评估维度时，获取最终聚合结果
        all_round_results = self._maybe_fetch_final_results(
            task_id, data, case_config, all_round_results, test_case_id,
            device_info_list
        )

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

        avg_response_time = E2ECalculationService.calculate_avg_latency(all_round_results)

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

    def _maybe_fetch_final_results(self, task_id, data, case_config,
                                    all_round_results, test_case_id,
                                    device_info_list=None):
        """多轮且配置了多轮评估维度时，调用驱动层获取最终聚合结果并合并

        条件：rounds 数量 > 1 且 case_config.dimensions 中存在 round_scope='multi' 的维度。
        满足条件时，对每个设备调用 driver.get_final_results，将返回的最终结果
        追加到 all_round_results 中（result_type 标记为 'final'）。
        不满足条件或无结果时直接返回原 all_round_results。
        """
        if not case_config:
            return all_round_results

        rounds = case_config.get('rounds', [])
        multi_dims = [
            d for d in (case_config.get('dimensions') or [])
            if isinstance(d, dict) and d.get('round_scope') == 'multi'
        ]
        if len(rounds) <= 1 or not multi_dims:
            return all_round_results

        if not device_info_list:
            return all_round_results

        self._log(
            level='INFO',
            content=f"多轮+多轮评估维度，开始获取最终聚合结果: "
                    f"rounds={len(rounds)}, multi_dims={len(multi_dims)}, "
                    f"devices={len(device_info_list)}",
            task_id=task_id, test_case_id=test_case_id,
        )

        device_repo = DeviceAclRepositoryImpl()
        for info in device_info_list:
            device_sn = info.get('device_sn')
            if not device_sn:
                continue
            device_config = {
                'action': 'get_final_results',
                'device_sn': device_sn,
                'kwargs': {
                    'round_count': len(rounds),
                    'all_round_results': all_round_results,
                },
            }
            try:
                final_results = device_repo.get_final_results(task_id, device_config)
                if final_results:
                    self._log(
                        level='INFO',
                        content=f"设备 {device_sn} 最终结果获取成功: {len(final_results)} 条",
                        task_id=task_id, test_case_id=test_case_id,
                    )
                    for fr in final_results:
                        fr_dict = dto_to_dict(fr)
                        if fr_dict:
                            fr_dict.setdefault('device_sn', device_sn)
                            fr_dict.setdefault('round_number', None)
                            all_round_results.append(fr_dict)
            except Exception as e:
                self._log(
                    level='WARNING',
                    content=f"设备 {device_sn} 获取最终结果失败（忽略）: {e}",
                    task_id=task_id, test_case_id=test_case_id,
                )

        return all_round_results
