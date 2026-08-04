# -*- coding: utf-8 -*-
"""EvaluationParamsMixin - 提供评估参数构建（平面/轮次兼容入口）

拆分自原 case_parameter_extractor.py 的 CaseParameterExtractor：
- get_evaluation_params
- _build_evaluation_params
"""

from typing import Dict, List, Any

from ..reference_params_generator import (
    get_reference_value as gen_reference_value,
    normalize_reference_params,
)
from shared.utils.log_handler import log_not_emit
from ._helpers import (
    _normalize_algorithm_params,
)


class EvaluationParamsMixin:
    """评估参数构建 mixin（平面格式入口，兼容 rounds 顶层结构）"""

    @classmethod
    def get_evaluation_params(
        cls,
        case_config: Dict,
        dimension_ids: List[int] = None,
        algorithm_result: Dict[str, Any] = None,
        test_type: str = 'api'
    ) -> Dict[str, Any]:
        """获取评估参数

        Args:
            case_config: 用例配置
            dimension_ids: 评估维度ID列表
            algorithm_result: 算法执行结果（可选，用于从device/api来源获取值）
            test_type: 测试类型 ('api' 或 'e2e')
        """
        algorithm_type = cls.get_algorithm_type(case_config)
        if algorithm_type == 'unknown':
            log_not_emit('WARNING', 'case_parameter_extractor', 'Cannot get evaluation params: algorithm_type is unknown', category='algorithm')
            return {}

        loader = cls._get_loader()
        mappings = loader.get_param_mapping(algorithm_type, 'evaluation')
        if not mappings:
            log_not_emit('WARNING', 'case_parameter_extractor', f'No evaluation mappings found for algorithm: {algorithm_type}', category='algorithm')
            return {}

        log_not_emit('DEBUG', 'case_parameter_extractor', f'get_evaluation_params: algorithm_type={algorithm_type}, mappings_count={len(mappings)}', category='algorithm')

        result = cls._build_evaluation_params(
            algorithm_type, case_config, mappings, dimension_ids, algorithm_result, test_type
        )
        log_not_emit('DEBUG', 'case_parameter_extractor', f'Built evaluation params for {algorithm_type}: keys={list(result.keys())}', category='algorithm')
        return result

    @classmethod
    def _build_evaluation_params(
        cls,
        algorithm_type: str,
        case_config: Dict,
        mappings: List[Dict],
        dimension_ids: List[int] = None,
        algorithm_result: Dict[str, Any] = None,
        test_type: str = 'api'
    ) -> Dict[str, Any]:
        """构建评估参数

        兼容两种数据来源：
        - 新格式：case_config 含 rounds（结构性字段），算法参数/参考参数从独立列
          algorithm_params_col / reference_params_col 按轮读取（取 rounds[0] 的 round_number）
        - 旧平面格式：case_config.algorithm_params / case_config.reference_params 直接读取

        Args:
            algorithm_type: 算法类型
            case_config: 用例配置
            mappings: 评估参数映射
            dimension_ids: 评估维度ID列表
            algorithm_result: 算法执行结果（可选）
            test_type: 测试类型 ('api' 或 'e2e')
        """
        eval_params = {}
        # 新格式：rounds 顶层存在时，从独立列按轮取参数
        rounds = case_config.get('rounds')
        algorithm_params_col = case_config.get('algorithm_params_col')
        reference_params_col = case_config.get('reference_params_col')

        if rounds and isinstance(rounds, list) and len(rounds) > 0:
            round_number = rounds[0].get('roundNumber') or rounds[0].get('round_number')
            # 优先从独立列按轮取
            if algorithm_params_col is not None:
                case_params = cls.get_round_algorithm_params(algorithm_params_col, round_number)
            else:
                # 兼容：独立列缺失但 round 内仍保留 algorithmParams
                case_params = _normalize_algorithm_params(rounds[0].get('algorithmParams', []))
            if reference_params_col is not None:
                ref_file_data = cls._load_round_ref_file(reference_params_col, round_number)
                # _load_round_ref_file 返回 dict {code: item}，转为 list 以兼容后续流程
                raw_reference_params = list(ref_file_data.values()) if ref_file_data else []
            else:
                # 兼容：旧平面格式
                raw_reference_params = case_config.get('reference_params', [])
        else:
            # 旧平面格式
            case_params = _normalize_algorithm_params(case_config.get('algorithm_params', {}))
            raw_reference_params = case_config.get('reference_params', [])
        reference_params = normalize_reference_params(raw_reference_params, test_type)

        if algorithm_result is None:
            algorithm_result = {}

        adjusted_reference_params = algorithm_result.get('adjusted_reference_params', [])

        for m in mappings:
            source = m.get('source', 'api')
            if dimension_ids and m.get('dimension_id') not in dimension_ids:
                continue
            source_param = m['source_param']
            target_param = m['target_param']
            value = None

            if source == 'case':
                value = case_params.get(source_param)
            elif source == 'reference':
                if reference_params:
                    ref_type = None
                    loader = cls._get_loader()
                    for ref_def in loader.get_reference_params(algorithm_type):
                        if ref_def.get('code') == source_param:
                            ref_type = ref_def.get('type')
                            break
                    for param in reference_params:
                        if param.get('code') == source_param:
                            if isinstance(param, dict):
                                value = gen_reference_value(
                                    param, test_type, ref_type,
                                    algorithm_type=algorithm_type,
                                    case_config=case_params
                                )
                                log_not_emit('DEBUG', 'case_parameter_extractor', f'[get_evaluation_params] source_param={source_param}, ref_type={ref_type}, value={value}, value_type={type(value)}', category='algorithm')
                            break
            elif source in ('device', 'api'):
                value = algorithm_result.get(source_param)
                # rounds 结构：顶层没有设备输出字段时，从 rounds[0].output 取
                # output 的 key 是 target_param 名（build_algorithm_result 已映射）
                if value is None and isinstance(algorithm_result, dict):
                    rounds_data = algorithm_result.get('rounds', [])
                    if rounds_data and isinstance(rounds_data[0], dict):
                        output = rounds_data[0].get('output', {})
                        value = output.get(target_param)
            elif source == 'adjusted_reference':
                if adjusted_reference_params:
                    for ref_param in adjusted_reference_params:
                        if ref_param.get('code') == source_param:
                            ref_value = ref_param.get('value')
                            if ref_value:
                                if isinstance(ref_value, dict):
                                    text = ref_value.get('text', '')
                                    json_data = ref_value.get('json', ref_value.get('segments', []))
                                    if text or json_data:
                                        value = {
                                            'text': text,
                                            'json': json_data
                                        }
                                        log_not_emit('DEBUG', 'case_parameter_extractor', f'[get_evaluation_params] from adjusted_reference: source_param={source_param}, text_len={len(text) if text else 0}, json_count={len(json_data) if isinstance(json_data, list) else 0}', category='algorithm')
                                elif isinstance(ref_value, str):
                                    value = {
                                        'text': ref_value,
                                        'json': []
                                    }
                            break

            if value is not None:
                eval_params[target_param] = value

        if dimension_ids:
            eval_params['dimension_ids'] = dimension_ids

        return eval_params
