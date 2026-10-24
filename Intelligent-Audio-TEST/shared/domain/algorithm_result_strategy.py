# -*- coding: utf-8 -*-
"""算法结果处理策略 — 只保留无法配置化的结果结构语义

输出字段清单（字段类型、展示名、映射目标键）由配置声明驱动：
`algorithm_api_params(direction=output)` + `param_mappings(source='api')`，
在应用层 `ResultFieldMappingQueryHandler.get_output_fields` 读取（C0 裁定 3）。
策略不再持有任何算法类型的硬编码字段表，新增算法/厂商只改配置即可完成输出映射；
`AlgorithmStrategyFactory` 只登记结构性语义确实不同的算法类型。

`map_api_results` 已废弃（C0 裁定 4 / INT-1748）：映射责任在执行侧，
评估侧只按 `target_param` 取值，不再保留第二个入口。
"""
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional


class AlgorithmResultStrategy(ABC):
    """算法结果处理策略接口"""

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
            output_fields: 配置声明的输出字段列表
                （含 param_type / label / target_param / field_path）
            resource: 设备/API 名称
            device_fields: 固定设备字段类型映射 (DEVICE_FIELDS，仅默认策略使用)
            algo_res: 原始 algorithm_result（默认策略用于提取设备字段）
            result_data: 完整 result_data（默认策略用于提取 raw_results_list）
            normalize_audio_path_fn: 音频路径规范化函数

        Returns:
            algorithm_results 扁平列表
        """
        ...


class VoiceLlmStrategy(AlgorithmResultStrategy):
    """voice_llm 算法策略

    只保留无法配置化的结构语义（C0 裁定 2）：
    - `rounds` 数组按轮展开为 `{key}@round:N` 键形；
    - 轮次内的 `evaluation` 子字典是评估回填，不是输出字段，跳过；
    - 轮内未知键（未在 output_fields 声明）不输出——键集合来自配置。
    字段清单 / 字段类型 / 展示名全部来自 output_fields，不再硬编码。

    （原 `get_output_fields` 中的硬编码字段表与 `map_api_results` 固定映射已删除。）
    """

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

        # 轮内子键的类型/展示名按声明键反查（target_param 是执行侧映射后的键）
        declared: Dict[str, Dict[str, Any]] = {}
        for field in output_fields or []:
            key = field.get('target_param') or field.get('source_param')
            if key and key not in declared:
                declared[key] = field

        # 输出顺序沿用配置声明顺序（ui_order / id），与改造前硬编码表顺序一致
        for field in output_fields or []:
            param_key = field.get('target_param') or field.get('source_param')
            if not param_key or not combined_data.get(param_key):
                continue

            if param_key != 'rounds':
                algorithm_results.append({
                    'device': resource,
                    'param_code': param_key,
                    'param_type': field.get('param_type', 'text'),
                    'label': field.get('label') or field.get('dimension_name') or param_key,
                    'value': combined_data[param_key],
                    'dimension_name': None,
                })
                continue

            # rounds 数组展开为按轮次扁平的 param_code；键集合与类型均取配置声明
            rounds_arr = combined_data.get(param_key)
            if not isinstance(rounds_arr, list):
                continue
            for r_idx, r_item in enumerate(rounds_arr):
                if not isinstance(r_item, dict):
                    continue
                raw_round = r_item.get('round')
                rn = (raw_round + 1) if isinstance(raw_round, int) else (r_idx + 1)
                out = r_item.get('output') or {}
                if not isinstance(out, dict):
                    continue
                for sub_key, val in out.items():
                    if val is None or sub_key == 'evaluation':
                        continue
                    sub_field = declared.get(sub_key)
                    if sub_field is None:
                        continue
                    sub_type = sub_field.get('param_type') or 'text'
                    if sub_type == 'audio_file' and isinstance(val, str) and val:
                        if normalize_audio_path_fn:
                            val = normalize_audio_path_fn(val)
                    sub_label = sub_field.get('label') or sub_key
                    algorithm_results.append({
                        'device': resource,
                        'param_code': f'{sub_key}@round:{rn}',
                        'param_type': sub_type,
                        'label': f'{sub_label} (第{rn}轮)',
                        'value': val,
                        'round_number': rn,
                        'dimension_name': None,
                    })
            algorithm_results.append({
                'device': resource,
                'param_code': param_key,
                'param_type': field.get('param_type') or 'json',
                'label': field.get('label') or field.get('dimension_name') or param_key,
                'value': rounds_arr,
                'dimension_name': None,
            })

        return algorithm_results


class DefaultStrategy(AlgorithmResultStrategy):
    """默认策略（非特殊算法类型）

    输出字段完全由配置声明（应用层读取），结果处理使用标准 output_fields 映射
    + 设备字段补充。

    translation 等无特殊结构语义的算法类型直接走本策略（原 TranslationStrategy
    与默认策略行为完全一致，已合并删除）。
    """

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
                'label': field.get('label') or field.get('dimension_name') or param_key,
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
    """策略工厂 — 按 algorithm_type 返回承载结构语义的策略

    只登记「结果结构」确实不同的算法类型；输出字段映射已配置驱动，
    新增算法/厂商无需在此登记（落到 DefaultStrategy）。
    """

    _strategies: Dict[str, AlgorithmResultStrategy] = {
        'voice_llm': VoiceLlmStrategy(),
    }
    _default = DefaultStrategy()

    @classmethod
    def get_strategy(cls, algorithm_type: str) -> AlgorithmResultStrategy:
        """根据算法类型获取策略实例"""
        return cls._strategies.get(algorithm_type, cls._default)
