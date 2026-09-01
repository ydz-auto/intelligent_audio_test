# -*- coding: utf-8 -*-
"""测试用例创建 - 轮次配置处理 Mixin

从 audio_testcase_creation_service.py 拆分出的职责：
- _resolve_rounds_and_strip_params：构建 rounds_resolved 并剥离 algorithm_params
- _build_config_and_apply_dimensions：构建 config 字典并应用评估维度
"""
import copy


class CreationRoundConfigMixin:
    """轮次配置（rounds_config）解析与 config 构建职责"""

    def _resolve_rounds_and_strip_params(self, tt, audio_id, audio, spl,
                                          effective_playback_device_id, rounds_config, algorithm_params):
        """构建 rounds_resolved，剥离 algorithm_params 到独立列"""
        if rounds_config:
            rounds_resolved = copy.deepcopy(rounds_config)
        else:
            audio_config = {
                'audio_id': audio_id,
                'spl': spl if spl else 65.0,
                'play_order': 0,
            }
            if tt == 'e2e':
                audio_config['playback_device_id'] = effective_playback_device_id
            rounds_resolved = [{'round_number': 1, 'audios': [audio_config]}]

        algo_params_col = []
        for round_item in rounds_resolved:
            if not isinstance(round_item, dict):
                continue
            rn = round_item.get('round_number') or round_item.get('roundNumber', 1)
            round_ap = round_item.pop('algorithm_params', None) or round_item.pop('algorithmParams', None)
            if round_ap:
                params_list = []
                if isinstance(round_ap, dict):
                    params_list = [{'field_code': k, 'field_value': v} for k, v in round_ap.items()]
                elif isinstance(round_ap, list):
                    for p in round_ap:
                        if isinstance(p, dict):
                            fc = p.get('field_code') or p.get('fieldCode')
                            fv = p.get('field_value', p.get('fieldValue'))
                            if fc:
                                params_list.append({'field_code': fc, 'field_value': fv})
                if params_list:
                    algo_params_col.append({'round_number': rn, 'params': params_list})
            round_item.pop('reference_params_path', None)
            round_item.pop('referenceParamsPath', None)

        if not algo_params_col and algorithm_params:
            round_algorithm_params = []
            if isinstance(algorithm_params, dict):
                round_algorithm_params = [
                    {'field_code': fc, 'field_value': fv} for fc, fv in algorithm_params.items()
                ]
            elif isinstance(algorithm_params, list):
                for p in algorithm_params:
                    if isinstance(p, dict):
                        fc = p.get('field_code') or p.get('fieldCode')
                        fv = p.get('field_value', p.get('fieldValue'))
                        if fc:
                            round_algorithm_params.append({'field_code': fc, 'field_value': fv})
            if round_algorithm_params:
                algo_params_col = [{'round_number': 1, 'params': round_algorithm_params}]

        # 秒传场景下已有音频的 name 可能与前端传的 audio_name 不一致（之前上传时可能改名），
        # 所以额外用 original_filename 和 md5 兜底匹配
        audio_name_for_match = audio.name
        audio_original_for_match = getattr(audio, 'original_filename', None) or audio.name
        audio_md5_for_match = getattr(audio, 'md5', None) or ''
        # 预查所有 audio_name → audio_id 映射（避免循环里重复查库）
        # 按 name / original_filename / md5 三重匹配
        audio_name_to_id = {}
        for round_item in rounds_resolved:
            if not isinstance(round_item, dict):
                continue
            for audio_item in round_item.get('audios', []):
                if not isinstance(audio_item, dict):
                    continue
                item_name = audio_item.get('audio_name') or ''
                if item_name and not audio_item.get('audio_id') and item_name not in audio_name_to_id:
                    # 查库：按文件名找已入库的音频
                    found = self.repo.find_audio_by_name(item_name)
                    if found:
                        audio_name_to_id[item_name] = found.id
        # 第一轮：按 name / original_filename / md5 / 预查映射 匹配
        unmatched_items = []
        for round_item in rounds_resolved:
            if not isinstance(round_item, dict):
                continue
            audios = round_item.get('audios', [])
            if not isinstance(audios, list):
                round_item['audios'] = []
                audios = []
            for audio_item in audios:
                if not isinstance(audio_item, dict):
                    continue
                if audio_item.get('audio_id'):
                    continue
                item_name = audio_item.get('audio_name') or ''
                # 优先用当前音频匹配（name / original_filename / md5 三重匹配）
                if (item_name == audio_name_for_match
                        or item_name == audio_original_for_match
                        or (audio_md5_for_match and item_name == audio_md5_for_match)
                        or not item_name):
                    audio_item['audio_id'] = audio_id
                # 其次用预查映射补全
                elif item_name in audio_name_to_id:
                    audio_item['audio_id'] = audio_name_to_id[item_name]
                else:
                    unmatched_items.append(audio_item)
        # 第二轮兜底：剩余唯一未匹配项直接用当前 audio_id
        # （秒传场景下当前 audio_id 就是已有音频 ID，无论单轮多轮都适用）
        if len(unmatched_items) == 1:
            unmatched_items[0]['audio_id'] = audio_id

        return rounds_resolved, algo_params_col

    def _build_config_and_apply_dimensions(self, audio, rounds_resolved, dimensions_data, tt,
                                            noise_spl, noise_audio_id, noise_device_ids=None,
                                            case_background_noise=None):
        """构建 config 字典，应用噪声配置和评估维度"""
        config = {
            'source_audio': audio.name,
            'auto_generated': True,
            'rounds': rounds_resolved,
        }
        # 噪声配置：case 级背景噪声（rounds 外层）优先，其次顶层 noise_audio_id/noise_spl
        if case_background_noise:
            config['background_noise'] = case_background_noise
        elif (noise_spl and noise_spl > 0) or noise_audio_id:
            config['background_noise'] = {
                'audio_id': noise_audio_id,
                'spl': noise_spl if noise_spl else 60.0,
                'device_ids': noise_device_ids or [],
                'loop': True,
            }
        if dimensions_data:
            raw_dims = []
            if isinstance(dimensions_data, dict):
                raw_dims = dimensions_data.get('dimensions', [])
            elif isinstance(dimensions_data, list):
                raw_dims = dimensions_data
            norm_dims = []
            for d in raw_dims:
                if isinstance(d, dict):
                    norm_dims.append(d)
                elif hasattr(d, 'model_dump'):
                    norm_dims.append(d.model_dump(by_alias=False, exclude_none=True))
                else:
                    norm_dims.append({'id': d})
            filtered_dims = [d for d in norm_dims if not d.get('test_type') or d.get('test_type') == tt]
            seen_keys = set()
            unique_dims = []
            for d in filtered_dims:
                dim_id = d.get('id')
                scope = d.get('round_scope', 'single')
                key = (dim_id, scope)
                if dim_id and key not in seen_keys:
                    seen_keys.add(key)
                    unique_dims.append(d)
            single_round_dims = [d for d in unique_dims if d.get('round_scope', 'single') == 'single']
            multi_round_dims = [d for d in unique_dims if d.get('round_scope') == 'multi']
            for round_item in rounds_resolved:
                if isinstance(round_item, dict):
                    if 'evaluation' not in round_item:
                        round_item['evaluation'] = {}
                    round_item['evaluation']['dimensions'] = single_round_dims
            if multi_round_dims:
                config['dimensions'] = multi_round_dims
        else:
            for round_item in rounds_resolved:
                if isinstance(round_item, dict):
                    if 'evaluation' not in round_item:
                        round_item['evaluation'] = {}
                    if 'dimensions' not in round_item['evaluation']:
                        round_item['evaluation']['dimensions'] = []
        return config
