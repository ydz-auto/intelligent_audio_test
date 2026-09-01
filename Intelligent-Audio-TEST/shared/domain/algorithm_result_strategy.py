# -*- coding: utf-8 -*-
"""算法结果处理策略 — 策略模式消除 algorithm_type 硬编码分支

将 voice_llm 等算法类型的特殊处理逻辑从各服务中抽取到统一策略接口，
消除 task_query_service / report_data_builder / result_field_mapping_queries
中分散的 if algorithm_type == 'voice_llm' 硬编码分支。
"""
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional


class AlgorithmResultStrategy(ABC):
    """算法结果处理策略接口"""

    @abstractmethod
    def get_output_fields(self, test_type: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """获取输出字段列表

        返回 None 表示该算法类型无特殊字段定义，调用方应使用默认仓库加载。
        """
        ...

    @abstractmethod
    def map_api_results(self, raw_results: Dict[str, Any], test_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """映射 API 结果到标准格式

        返回 None 表示该算法类型无特殊映射逻辑，调用方应使用默认字段映射。
        """
        ...

    @abstractmethod
    def process_algorithm_result(
        self,
        combined_data: Dict[str, Any],
        output_fields: List[Dict[str, Any]],
        resource: str,
        device_fields: Dict[str, str],
        algo_res: Optional[Dict[str, Any]] = None,
        result_data: Optional[Dict[str, Any]] = None,
        normalize_audio_path_fn: Optional[Callable[[str], str]] = None,
    ) -> List[Dict[str, Any]]:
        """处理算法结果，提取和规范化字段

        Args:
            combined_data: 合并后的算法结果 + result_data
            output_fields: 输出字段定义列表
            resource: 设备/API 名称
            device_fields: 固定设备字段类型映射 (DEVICE_FIELDS)
            algo_res: 原始 algorithm_result（默认策略用于提取设备字段）
            result_data: 完整 result_data（默认策略用于提取 raw_results_list）
            normalize_audio_path_fn: 音频路径规范化函数

        Returns:
            algorithm_results 扁平列表
        """
        ...


class VoiceLlmStrategy(AlgorithmResultStrategy):
    """voice_llm 算法策略

    voice_llm 的特殊处理：
    - 输出字段为硬编码（不依赖数据库映射）
    - API 结果映射为固定结构
    - rounds 数组需展开为按轮次扁平的 param_code
    """

    def get_output_fields(self, test_type: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        if test_type == 'e2e':
            return [
                {'source_param': 'test_type', 'target_param': 'test_type', 'param_type': 'text', 'dimension_name': 'test type'},
                {'source_param': 'algorithm_type', 'target_param': 'algorithm_type', 'param_type': 'text', 'dimension_name': 'algorithm type'},
                {'source_param': 'session_id', 'target_param': 'session_id', 'param_type': 'text', 'dimension_name': 'session ID'},
                {'source_param': 'rail_distance', 'target_param': 'rail_distance', 'param_type': 'number', 'dimension_name': 'rail distance(cm)'},
                {'source_param': 'voiceprint_registered', 'target_param': 'voiceprint_registered', 'param_type': 'boolean', 'dimension_name': 'voiceprint registered'},
                {'source_param': 'total_rounds', 'target_param': 'total_rounds', 'param_type': 'number', 'dimension_name': 'total rounds'},
                {'source_param': 'rounds', 'target_param': 'rounds', 'param_type': 'json', 'dimension_name': 'round results'},
                {'source_param': 'aggregated', 'target_param': 'aggregated', 'param_type': 'json', 'dimension_name': 'aggregated metrics'},
            ]
        else:
            return [
                {'source_param': 'session_id', 'target_param': 'session_id', 'param_type': 'text', 'dimension_name': 'session ID'},
                {'source_param': 'round_count', 'target_param': 'round_count', 'param_type': 'number', 'dimension_name': 'round count'},
                {'source_param': 'total_latency', 'target_param': 'total_latency', 'param_type': 'number', 'dimension_name': 'total latency(ms)'},
                {'source_param': 'context_mode', 'target_param': 'context_mode', 'param_type': 'text', 'dimension_name': 'context mode'},
                {'source_param': 'history_count', 'target_param': 'history_count', 'param_type': 'number', 'dimension_name': 'history count'},
                {'source_param': 'error', 'target_param': 'error', 'param_type': 'text', 'dimension_name': 'error'},
                {'source_param': 'rounds', 'target_param': 'rounds', 'param_type': 'json', 'dimension_name': 'round results'},
            ]

    def map_api_results(self, raw_results: Dict[str, Any], test_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if test_type == 'e2e':
            return {
                'test_type': raw_results.get('test_type', 'e2e'),
                'algorithm_type': raw_results.get('algorithm_type', 'voice_llm'),
                'session_id': raw_results.get('session_id'),
                'rail_distance': raw_results.get('rail_distance', 50),
                'voiceprint_registered': raw_results.get('voiceprint_registered', False),
                'total_rounds': raw_results.get('total_rounds', 0),
                'rounds': raw_results.get('rounds', []),
                'aggregated': raw_results.get('aggregated', {}),
            }
        else:
            return {
                'session_id': raw_results.get('session_id', ''),
                'round_count': raw_results.get('round_count', 0),
                'total_latency': raw_results.get('total_latency', 0),
                'context_mode': raw_results.get('context_mode', ''),
                'history_count': raw_results.get('history_count', 0),
                'error': raw_results.get('error'),
                'rounds': raw_results.get('rounds', []),
            }

    def process_algorithm_result(
        self,
        combined_data: Dict[str, Any],
        output_fields: List[Dict[str, Any]],
        resource: str,
        device_fields: Dict[str, str],
        algo_res: Optional[Dict[str, Any]] = None,
        result_data: Optional[Dict[str, Any]] = None,
        normalize_audio_path_fn: Optional[Callable[[str], str]] = None,
    ) -> List[Dict[str, Any]]:
        algorithm_results: List[Dict[str, Any]] = []

        for field in output_fields:
            param_key = field.get('target_param') or field.get('source_param')
            if not param_key or not combined_data.get(param_key):
                continue
            if param_key == 'rounds':
                # rounds 数组展开为按轮次扁平的 param_code
                rounds_arr = combined_data.get('rounds') or []
                if isinstance(rounds_arr, list):
                    for r_idx, r_item in enumerate(rounds_arr):
                        raw_round = r_item.get('round')
                        rn = (raw_round + 1) if isinstance(raw_round, int) else (r_idx + 1)
                        out = r_item.get('output') or {}
                        if isinstance(out, dict):
                            for sub_key, val in out.items():
                                if val is None or sub_key == 'evaluation':
                                    continue
                                sub_type = device_fields.get(sub_key, 'text')
                                if sub_type == 'audio_file' and isinstance(val, str) and val:
                                    if normalize_audio_path_fn:
                                        val = normalize_audio_path_fn(val)
                                algorithm_results.append({
                                    'device': resource,
                                    'param_code': f'{sub_key}@round:{rn}',
                                    'param_type': sub_type,
                                    'label': f'{sub_key} (第{rn}轮)',
                                    'value': val,
                                    'round_number': rn,
                                    'dimension_name': None,
                                })
                algorithm_results.append({
                    'device': resource,
                    'param_code': param_key,
                    'param_type': field.get('param_type', 'json'),
                    'label': field.get('dimension_name') or param_key,
                    'value': combined_data[param_key],
                    'dimension_name': None,
                })
            else:
                algorithm_results.append({
                    'device': resource,
                    'param_code': param_key,
                    'param_type': field.get('param_type', 'text'),
                    'label': field.get('dimension_name') or param_key,
                    'value': combined_data[param_key],
                    'dimension_name': None,
                })

        return algorithm_results


class TranslationStrategy(AlgorithmResultStrategy):
    """translation 算法策略

    translation 类型在结果字段映射和 API 映射方面无特殊处理，
    与 DefaultStrategy 行为一致。
    在 dimension_result_recorder 中 translation 有独立的算法类型解析逻辑，
    但该逻辑属于类型解析范畴，不属于结果处理策略。
    """

    def get_output_fields(self, test_type: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        return None

    def map_api_results(self, raw_results: Dict[str, Any], test_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return None

    def process_algorithm_result(
        self,
        combined_data: Dict[str, Any],
        output_fields: List[Dict[str, Any]],
        resource: str,
        device_fields: Dict[str, str],
        algo_res: Optional[Dict[str, Any]] = None,
        result_data: Optional[Dict[str, Any]] = None,
        normalize_audio_path_fn: Optional[Callable[[str], str]] = None,
    ) -> List[Dict[str, Any]]:
        return DefaultStrategy().process_algorithm_result(
            combined_data, output_fields, resource, device_fields,
            algo_res, result_data, normalize_audio_path_fn,
        )


class DefaultStrategy(AlgorithmResultStrategy):
    """默认策略（非特殊算法类型）

    输出字段和 API 映射返回 None，调用方使用默认仓库加载和字段映射。
    结果处理使用标准 output_fields 映射 + 设备字段补充。
    """

    def get_output_fields(self, test_type: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        return None

    def map_api_results(self, raw_results: Dict[str, Any], test_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return None

    def process_algorithm_result(
        self,
        combined_data: Dict[str, Any],
        output_fields: List[Dict[str, Any]],
        resource: str,
        device_fields: Dict[str, str],
        algo_res: Optional[Dict[str, Any]] = None,
        result_data: Optional[Dict[str, Any]] = None,
        normalize_audio_path_fn: Optional[Callable[[str], str]] = None,
    ) -> List[Dict[str, Any]]:
        algorithm_results: List[Dict[str, Any]] = []

        # 按 output_fields 映射
        for field in output_fields:
            param_key = field.get('target_param') or field.get('source_param')
            if not param_key or not combined_data.get(param_key):
                continue
            algorithm_results.append({
                'device': resource,
                'param_code': param_key,
                'param_type': field.get('param_type', 'text'),
                'label': field.get('dimension_name') or param_key,
                'value': combined_data[param_key],
                'dimension_name': None,
            })

        # 补充固定设备字段
        device_values: Dict[str, Any] = {}
        if isinstance(algo_res, dict):
            rounds = algo_res.get('rounds') or []
            if rounds and isinstance(rounds, list) and isinstance(rounds[0], dict):
                output = rounds[0].get('output') or {}
                if isinstance(output, dict):
                    for k, v in output.items():
                        if k in device_fields and v is not None:
                            device_values[k] = v
            agg = algo_res.get('aggregated') or {}
            if isinstance(agg, dict):
                for k, v in agg.items():
                    if v is not None:
                        agg_type = 'number' if isinstance(v, (int, float)) else 'text'
                        device_values['agg_' + k] = {'value': v, 'type': agg_type}

        if result_data:
            rrl = result_data.get('raw_results_list') or []
            if rrl and isinstance(rrl, list) and isinstance(rrl[0], dict):
                raw_item = rrl[0]
                raw_res = raw_item.get('raw_results') or {}
                if isinstance(raw_res, dict):
                    for k, v in raw_res.items():
                        if k in device_fields and v is not None and k not in device_values:
                            device_values[k] = v
                for k in ['round_number', 'success']:
                    if k in raw_item and raw_item[k] is not None and k not in device_values:
                        device_values[k] = raw_item[k]

        existing_codes = {item['param_code'] for item in algorithm_results if item.get('device') == resource}
        for param_code, param_value in device_values.items():
            if param_value is None or param_value == '':
                continue
            if param_code in existing_codes:
                continue
            if param_code.startswith('agg_') and isinstance(param_value, dict) and 'value' in param_value:
                actual_value = param_value['value']
                param_type = param_value.get('type', 'text')
            else:
                actual_value = param_value
                param_type = device_fields.get(param_code, 'text')
            if param_type == 'audio_file' and isinstance(actual_value, str) and actual_value:
                if normalize_audio_path_fn:
                    actual_value = normalize_audio_path_fn(actual_value)
            algorithm_results.append({
                'device': resource,
                'param_code': param_code,
                'param_type': param_type,
                'label': param_code,
                'value': actual_value,
                'dimension_name': None,
            })

        return algorithm_results


class AlgorithmStrategyFactory:
    """策略工厂 — 根据 algorithm_type 返回对应策略"""

    _strategies: Dict[str, AlgorithmResultStrategy] = {
        'voice_llm': VoiceLlmStrategy(),
        'translation': TranslationStrategy(),
    }
    _default = DefaultStrategy()

    @classmethod
    def get_strategy(cls, algorithm_type: str) -> AlgorithmResultStrategy:
        """根据算法类型获取策略实例"""
        return cls._strategies.get(algorithm_type, cls._default)
