# -*- coding: utf-8 -*-
"""测试用例创建 - 轮次配置处理 Mixin

从 audio_testcase_creation_service.py 拆分出的职责：
- _resolve_rounds_and_strip_params：构建 rounds_resolved 并剥离 algorithm_params
- _build_config_and_apply_dimensions：构建 config 字典并应用评估维度
"""
import copy
import logging

from shared.models.common_enums import DeviceType

logger = logging.getLogger(__name__)


class CreationRoundConfigMixin:
    """轮次配置（rounds_config）解析与 config 构建职责"""

    # 多轮整体评估口径的 round_scope 取值（与读侧 case_loader.OVERALL_ROUND_SCOPE、
    # 网关 DimensionItem.round_scope 协议一致）；其余值（single / per_round / 未标注）
    # 一律按逐轮口径处理
    OVERALL_ROUND_SCOPE = 'multi'

    def _resolve_rounds_and_strip_params(self, device_type, audio_id, audio, spl,
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
            if device_type == DeviceType.PHYSICAL.value:
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

    def _build_config_and_apply_dimensions(self, audio, rounds_resolved, dimensions_data, device_type,
                                            noise_spl, noise_audio_id, noise_device_ids=None,
                                            case_background_noise=None):
        """构建 config 字典，应用噪声配置和评估维度

        维度写侧规则（INT-1606 / INT-1607 评审裁定）：
        - 任一轮自带 `evaluation.dimensions`（list，显式 [] 也算）→ 整体以载荷为准：
          自带轮写「归一化 → device_type 作用域过滤 → 去重保序」后的逐轮维度；未自带轮写 []；
          顶层维度只保留 multi 口径（并入 `config.dimensions`），逐轮口径忽略并告警。
        - 所有轮都未自带 → 顶层维度回填每一轮（改动前口径），multi 写 `config.dimensions`。
        - 既无顶层有效维度也无轮自带 → 只给缺失维度的轮补 []。
        轮内 `round_scope='multi'` 一律归并进 `config.dimensions` 并从轮内移除：物理设备
        （physical）整体评估只认顶层 config.dimensions（finalization_mixin.py:84），
        仅留轮内会永不出整体分。
        """
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
        top_dims = self._extract_top_level_dimensions(dimensions_data)
        round_items = [r for r in rounds_resolved if isinstance(r, dict)]
        if any(self._round_self_provides_dimensions(r) for r in round_items):
            # R1：任一轮自带维度 → 整体以载荷为准，不拿顶层维度回填未自带轮
            self._apply_payload_round_dimensions(round_items, top_dims, device_type, config, audio)
        elif top_dims is not None:
            # R2：所有轮都未自带 → 顶层维度回填每一轮（旧调用方行为零变化）
            self._apply_top_level_dimensions(round_items, top_dims, device_type, config)
        else:
            # R4：无顶层维度且无轮自带 → 维持现状，只给缺失轮补 []
            self._ensure_round_dimension_placeholders(round_items)
        return config

    # ==== 评估维度写侧辅助（INT-1606 R1~R6） ====

    @staticmethod
    def _extract_top_level_dimensions(dimensions_data):
        """顶层维度载荷解析：只有解析结果是 list 且非空才有效。

        `{'dimensions': []}` 是真值 dict，不能按 truthiness 判为「有顶层维度」，
        否则会把未自带维度的轮覆盖成空（INT-1607 评审 S6）。
        """
        if isinstance(dimensions_data, dict):
            raw_dims = dimensions_data.get('dimensions')
        elif isinstance(dimensions_data, list):
            raw_dims = dimensions_data
        else:
            raw_dims = None
        if not isinstance(raw_dims, list) or not raw_dims:
            return None
        return raw_dims

    @staticmethod
    def _normalize_dimension(dim):
        """维度条目归一：dict 原样，裸 id（int）包装成 {'id': n}，其它形态跳过。"""
        if isinstance(dim, dict):
            return dim
        if hasattr(dim, 'model_dump'):
            return dim.model_dump(by_alias=False, exclude_none=True)
        if isinstance(dim, int):
            return {'id': dim}
        return None

    def _normalize_dimensions(self, raw_dims):
        """归一化维度列表，跳过无法识别的条目（不抛异常）。"""
        normalized = []
        for d in raw_dims or []:
            item = self._normalize_dimension(d)
            if item is not None:
                normalized.append(item)
        return normalized

    @staticmethod
    def _filter_dimension_by_device_type(dims, device_type):
        """按设备类型作用域过滤：未标注 device_type 的条目对所有目标设备都生效。"""
        return [d for d in dims if not d.get('device_type') or d.get('device_type') == device_type]

    @classmethod
    def _is_overall_scope_dimension(cls, dim):
        """维度条目是否为多轮整体评估口径（round_scope=multi）。

        逐轮集合 = round_scope != 'multi'（per_round / 未标注同属逐轮，与读侧
        case_loader._merge_dimensions_config 对齐，评审 S7）。
        """
        return isinstance(dim, dict) and dim.get('round_scope') == cls.OVERALL_ROUND_SCOPE

    @staticmethod
    def _dedupe_dimensions(dims):
        """按 (id, round_scope) 去重保序，id 为真值才保留。"""
        seen_keys = set()
        unique_dims = []
        for d in dims:
            dim_id = d.get('id')
            key = (dim_id, d.get('round_scope', 'single'))
            if dim_id and key not in seen_keys:
                seen_keys.add(key)
                unique_dims.append(d)
        return unique_dims

    @staticmethod
    def _round_self_provides_dimensions(round_item):
        """该轮是否自带评估维度。

        `evaluation` 为 dict 且含 `dimensions` 键、值为 list 才算自带（显式 `[]` 算自带）；
        判定在任何 device_type 作用域过滤之前（评审 S5）。
        """
        if not isinstance(round_item, dict):
            return False
        evaluation = round_item.get('evaluation')
        return (isinstance(evaluation, dict)
                and 'dimensions' in evaluation
                and isinstance(evaluation['dimensions'], list))

    def _resolve_round_dimensions(self, raw_dims, device_type):
        """轮内维度：归一化 → device_type 作用域过滤 → 去重保序，再分逐轮 / 整体两桶。"""
        dims = self._dedupe_dimensions(
            self._filter_dimension_by_device_type(self._normalize_dimensions(raw_dims), device_type))
        round_scoped = [d for d in dims if not self._is_overall_scope_dimension(d)]
        overall_scoped = [d for d in dims if self._is_overall_scope_dimension(d)]
        return round_scoped, overall_scoped

    def _apply_payload_round_dimensions(self, round_items, top_dims, device_type, config, audio):
        """R1：整体以载荷为准写入各轮维度，并按 R3 归并整体维度。"""
        top_normalized = self._normalize_dimensions(top_dims)
        ignored_top_dims = [d for d in self._dedupe_dimensions(top_normalized)
                            if not self._is_overall_scope_dimension(d)]
        # R3：归一化 → device_type 作用域过滤 → 按 (id, round_scope) 去重保序（与 R2 回填分支同口径）
        overall_dims = self._dedupe_dimensions(self._filter_dimension_by_device_type(
            [d for d in top_normalized if self._is_overall_scope_dimension(d)], device_type))
        if ignored_top_dims:
            logger.warning(
                "上传生成用例时轮内已自带评估维度，忽略顶层逐轮维度: audio=%s, audio_id=%s, "
                "device_type=%s, ignored_dim_ids=%s",
                getattr(audio, 'name', None), getattr(audio, 'id', None), device_type,
                [d.get('id') for d in ignored_top_dims],
            )
        for round_item in round_items:
            if not self._round_self_provides_dimensions(round_item):
                # 未自带轮写空，不用顶层回填（评审 S1）；evaluation 非 dict（如 null）先归一为 {}
                if not isinstance(round_item.get('evaluation'), dict):
                    round_item['evaluation'] = {}
                round_item['evaluation']['dimensions'] = []
                continue
            round_scoped, round_overall = self._resolve_round_dimensions(
                round_item['evaluation']['dimensions'], device_type)
            round_item['evaluation']['dimensions'] = list(round_scoped)
            overall_dims.extend(round_overall)
        overall_dims = self._dedupe_dimensions(overall_dims)
        if overall_dims:
            config['dimensions'] = overall_dims

    def _apply_top_level_dimensions(self, round_items, top_dims, device_type, config):
        """R2：所有轮都未自带维度时，顶层维度回填每一轮（改动前口径）。"""
        dims = self._dedupe_dimensions(
            self._filter_dimension_by_device_type(self._normalize_dimensions(top_dims), device_type))
        round_scoped = [d for d in dims if not self._is_overall_scope_dimension(d)]
        overall_scoped = [d for d in dims if self._is_overall_scope_dimension(d)]
        for round_item in round_items:
            if not isinstance(round_item.get('evaluation'), dict):
                round_item['evaluation'] = {}
            # 每轮独立 list 拷贝，避免各轮共享同一引用
            round_item['evaluation']['dimensions'] = list(round_scoped)
        if overall_scoped:
            config['dimensions'] = list(overall_scoped)

    @staticmethod
    def _ensure_round_dimension_placeholders(round_items):
        """R4：无维度可写时，只给缺失维度的轮补 []，不覆盖已有配置。

        非 list 的 `dimensions`（None / dict 等脏载荷）同样归一为 []（R5）：读侧
        `case_loader._merge_dimensions_config` 会直接迭代该值，原样落库会把 TypeError
        推迟到评估侧爆发（INT-1615 审计 P2-1）。
        """
        for round_item in round_items:
            if not isinstance(round_item.get('evaluation'), dict):
                round_item['evaluation'] = {}
            if not isinstance(round_item['evaluation'].get('dimensions'), list):
                round_item['evaluation']['dimensions'] = []

