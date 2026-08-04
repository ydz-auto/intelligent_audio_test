# -*- coding: utf-8 -*-
"""RoundEvaluationMixin - 提供 rounds-as-top-level 架构的轮次级评估参数提取

拆分自原 case_parameter_extractor.py 的 CaseParameterExtractor：
- get_round_evaluation_params
"""

from typing import Dict, Any

from ..reference_params_generator import (
    get_reference_value as gen_reference_value,
)
from shared.utils.log_handler import log_not_emit
from ._helpers import (
    _get_round_algo_params,
    _normalize_algorithm_params,
)


class RoundEvaluationMixin:
    """轮次级评估参数提取 mixin（rounds-as-top-level 架构）"""

    @classmethod
    def get_round_evaluation_params(
        cls,
        algorithm_type: str,
        round_config: Dict,
        algorithm_params_col,
        reference_params_col,
        algorithm_result: Dict[str, Any] = None,
        test_type: str = 'api'
    ) -> Dict[str, Any]:
        """提取单轮评估参数（rounds-as-top-level 架构）

        新设计下算法参数和参考参数从 test_cases 表独立列按轮读取：
        - algorithm_params_col: [{round_number, params:[{field_code, field_value}]}]
        - reference_params_col: [{round_number, reference_params_path}]

        兼容旧格式：若 algorithm_params_col 为 None 且 round_config 内含 algorithmParams，
        则走旧逻辑从 round_config 读取。

        Args:
            algorithm_type: 算法类型
            round_config: 单轮配置 dict（含 roundNumber 等结构性字段）
            algorithm_params_col: 算法参数独立列（按轮分组）
            reference_params_col: 参考参数独立列（按轮分组）
            algorithm_result: 算法执行结果（可选）
            test_type: 测试类型 ('api' 或 'e2e')
        """
        if algorithm_type == 'unknown':
            return {}

        loader = cls._get_loader()
        mappings = loader.get_param_mapping(algorithm_type, 'evaluation')
        if not mappings:
            log_not_emit('WARNING', 'case_parameter_extractor',
                         f'No evaluation mappings for {algorithm_type}', category='algorithm')
            return {}

        # 获取轮次序号，兼容 roundNumber / round_number 两种键
        round_number = round_config.get('roundNumber')
        if round_number is None:
            round_number = round_config.get('round_number')

        # 读取算法参数：优先从独立列按轮取，兼容旧格式
        if algorithm_params_col is not None:
            algo_params = _get_round_algo_params(algorithm_params_col, round_number)
        else:
            # 兼容旧格式：round_config.algorithmParams
            algo_params = round_config.get('algorithmParams', [])
        algo_dict = _normalize_algorithm_params(algo_params)

        # 加载参考参数文件：优先从独立列按轮取，兼容旧格式
        if reference_params_col is not None:
            ref_file_data = cls._load_round_ref_file(reference_params_col, round_number)
        else:
            # 兼容旧格式：round_config.referenceParamsPath
            ref_file_data = cls._load_ref_file(round_config.get('referenceParamsPath'))
        reference_params_list = list(ref_file_data.values()) if ref_file_data else []

        if algorithm_result is None:
            algorithm_result = {}
        adjusted_reference_params = algorithm_result.get('adjusted_reference_params', [])

        eval_params = {}
        eval_params['round_number'] = round_number

        for m in mappings:
            source = m.get('source', 'api')
            source_param = m['source_param']
            target_param = m['target_param']
            value = None

            if source == 'case':
                value = algo_dict.get(source_param)
            elif source == 'reference':
                ref_type = None
                for ref_def in loader.get_reference_params(algorithm_type):
                    if ref_def.get('code') == source_param:
                        ref_type = ref_def.get('type')
                        break
                for param in reference_params_list:
                    if isinstance(param, dict) and param.get('code') == source_param:
                        value = gen_reference_value(
                            param, test_type, ref_type,
                            algorithm_type=algorithm_type,
                            case_config=algo_dict
                        )
                        break
            elif source in ('device', 'api'):
                value = algorithm_result.get(source_param)
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
                                        value = {'text': text, 'json': json_data}
                                elif isinstance(ref_value, str):
                                    value = {'text': ref_value, 'json': []}
                            break

            if value is not None:
                eval_params[target_param] = value

        # 轮次级额外信息
        eval_params['algorithm_params'] = algo_params
        return eval_params
