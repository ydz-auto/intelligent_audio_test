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
                                          effective_playback_device_id, rounds_config, algorithm_params,
                                          upload_task_id=None):
        """构建 rounds_resolved，剥离 algorithm_params 到独立列

        :param upload_task_id: 本次上传任务 ID。提供时优先在任务内文件（按 md5 定位
            本次上传/秒传命中的音频记录）解析轮次音频名，避免同名素材绑到库中
            陈旧同名记录；任务内记录尚未创建的文件名保持未匹配，不回退库内旧记录。
        """
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
        # 本次上传任务内 文件名→audio_id 映射（新上传记录优先于库中陈旧同名记录）
        task_name_to_id, task_file_names = self._build_task_audio_name_map(upload_task_id)
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
                    if upload_task_id and item_name in task_file_names:
                        continue  # 本任务文件名不查库：记录存在与否均由任务内映射决定
                    # 查库：按文件名找已入库的音频（同名多条时最新创建的优先）
                    found = self.repo.find_audio_by_name(item_name)
                    if found:
                        audio_name_to_id[item_name] = found.id
        # 逐项匹配：当前音频 → 任务内记录 → 库内最新同名记录
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
                # 其次用本次上传任务内的记录
                elif upload_task_id and item_name in task_name_to_id:
                    audio_item['audio_id'] = task_name_to_id[item_name]
                # 名字属于本任务文件但记录尚未创建（分文件 merge 时序）：保持未匹配，
                # 不回退库内陈旧同名记录，也不强赋当前音频
                elif upload_task_id and item_name in task_file_names:
                    continue
                # 再用预查映射补全（库内最新同名记录）
                elif item_name in audio_name_to_id:
                    audio_item['audio_id'] = audio_name_to_id[item_name]

        return rounds_resolved, algo_params_col

    def _build_task_audio_name_map(self, upload_task_id):
        """构建本次上传任务内 文件名→audio_id 映射与任务文件名集合。

        任务文件按 md5 定位音频记录（本次新建或秒传命中），同 md5 多条记录取
        最新创建的一条；任务文件尚无对应音频记录时不入映射（仅入文件名集合，
        供调用方对该名字跳过库内陈旧同名记录回退）。
        """
        task_name_to_id = {}
        task_file_names = set()
        if not upload_task_id:
            return task_name_to_id, task_file_names
        try:
            task_files = self.repo.list_upload_files(upload_task_id) or []
        except Exception:
            return task_name_to_id, task_file_names
        for f in task_files:
            for key in (getattr(f, 'filename', None), getattr(f, 'original_filename', None)):
                if key:
                    task_file_names.add(key)
        md5s = {f.md5 for f in task_files if getattr(f, 'md5', None)}
        md5_to_id = {}
        if md5s:
            try:
                audios = self.repo.get_audios_by_md5_list(list(md5s)) or []
            except Exception:
                audios = []
            # id 单调递增：同名/同 md5 多条记录时保留最新创建的一条
            for _a in sorted(audios, key=lambda x: getattr(x, 'id', 0) or 0, reverse=True):
                if getattr(_a, 'md5', None):
                    md5_to_id.setdefault(_a.md5, getattr(_a, 'id', None))
        for f in task_files:
            audio_id = md5_to_id.get(getattr(f, 'md5', None) or '')
            if not audio_id:
                continue
            for key in (getattr(f, 'filename', None), getattr(f, 'original_filename', None)):
                if key:
                    task_name_to_id.setdefault(key, audio_id)
        return task_name_to_id, task_file_names

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
