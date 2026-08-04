"""多轮评估数据构建混入：从 algorithm_result.rounds 提取/构建单轮评估数据"""
import json


class RoundDataBuilderMixin:
    """从多轮 algorithm_result 中提取单轮评估数据"""

    def _extract_round_eval_data(self, algorithm_result, round_number):
        """从多轮 algorithm_result 中提取单轮评估数据

        当 round_number 不为 None 时，从 rounds[round_number] 提取该轮的扁平字段
        （asr_text 等），供评估端点直接使用。

        Args:
            algorithm_result: 完整的 algorithm_result（含 rounds[] 结构）
            round_number: 0-indexed 轮次编号

        Returns:
            dict: 单轮扁平数据，若轮次不存在返回 None
        """
        # 循环反序列化，处理可能的双重序列化旧数据
        while isinstance(algorithm_result, str):
            try:
                algorithm_result = json.loads(algorithm_result)
            except (json.JSONDecodeError, TypeError):
                return None

        if not isinstance(algorithm_result, dict):
            return None

        rounds = algorithm_result.get('rounds', [])
        if not rounds or round_number >= len(rounds):
            return None

        round_data = rounds[round_number]
        output = round_data.get('output', {})

        # 构建扁平结构，把 rounds[i].output 的字段提升到顶层
        flat = dict(output) if isinstance(output, dict) else {}
        if 'latency' in round_data:
            flat['latency'] = round_data['latency']

        return flat

    def _build_rounds_list(self, algorithm_result, reference_params_col,
                            field_mapper, algorithm_type, test_type, task_id, test_case_id):
        """从 algo_result.rounds 构建 [{reference, hypothesis, ...}, ...] 列表

        遍历 param_mappings，按 source 类型从每轮的 output（device/api）和
        按轮加载的 reference_params（reference）取值，用 target_param 作为 key。
        """
        from shared.algorithm.case_parameter_extractor import CaseParameterExtractor
        from shared.algorithm.reference_params_generator import (
            get_reference_value as gen_reference_value,
        )

        rounds = algorithm_result.get('rounds', [])
        output_field_keys = field_mapper.get_mapped_device_output_field_keys(algorithm_type)
        loader = CaseParameterExtractor._get_loader()
        mappings = loader.get_param_mapping(algorithm_type, 'evaluation')

        if not mappings:
            self._log(
                level='WARNING',
                content=f"[_build_rounds_list] 未找到 {algorithm_type} 的 evaluation param mappings",
                task_id=task_id, test_case_id=test_case_id
            )
            return []

        rounds_list = []
        for rd in rounds:
            item = self._build_single_round(
                rd, reference_params_col, mappings, loader,
                gen_reference_value, test_type, algorithm_type, task_id, test_case_id
            )
            rounds_list.append(item)

        return rounds_list

    def _build_single_round(self, round_item, reference_params_col, mappings, loader,
                            gen_reference_value, test_type, algorithm_type, task_id, test_case_id):
        """构建单轮评估数据 item

        按轮加载 reference_params，遍历 mappings 按 source 类型从 output / reference 取值。
        """
        from shared.algorithm.case_parameter_extractor import CaseParameterExtractor

        output = round_item.get('output', {})
        round_number = round_item.get('round', 0)

        item = {}

        # 按轮加载 reference_params
        # algo_result.rounds[].round 是 0-indexed，reference_params_col 用 1-indexed
        round_ref_data = {}
        if reference_params_col:
            round_ref_data = CaseParameterExtractor._load_round_ref_file(
                reference_params_col, round_number + 1
            )
        for m in mappings:
            source = m.get('source', 'api')
            source_param = m.get('source_param', '')
            target_param = m.get('target_param', '')
            value = None

            if source in ('device', 'api'):
                # output 的 key 是 target_param 名（build_algorithm_result 已映射）
                value = output.get(target_param, '')
            elif source == 'reference':
                # 从按轮加载的 reference 取
                ref_item = round_ref_data.get(source_param)
                if ref_item and isinstance(ref_item, dict):
                    ref_type = None
                    for ref_def in loader.get_reference_params(algorithm_type):
                        if ref_def.get('code') == source_param:
                            ref_type = ref_def.get('type')
                            break
                    value = gen_reference_value(
                        ref_item, test_type, ref_type,
                        algorithm_type=algorithm_type,
                        case_config={}
                    )
            elif source == 'case':
                # case 参数暂不按轮处理，跳过
                pass

            if value is not None:
                item[target_param] = value

        return item
