import json
import copy

from shared.infrastructure.base_executor import TaskStopSignal, EvaluationSubmitError
from shared.utils.result_data_store import write_result_data_file
from shared.utils.status_constants import ExecutionStatus, RESULT_TYPE_FINAL
from e2e_test_service.domain.services import E2ECalculationService
from e2e_test_service.infrastructure.acl import (
    DeviceAclRepositoryImpl,
    DeviceResultAclRepositoryImpl,
)
from shared.utils.dto_utils import dto_to_dict
from shared.models.common_enums import DeviceType


class FinalizationMixin:
    """阶段三：循环后聚合 + 评估 —— 构建最终 algo_result，提交整体评估，聚合维度分数"""

    def _finalize_rounds(self, task_id, tc_rel_id, data, case_config, case_name,
                         algorithm_type, test_case_id, result_ids,
                         all_round_results, execution_success,
                         case_reference_params, last_adjusted_ref_params,
                         device_info_list=None, tc_rel_ids=None):
        """逐设备构建最终 algo_result、提交整体评估并回写对应路由行状态

        组执行时一次播放驱动多台设备，但评估按路由行逐行收口：
        每台设备一条 TestResult（evaluation_service 按 results_by_device[row.device_id]
        取结果），因此聚合/评估/回写都必须按设备分别执行。
        """
        tc_rel_ids = tc_rel_ids or {}
        device_info_by_id = {
            int(info.get('device_id')): info
            for info in (device_info_list or []) if info.get('device_id')
        }
        grouped_results = self._group_results_by_device(all_round_results, result_ids)
        device_keys = list(result_ids.keys())
        any_success = False

        for device_index, device_key in enumerate(device_keys):
            result_id = result_ids.get(device_key)
            if result_id is None:
                self._log(level='WARNING',
                          content=f"设备 {device_key} 缺少预创建结果行，跳过收口",
                          task_id=task_id, test_case_id=test_case_id)
                continue
            device_info = device_info_by_id.get(device_key)
            # 逐轮原始结果：保持独立，仅用于持久化 raw_results_list / 逐轮评估 / 状态收口
            device_results = list(grouped_results.get(device_key, []))
            # 该设备本轮无结果 → 该设备失败（不能沿用组级 success 强判成功）
            device_success = bool(execution_success and device_results)
            row_id = tc_rel_ids.get(device_key, tc_rel_id)
            is_last_device = device_index == len(device_keys) - 1

            # 多轮 + 多轮评估维度且驱动覆写 get_final_results 时，按 (device_sn, 'final')
            # 独立取最终聚合结果；命中则替代逐轮结果构建最终 algo_result（不改动原始逐轮数据）
            build_results = self._maybe_fetch_final_results(
                task_id, data, case_config, device_results, test_case_id,
                [device_info] if device_info else None,
                algorithm_type=algorithm_type,
            )

            # 构建该设备的最终 algo_result
            final_algo_result = self._aggregator.build_algorithm_result(
                task_id, build_results, case_config, algorithm_type)

            # INT-296：UI 抓取层降级（explicit_degrade）留痕合并到最终记录各轮
            #（build_algorithm_result 从原始结果重建，不含 round_data 上的标记），严禁无痕跳过
            _ui_note = getattr(self, '_ui_capture_degraded_note', None)
            if _ui_note:
                for _round_entry in final_algo_result.get('rounds', []):
                    _round_entry.setdefault('ui_capture', _ui_note)

            # 持久化该设备 raw_results 到文件，供重新评估时重新映射字段
            result_data_to_save = {
                'multi_round': True,
                'total_rounds': len(device_results),
                'raw_results_list': copy.deepcopy(device_results),
            }
            if last_adjusted_ref_params:
                result_data_to_save['adjusted_reference_params'] = last_adjusted_ref_params
            device_sn = (device_results[0].get('device_sn', '') if device_results
                         else (device_info or {}).get('device_sn', ''))
            result_data_path = write_result_data_file(
                task_id, test_case_id, device_sn, result_data_to_save)

            avg_response_time = E2ECalculationService.calculate_avg_latency(device_results)

            self._aggregator.update_test_result(
                result_id=result_id, algo_result=final_algo_result,
                execution_status=ExecutionStatus.COMPLETED if device_success else ExecutionStatus.FAILED,
                response_time=avg_response_time,
                error_message=None if device_success else "多轮测试存在失败轮次",
                task_id=task_id,
                result_data_path=result_data_path or None,
            )
            _final_out = final_algo_result.get('rounds', [{}])[0].get('output', {})
            self._log(
                level='DEBUG',
                content=(f"[_finalize_rounds] device_id={device_key}, result_id={result_id}, "
                         f"result_data_path={result_data_path!r}, output_keys={list(_final_out.keys())}, "
                         f"record_file={_final_out.get('record_file', '<MISSING>')!r}"),
                task_id=task_id, test_case_id=test_case_id,
            )

            # 整体评估 / 聚合触发条件（对齐评估维度隔离设计文档与 V9.7.10 e2e_executor）：
            # _has_round_dims: 任一轮配置了 evaluation.dimensions（enabled 非 False）→ 需要聚合各轮分数
            # _has_overall_dims: 顶层 config.dimensions 非空 → 才提交 round_number=None 的整体评估
            #   （整体评估只取顶层维度；仅有轮次维度时提交整体评估会在评估入口因无维度被跳过）
            _has_round_dims = False
            if case_config:
                rounds = case_config.get('rounds', [])
                if rounds and isinstance(rounds, list):
                    for round_item in rounds:
                        if isinstance(round_item, dict):
                            evaluation = round_item.get('evaluation', {})
                            if isinstance(evaluation, dict):
                                if evaluation.get('enabled', True) is False:
                                    continue
                                if evaluation.get('dimensions'):
                                    _has_round_dims = True
                                    break
            _has_overall_dims = bool(case_config.get('dimensions')) if case_config else False

            # INT-2285：本用例是否真的有评估提交。逐轮评估在上面的轮次循环里按
            # _has_round_dims 提交、整体评估按 _has_overall_dims 提交；两者皆无
            # （评测关闭 / 无维度）时评估永远不会回调，收口必须就地把评估状态
            # 补写终态，否则 TaskCase 停留 evaluating、任务执行完成后不收敛。
            _evaluation_expected = _has_overall_dims or _has_round_dims

            # 停止/暂停检查：任务已停则跳过整体评估提交（评估耗时较长），仅完成结果落库与状态收尾
            _stopped = False
            try:
                self._handle_control(task_id)
            except TaskStopSignal:
                _stopped = True
                self._log(level='INFO',
                          content='任务已停止，跳过整体评估提交，仅完成结果落库',
                          task_id=task_id, test_case_id=test_case_id)

            if device_success and _has_overall_dims and not _stopped:
                _dims_log = json.dumps(case_config.get('dimensions', []), ensure_ascii=False)[:200]
                self._log(
                    level='INFO',
                    content=(f"提交整体评估: device_id={device_key}, result_id={result_id}, "
                             f"dimensions={_dims_log}"),
                    task_id=task_id, test_case_id=test_case_id,
                )
                # INT-169: 整体评估提交失败不中止收尾链（聚合/TaskCase 状态照常）
                try:
                    self._evaluate_result(
                        task_id=task_id, result_id=result_id, test_case_id=test_case_id,
                        algo_result=final_algo_result, case_config=case_config or {},
                        case_reference_params=case_reference_params,
                        algorithm_type=algorithm_type, device_type=DeviceType.PHYSICAL.value,
                        case_algorithm_params=data.get('case_algorithm_params'),
                        algorithm_params_col=data.get('algorithm_params_col'),
                        round_number=None,
                        reference_params_col=data.get('reference_params_col')
                    )
                except EvaluationSubmitError as e:
                    self._record_eval_submit_failure(
                        f"整体评估提交失败(device_id={device_key}): {e}",
                        task_id=task_id, test_case_id=test_case_id)

            # 聚合各轮评估分数到 algo_result（仅当有单轮评估维度且未停止时才执行）
            if _has_round_dims and not _stopped:
                self._aggregator.update_algorithm_result_evaluation(task_id, result_id)

            # 更新 TaskCase 状态（按路由行精确回写；事件仅组内最后一台发布）
            row_success = self._aggregator.process_results(
                task_id, case_name, row_id, test_case_id, device_results, case_config,
                case_reference_params=case_reference_params,
                case_algorithm_params=data.get('case_algorithm_params'),
                algorithm_params_col=data.get('algorithm_params_col'),
                algorithm_type=algorithm_type,
                adjusted_case_reference_params=last_adjusted_ref_params,
                precreated_result_id=result_id,
                precomputed_execution_success=device_success,
                publish_event=is_last_device,
                evaluation_expected=_evaluation_expected,
            )
            any_success = any_success or bool(row_success)

        return any_success

    @staticmethod
    def _group_results_by_device(all_round_results, result_ids):
        """按设备归属拆分扁平结果列表（device_id 优先；单设备时回落唯一键）。"""
        grouped = {}
        for result in all_round_results:
            raw_device_id = result.get('device_id')
            device_key = None
            if raw_device_id not in (None, ''):
                try:
                    device_key = int(raw_device_id)
                except (TypeError, ValueError):
                    device_key = None
            if device_key not in result_ids:
                if len(result_ids) == 1:
                    device_key = next(iter(result_ids))
                else:
                    continue
            grouped.setdefault(device_key, []).append(result)
        return grouped

    def _process_results_base(self, **kwargs):
        """委托到 BaseExecutor._process_results，供 E2EAggregator 调用"""
        return super()._process_results(**kwargs)

    def _maybe_fetch_final_results(self, task_id, data, case_config,
                                    device_results, test_case_id,
                                    device_info_list=None,
                                    algorithm_type=None):
        """多轮且配置了多轮评估维度时，按 (device_sn, 'final') 独立获取驱动最终聚合结果

        条件：rounds 数量 > 1 且 case_config.dimensions 中存在 round_scope='multi' 的维度。
        满足条件时对每台设备调用 driver.get_final_results：
        - 返回非空 → 按文档 23 §6「以驱动最终结果替代逐轮聚合」返回最终结果列表；
          每条补齐 device_sn / device_id / 整数 round_number / result_type='final'，
          并走 convert_results 字段映射（失败回退原始结构），保证
          build_algorithm_result 与整体评估可用；
        - 返回空 / 异常 → 该设备沿用逐轮结果。
        逐轮原始结果不在本方法内修改（调用方单独持久化到 raw_results_list），
        避免最终结果覆盖逐轮数据，也避免 round_number=None 混入逐轮列表
        导致 build_algorithm_result 排序/索引异常。
        """
        if not case_config:
            return device_results

        rounds = case_config.get('rounds', [])
        multi_dims = [
            d for d in (case_config.get('dimensions') or [])
            if isinstance(d, dict) and d.get('round_scope') == 'multi'
        ]
        if len(rounds) <= 1 or not multi_dims:
            return device_results

        if not device_info_list:
            return device_results

        self._log(
            level='INFO',
            content=f"多轮+多轮评估维度，开始获取最终聚合结果: "
                    f"rounds={len(rounds)}, multi_dims={len(multi_dims)}, "
                    f"devices={len(device_info_list)}",
            task_id=task_id, test_case_id=test_case_id,
        )

        device_repo = DeviceAclRepositoryImpl()
        final_results = []
        for info in device_info_list:
            device_sn = info.get('device_sn')
            if not device_sn:
                continue
            device_config = {
                'action': 'get_final_results',
                'device_sn': device_sn,
                # 同 SN 多 App 时驱动定位依赖元数据，不得只靠 SN
                'system': info.get('system'),
                'keywords': info.get('keywords'),
                'kwargs': {
                    'round_count': len(rounds),
                    'all_round_results': device_results,
                },
            }
            try:
                fetched = device_repo.get_final_results(task_id, device_config)
            except Exception as e:
                self._log(
                    level='WARNING',
                    content=f"设备 {device_sn} 获取最终结果失败（沿用逐轮结果）: {e}",
                    task_id=task_id, test_case_id=test_case_id,
                )
                continue
            if not fetched:
                continue

            normalized = [dto_to_dict(fr) for fr in fetched]
            normalized = [item for item in normalized if item]
            if not normalized:
                continue
            if algorithm_type:
                try:
                    converted = DeviceResultAclRepositoryImpl().convert_results(
                        normalized, algorithm_type)
                    converted_dicts = [dto_to_dict(item) for item in (converted or [])]
                    converted_dicts = [item for item in converted_dicts if item]
                    if converted_dicts:
                        normalized = converted_dicts
                except Exception as e:
                    self._log(
                        level='WARNING',
                        content=f"设备 {device_sn} 最终结果字段映射失败（沿用原始结构）: {e}",
                        task_id=task_id, test_case_id=test_case_id,
                    )

            for idx, fr_dict in enumerate(normalized):
                fr_dict.setdefault('device_sn', device_sn)
                fr_dict.setdefault('device_id', info.get('device_id'))
                fr_dict['round_number'] = self._safe_round_index(
                    fr_dict.get('round_number'), idx)
                fr_dict.setdefault('result_type', RESULT_TYPE_FINAL)

            self._log(
                level='INFO',
                content=f"设备 {device_sn} 最终结果获取成功: {len(normalized)} 条（替代逐轮聚合）",
                task_id=task_id, test_case_id=test_case_id,
            )
            final_results.extend(normalized)

        return final_results or device_results

    @staticmethod
    def _safe_round_index(value, default):
        """把驱动返回的 round_number 规整为非负整数（None/非法 → 默认序号）。

        build_algorithm_result 按 round_number 分组并排序，None/字符串会与整数
        混排抛 TypeError，因此这里统一收口。
        """
        if isinstance(value, bool):
            return default
        try:
            index = int(value)
        except (TypeError, ValueError):
            return default
        return index if index >= 0 else default
