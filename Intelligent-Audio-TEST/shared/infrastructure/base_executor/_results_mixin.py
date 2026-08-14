# -*- coding: utf-8 -*-
"""测试结果处理与评估提交"""
import json
import copy


class ResultsMixin:
    """执行器基类结果处理与评估方法"""

    def _evaluate_result(self, task_id, result_id, test_case_id, algo_result,
                         case_config, case_reference_params, algorithm_type,
                         test_type='e2e', case_algorithm_params=None,
                         reference_params_col=None, round_number=None, **kwargs):
        """评估测试结果（通过 gRPC 调用 evaluation_service.EvaluateCase）

        依赖通过抽象方法注入：
        - _get_algorithm_acl(): 返回 algorithm_service ACL 仓储
        - _get_task_data_acl(): 返回 task_service ACL 仓储（含 submit_evaluate_case 代理）
        """
        from shared.utils.dto_utils import dto_to_dict
        from shared.utils.grpc_json import dumps as _dumps

        if isinstance(case_reference_params, list):
            ref_params_dict = {}
            for item in case_reference_params:
                code = item.code if hasattr(item, 'code') else item.get('code')
                val = item.value if hasattr(item, 'value') else item.get('value')
                if code:
                    ref_params_dict[code] = val
            case_reference_params = ref_params_dict
        elif case_reference_params and hasattr(case_reference_params, '__dict__'):
            case_reference_params = dto_to_dict(case_reference_params)

        if isinstance(algo_result, str):
            try:
                algo_result = json.loads(algo_result)
            except (json.JSONDecodeError, TypeError):
                algo_result = {}

        full_case_params = {
            'algorithm_type': algorithm_type,
            'algorithm_params': case_algorithm_params or {},
            'reference_params': case_reference_params or {},
            'reference_params_col': reference_params_col,
        }

        algo_acl = self._get_algorithm_acl()
        eval_params = algo_acl.extract_case_all_params(full_case_params)
        if hasattr(eval_params, '__dict__'):
            eval_params = dto_to_dict(eval_params)
        eval_params = (eval_params.get('evaluation', {}) or {}) if isinstance(eval_params, dict) else {}

        eval_params['algorithm_type'] = algorithm_type
        eval_params['test_type'] = test_type
        if round_number is not None:
            eval_params['round_number'] = round_number
        if reference_params_col is not None:
            eval_params['reference_params_col'] = reference_params_col

        self._log(
            level='DEBUG',
            content=f"[_evaluate_result] 调用评估服务(通过ACL) task_id={task_id}, result_id={result_id}, eval_params={json.dumps(eval_params, ensure_ascii=False, indent=2)[:500]}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        # 通过 ACL 仓储调用 evaluation_service 的 EvaluateCase
        self._get_task_data_acl().submit_evaluate_case(
            task_id=task_id,
            result_id=result_id,
            test_case_id=test_case_id,
            algorithm_result=algo_result,
            **eval_params,
        )

        self._log(
            level='INFO',
            content=f"评估已提交: task_id={task_id}, result_id={result_id}",
            task_id=task_id,
            test_case_id=test_case_id
        )

    def _process_results_base(self, task_id, test_case_id, all_results, case_config,
                              case_reference_params, algorithm_type,
                              device_id_field='device_id', api_id_field='api_id'):
        """处理测试结果基类方法"""
        from shared.utils.dto_utils import dto_to_dict

        if isinstance(case_reference_params, list):
            ref_params_dict = {}
            for item in case_reference_params:
                code = item.code if hasattr(item, 'code') else item.get('code')
                val = item.value if hasattr(item, 'value') else item.get('value')
                if code:
                    ref_params_dict[code] = val
            case_reference_params = ref_params_dict
        elif case_reference_params and hasattr(case_reference_params, '__dict__'):
            case_reference_params = dto_to_dict(case_reference_params)

        if not all_results:
            return {'execution_success': False, 'all_eval_items': [], 'case_params': {}}

        mapper = self._get_result_mapper()
        converted = mapper.convert_results(all_results, algorithm_type)

        algo_acl = self._get_algorithm_acl()
        output_keys = _get_algorithm_output_keys(algorithm_type, algo_acl)

        all_eval_items = []
        execution_success = True
        case_params = case_config.copy() if isinstance(case_config, dict) else {}

        for result_item in converted:
            res = result_item.get('raw_results', result_item) if isinstance(result_item, dict) else {}
            if not isinstance(res, dict):
                res = {}

            success = res.get('success', True)

            mapped_output_keys = _get_mapped_device_output_field_keys(algorithm_type, algo_acl)
            ref_fields = _build_ref_fields({
                'case_reference_params': case_reference_params,
                'output_keys': output_keys,
                'mapped_output_keys': mapped_output_keys,
            })

            log_content = mapper.build_case_result_log(
                algorithm_type, res, ref_fields,
                task_id=task_id, test_case_id=test_case_id
            )

            self._log(
                level='INFO' if success else 'WARNING',
                content=log_content,
                task_id=task_id,
                test_case_id=test_case_id,
                device_id=res.get('device_id'),
                api_id=res.get('api_id')
            )

            if not success:
                execution_success = False

            all_eval_items.append({
                'res': res,
                'test_case_id': test_case_id,
                'result_id': result_item.get('result_id') if isinstance(result_item, dict) else None,
            })

        return {
            'execution_success': execution_success,
            'all_eval_items': all_eval_items,
            'case_params': case_params,
        }

    def _log_case_result(self, task_id, case_name, res, ref_fields, algorithm_type, test_case_id=None):
        """记录用例结果日志"""
        mapper = self._get_result_mapper()
        log_content = mapper.build_case_result_log(
            algorithm_type, res, ref_fields,
            task_id=task_id, test_case_id=test_case_id
        )
        self._log(
            level='INFO',
            content=log_content,
            task_id=task_id,
            test_case_id=test_case_id,
            device_id=res.get('device_id'),
            api_id=res.get('api_id')
        )


def _get_algorithm_output_keys(algorithm_type, algo_acl=None):
    """从算法配置派生 output_keys

    Args:
        algorithm_type: 算法类型
        algo_acl: algorithm_service ACL 仓储（由调用方注入）
    """
    output_keys = {}
    if algo_acl is None:
        from shared.clients.grpc_clients import (
            algo_get_device_params as _get_dev,
            algo_get_api_params as _get_api,
        )
        params = (_get_dev(algorithm_type) or []) + (_get_api(algorithm_type) or [])
    else:
        params = (algo_acl.get_device_params(algorithm_type) or []) + (algo_acl.get_api_params(algorithm_type) or [])
    for param in params:
        code = param.get('code', '')
        if 'direction' in code.lower():
            output_keys['direction'] = code
        elif 'source' in code.lower() and 'lang' in code.lower():
            output_keys['source_lang'] = code
        elif 'target' in code.lower() and 'lang' in code.lower():
            output_keys['target_lang'] = code
    return output_keys


def _get_mapped_device_output_field_keys(algorithm_type, algo_acl=None):
    """获取设备输出字段键列表（映射后）"""
    if algo_acl is None:
        from shared.clients.grpc_clients import algo_get_field_mappings
        field_defs = algo_get_field_mappings(algorithm_type)
    else:
        field_defs = algo_acl.get_field_mappings(algorithm_type)
    if not field_defs:
        return []
    return field_defs.get_mapped_device_output_field_keys(algorithm_type)


def _build_ref_fields(extra_params):
    """从 extra_params 提取 ref_fields"""
    def extract_value(val):
        if isinstance(val, dict) and 'value' in val:
            return val.get('value', '')
        return val

    ref_fields = {}
    for field_key, field_value in extra_params.items():
        if field_value:
            ref_fields[field_key] = extract_value(field_value)
    return ref_fields
