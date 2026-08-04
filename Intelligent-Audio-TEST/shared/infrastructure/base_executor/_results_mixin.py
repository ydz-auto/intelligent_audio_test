# -*- coding: utf-8 -*-
"""测试结果处理与评估提交"""
import json
import copy

from shared.algorithm.field_mapper import get_field_mapper
from shared.algorithm.algorithm_config_loader import get_config_loader


class ResultsMixin:
    """执行器基类结果处理与评估方法"""

    def _process_results(self, task_id, test_case_id, all_results, case_config=None,
                        case_reference_params=None, algorithm_type='translation',
                        device_id_field='device_id', api_id_field='api_id',
                        result_data_extra=None, **kwargs):
        """处理测试结果 - 通用方法"""
        self._log(
            level='DEBUG',
            content=f"[_process_results] 开始处理结果 task_id={task_id}, test_case_id={test_case_id}, algorithm_type={algorithm_type}, results_count={len(all_results) if all_results else 0}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        if case_config:
            self._log(
                level='DEBUG',
                content=f"[_process_results] case_config: {json.dumps(case_config, ensure_ascii=False, indent=2)[:500]}",
                task_id=task_id,
                test_case_id=test_case_id
            )

        if case_reference_params:
            self._log(
                level='DEBUG',
                content=f"[_process_results] case_reference_params: {json.dumps(case_reference_params, ensure_ascii=False, indent=2)[:500]}",
                task_id=task_id,
                test_case_id=test_case_id
            )

        adjusted_reference_params = None
        for res in all_results:
            if 'adjusted_reference_params' in res:
                adjusted_reference_params = res.get('adjusted_reference_params')
                if adjusted_reference_params:
                    self._log(
                        level='DEBUG',
                        content=f"[_process_results] 使用调整后的参考参数",
                        task_id=task_id,
                        test_case_id=test_case_id
                    )
                    case_reference_params = adjusted_reference_params
                break

        field_mapper = get_field_mapper()

        if result_data_extra is None:
            result_data_extra = {}

        if case_config:
            extra_config = field_mapper._get_algorithm_extra_config(algorithm_type)
            output_keys = extra_config.get('output_keys', {})
            for key, config_key in output_keys.items():
                if config_key not in result_data_extra and config_key in case_config:
                    result_data_extra[config_key] = case_config[config_key]

        config_loader = get_config_loader()
        all_results = copy.deepcopy(all_results)

        self._log(
            level='DEBUG',
            content=f"[_process_results] after deepcopy: all_results id={id(all_results)}, results_count={len(all_results)}, raw_keys[0]={list(all_results[0].get('raw_results', {}).keys())[:10] if all_results else 'empty'}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        self._log(
            level='DEBUG',
            content=f"[_process_results] before get_result_mapper: raw_keys[0]={list(all_results[0].get('raw_results', {}).keys())[:10]}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        collector = self._get_result_mapper()

        self._log(
            level='DEBUG',
            content=f"[_process_results] after get_result_mapper: raw_keys[0]={list(all_results[0].get('raw_results', {}).keys())[:10]}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        case_params = case_config or {}

        self._log(
            level='DEBUG',
            content=f"[_process_results] after case_params: raw_keys[0]={list(all_results[0].get('raw_results', {}).keys())[:10]}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        mapped_output_keys = field_mapper.get_mapped_device_output_field_keys(algorithm_type)

        self._log(
            level='DEBUG',
            content=f"[_process_results] after mapped_output_keys: raw_keys[0]={list(all_results[0].get('raw_results', {}).keys())[:10]}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        all_results = copy.deepcopy(all_results)

        self._log(
            level='DEBUG',
            content=f"[_process_results] after 2nd deepcopy: raw_keys[0]={list(all_results[0].get('raw_results', {}).keys())[:10]}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        self._log(
            level='DEBUG',
            content=f"[_process_results] before convert_results: all_results id={id(all_results)}, results_count={len(all_results)}, raw_keys[0]={list(all_results[0].get('raw_results', {}).keys())[:5] if all_results else 'empty'}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        all_results = collector.convert_results(all_results, algorithm_type)

        execution_success = True
        all_eval_items = []

        for res in all_results:
            raw_results = res.get('raw_results', {})
            success = raw_results.get('success', False)

            result_type = res.get('result_type', 'default')

            if not success:
                execution_success = False

            algo_result = {}
            for key in mapped_output_keys:
                if res.get(key):
                    algo_result[key] = res[key]

            result_data_to_save = res.copy()
            if result_type and result_type != 'default':
                result_data_to_save['result_type'] = result_type

            from shared.utils.result_data_store import write_result_data_file, split_result_data
            device_sn = res.get('device_sn', 'unknown')
            result_data_path = write_result_data_file(task_id, test_case_id, device_sn, result_data_to_save)
            lightweight_data, _ = split_result_data(result_data_to_save)

            result_id = self._save_result(
                task_id=task_id,
                test_case_id=test_case_id,
                result_data=lightweight_data,
                algo_result=algo_result,
                algorithm_type=algorithm_type,
                device_id=res.get(device_id_field),
                api_id=res.get(api_id_field),
                execution_status='completed' if success else 'failed',
                response_time=450 if success else 0,
                error_message=None if success else "采集结果失败",
                extra_data=result_data_extra,
                result_data_path=result_data_path
            )

            self._log(
                level='DEBUG',
                content=f"[_process_results] 保存结果 result_id={result_id}, result_type={result_type}, success={success}, device_id={res.get(device_id_field)}, api_id={res.get(api_id_field)}",
                task_id=task_id,
                test_case_id=test_case_id,
                device_id=res.get(device_id_field),
                api_id=res.get(api_id_field)
            )

            if algo_result:
                self._log(
                    level='DEBUG',
                    content=f"[_process_results] algo_result: {json.dumps(algo_result, ensure_ascii=False, indent=2)[:500]}",
                    task_id=task_id,
                    test_case_id=test_case_id,
                    device_id=res.get(device_id_field),
                    api_id=res.get(api_id_field)
                )

            if success:
                eval_item = {
                    'result_id': result_id,
                    'res': res,
                    'test_case_id': test_case_id
                }
                if 'round_number' in res:
                    eval_item['round_number'] = res['round_number']
                all_eval_items.append(eval_item)

        self._log(
            level='DEBUG',
            content=f"[_process_results] 处理完成 task_id={task_id}, test_case_id={test_case_id}, execution_success={execution_success}, eval_items_count={len(all_eval_items)}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        return {
            'execution_success': execution_success,
            'all_eval_items': all_eval_items,
            'case_params': case_params,
            'case_reference_params': case_reference_params,
            'algorithm_type': algorithm_type
        }

    def _evaluate_result(self, task_id, result_id, test_case_id, algo_result, case_config=None,
                        case_reference_params=None, algorithm_type='translation', test_type='api',
                        case_algorithm_params=None, round_number=None,
                        reference_params_col=None):
        """提交评估 - 通用方法

        迁移后改为通过 gRPC 调用 task_service 的 ExecutionService.EvaluateCase。
        """
        self._log(
            level='DEBUG',
            content=f"[DEBUG _evaluate_result] 传入参数: task_id={task_id}, result_id={result_id}, result_id_type={type(result_id)}, test_case_id={test_case_id}, algorithm_type={algorithm_type}, test_type={test_type}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        self._log(
            level='DEBUG',
            content=f"[_evaluate_result] 开始评估 task_id={task_id}, result_id={result_id}, test_case_id={test_case_id}, algorithm_type={algorithm_type}, test_type={test_type}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        if case_config:
            self._log(
                level='DEBUG',
                content=f"[_evaluate_result] case_config: {json.dumps(case_config, ensure_ascii=False, indent=2)[:500]}",
                task_id=task_id,
                test_case_id=test_case_id
            )

        if case_reference_params:
            self._log(
                level='DEBUG',
                content=f"[_evaluate_result] case_reference_params: {json.dumps(case_reference_params, ensure_ascii=False, indent=2)[:500]}",
                task_id=task_id,
                test_case_id=test_case_id
            )

        if case_algorithm_params:
            self._log(
                level='DEBUG',
                content=f"[_evaluate_result] case_algorithm_params: {json.dumps(case_algorithm_params, ensure_ascii=False, indent=2)[:500]}",
                task_id=task_id,
                test_case_id=test_case_id
            )

        if algo_result:
            self._log(
                level='DEBUG',
                content=f"[_evaluate_result] algo_result: {json.dumps(algo_result, ensure_ascii=False, indent=2)[:500]}",
                task_id=task_id,
                test_case_id=test_case_id
            )

        from shared.algorithm.case_parameter_extractor import CaseParameterExtractor

        case_params = case_config or {}
        algorithm_params = case_params.get('algorithm_params', case_params)

        if case_algorithm_params:
            if isinstance(case_algorithm_params, list):
                case_algorithm_params_dict = {}
                for item in case_algorithm_params:
                    if isinstance(item, dict) and 'field_code' in item:
                        case_algorithm_params_dict[item['field_code']] = item.get('field_value')
                case_algorithm_params = case_algorithm_params_dict

            if isinstance(algorithm_params, dict):
                algorithm_params = {**case_algorithm_params, **algorithm_params}
            else:
                algorithm_params = case_algorithm_params

        if case_reference_params:
            reference_params = case_reference_params
        else:
            reference_params = case_params.get('reference_params', {})

        full_case_params = {
            'algorithm_type': algorithm_type,
            'algorithm_params': algorithm_params,
            'reference_params': reference_params,
            'reference_params_col': reference_params_col,
            'rounds': case_config.get('rounds') if case_config else None,
        }

        self._log(
            level='DEBUG',
            content=f"[_evaluate_result] algorithm_params: {json.dumps(algorithm_params, ensure_ascii=False, indent=2)[:500]}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        self._log(
            level='DEBUG',
            content=f"[_evaluate_result] reference_params: {json.dumps(reference_params, ensure_ascii=False, indent=2)[:500]}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        eval_params = CaseParameterExtractor.get_evaluation_params(
            case_config=full_case_params,
            algorithm_result=algo_result,
            test_type=test_type
        )

        eval_params['algorithm_type'] = algorithm_type
        eval_params['test_type'] = test_type
        if round_number is not None:
            eval_params['round_number'] = round_number
        if reference_params_col is not None:
            eval_params['reference_params_col'] = reference_params_col

        self._log(
            level='DEBUG',
            content=f"[_evaluate_result] 调用评估服务(通过gRPC) task_id={task_id}, result_id={result_id}, eval_params={json.dumps(eval_params, ensure_ascii=False, indent=2)[:500]}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        # 通过 gRPC 调用 task_service 的 EvaluateCase
        from shared.clients.grpc_clients import submit_evaluate_case
        submit_evaluate_case(
            task_id=task_id,
            result_id=result_id,
            test_case_id=test_case_id,
            algorithm_result=algo_result,
            eval_params=eval_params,
        )

        self._log(
            level='DEBUG',
            content=f"[_evaluate_result] 评估已提交 task_id={task_id}, result_id={result_id}, test_case_id={test_case_id}",
            task_id=task_id,
            test_case_id=test_case_id
        )

    def _log_case_result(self, task_id, case_name, res, ref_fields=None, algorithm_type='translation', **kwargs):
        """记录用例结果日志 - 通用方法"""
        collector = self._get_result_mapper()

        log_content = f"用例 {case_name}: " + collector.build_case_result_log(algorithm_type, res, ref_fields, **kwargs)

        raw_results = res.get('raw_results', {})
        success = raw_results.get('success', False)
        test_case_id = kwargs.pop('test_case_id', None)

        self._log(
            level='INFO' if success else 'WARNING',
            content=log_content,
            task_id=task_id,
            test_case_id=test_case_id,
            device_id=res.get('device_id'),
            api_id=res.get('api_id')
        )
