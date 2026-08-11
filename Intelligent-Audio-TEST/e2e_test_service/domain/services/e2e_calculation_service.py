# -*- coding: utf-8 -*-
"""E2E 测试纯领域计算服务。

本模块仅包含不涉及任何 IO（gRPC、DB、文件系统）的领域逻辑：
- 播放偏移计算
- algorithm_result 构建（多轮数据结构组装）
- round_data 构建（单轮输出字段映射）
- 参考参数提取

依赖方向：domain -> domain（纯领域依赖，无 infrastructure）
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union


class E2ECalculationService:
    """E2E 测试领域计算服务

    职责：
    - 计算实际播放偏移（offset）
    - 从多轮原始结果构建 algorithm_result 数据结构
    - 从单轮 primary 结果构建 round_data（含字段映射）
    - 从 extra_params 提取 ref_fields

    本类不执行任何 IO，仅做数据结构与数学计算。
    """

    @staticmethod
    def calculate_actual_offset(playback_timestamps: Dict) -> Dict:
        """计算实际播放偏移

        Args:
            playback_timestamps: 播放时间戳字典，含 record_start_time 和 audio_play_times

        Returns:
            Dict: {key: {audio_id, play_order, offset}} 的字典
        """
        record_start_time = playback_timestamps.get('record_start_time')
        audio_play_times = playback_timestamps.get('audio_play_times', [])

        if not record_start_time or not audio_play_times:
            return {}

        audio_offsets: Dict[str, Any] = {}

        for play_time in audio_play_times:
            audio_id = play_time.get('audio_id')
            if not audio_id:
                continue

            play_order = play_time.get('play_order', 0)
            actual_time = play_time.get('actual_time', record_start_time)
            theory_offset = play_time.get('actual_start_offset', 0.0)
            actual_offset = actual_time - record_start_time - theory_offset

            key = f"{audio_id}_{play_order}"
            audio_offsets[key] = {
                'audio_id': audio_id,
                'play_order': play_order,
                'offset': actual_offset,
            }

        return audio_offsets

    @staticmethod
    def build_algorithm_result(
        all_round_results: List[Dict],
        case_config: Dict,
        algorithm_type: str,
    ) -> Dict:
        """从多轮原始结果构建 algo_result 结构（rounds[] + aggregated）

        Args:
            all_round_results: 所有轮次的结果列表
            case_config: 用例配置，含 rounds 配置
            algorithm_type: 算法类型

        Returns:
            Dict: algorithm_result 数据结构
        """
        # TODO: 重构为通过 port 接口注入
        from shared.clients.grpc_clients import algo_get_field_mappings

        field_mappings = algo_get_field_mappings(algorithm_type)
        mapped_output_fields = (field_mappings.get('mapped', {}) or {}).get('device', {}).get('output', {})

        rounds_by_index: Dict[int, List[Dict]] = {}
        for r in all_round_results:
            rn = r.get('round_number', 0)
            if rn not in rounds_by_index:
                rounds_by_index[rn] = []
            rounds_by_index[rn].append(r)

        case_rounds = case_config.get('rounds', [])
        rounds_list: List[Dict] = []
        latency_values: List[float] = []

        for round_idx in sorted(rounds_by_index.keys()):
            round_results = rounds_by_index[round_idx]
            primary = round_results[0] if round_results else {}

            round_config = case_rounds[round_idx] if round_idx < len(case_rounds) else {}
            audios = round_config.get('audios', [])
            first_audio = audios[0] if audios else {}

            audio_name = first_audio.get('audio_name') or first_audio.get('name', '')
            audio_path = first_audio.get('audio_path') or first_audio.get('path', '')

            round_output = E2ECalculationService._map_round_output(primary, mapped_output_fields)

            latency = primary.get('response_time') or primary.get('latency')
            if latency is not None:
                try:
                    latency_values.append(float(latency))
                except (ValueError, TypeError):
                    pass

            wait_time = round_config.get('waitTime', 5000)
            if wait_time is None:
                wait_time = 5000

            rounds_list.append({
                'round': round_idx,
                'input': {
                    'audio_name': audio_name,
                    'audio_path': audio_path,
                    'type': 'audio',
                },
                'output': round_output,
                'latency': latency,
                'wait_time': wait_time,
                'evaluation': {},
            })

        avg_latency = None
        if latency_values:
            avg_latency = round(sum(latency_values) / len(latency_values), 4)

        aggregated = {
            'avg_latency': avg_latency,
            'avg_wer': None,
            'avg_llm_judge': None,
        }

        return {
            'test_type': 'e2e',
            'algorithm_type': algorithm_type,
            'total_rounds': len(rounds_list),
            'rounds': rounds_list,
            'aggregated': aggregated,
        }

    @staticmethod
    def build_round_data(
        primary: Dict,
        round_idx: int,
        case_config: Dict,
        algorithm_type: str,
        audio_name: str,
        audio_path: str,
    ) -> Dict:
        """从单轮 primary 结果构建 round_data（含字段映射）

        Args:
            primary: 本轮主结果
            round_idx: 轮次索引
            case_config: 用例配置
            algorithm_type: 算法类型
            audio_name: 音频名
            audio_path: 音频路径

        Returns:
            Dict: round_data 数据结构
        """
        # TODO: 重构为通过 port 接口注入
        from shared.clients.grpc_clients import algo_get_field_mappings

        field_mappings = algo_get_field_mappings(algorithm_type)
        mapped_output_fields = (field_mappings.get('mapped', {}) or {}).get('device', {}).get('output', {})
        round_output = E2ECalculationService._map_round_output(primary, mapped_output_fields)

        latency = primary.get('response_time') or primary.get('latency')

        return {
            'round': round_idx,
            'input': {'audio_name': audio_name, 'audio_path': audio_path, 'type': 'audio'},
            'output': round_output,
            'latency': latency,
            'evaluation': {},
        }

    @staticmethod
    def build_ref_fields(extra_params: Dict) -> Dict:
        """从 extra_params 提取 ref_fields"""
        def extract_value(val):
            if isinstance(val, dict) and 'value' in val:
                return val.get('value', '')
            return val

        ref_fields: Dict[str, Any] = {}
        for field_key, field_value in extra_params.items():
            if field_value:
                ref_fields[field_key] = extract_value(field_value)
        return ref_fields

    @staticmethod
    def _map_round_output(primary: Dict, mapped_output_fields: Union[List, Dict]) -> Dict:
        """将 primary 结果的字段映射为 target 字段"""
        round_output: Dict[str, Any] = {}
        if isinstance(mapped_output_fields, list):
            for f in mapped_output_fields:
                target = f.get('code')
                dim_id = f.get('dimension_id')
                if dim_id is not None:
                    dim_key = f'{target}__dim_{dim_id}'
                    dim_val = primary.get(dim_key)
                    if dim_val is not None:
                        round_output[dim_key] = dim_val
                val = primary.get(target)
                if val is not None:
                    if target not in round_output or not round_output[target]:
                        round_output[target] = val
        else:
            for target, f in mapped_output_fields.items():
                dim_id = f.get('dimension_id') if isinstance(f, dict) else None
                if dim_id is not None:
                    dim_key = f'{target}__dim_{dim_id}'
                    dim_val = primary.get(dim_key)
                    if dim_val is not None:
                        round_output[dim_key] = dim_val
                val = primary.get(target)
                if val is not None:
                    if target not in round_output or not round_output[target]:
                        round_output[target] = val
        return round_output

    @staticmethod
    def calculate_avg_latency(all_round_results: List[Dict]) -> float:
        """计算平均响应时间"""
        latency_values: List[float] = []
        for r in all_round_results:
            lat = r.get('response_time') or r.get('latency')
            if lat is not None:
                try:
                    latency_values.append(float(lat))
                except (ValueError, TypeError):
                    pass
        return round(sum(latency_values) / len(latency_values), 4) if latency_values else 0
