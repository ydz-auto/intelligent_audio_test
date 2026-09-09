# -*- coding: utf-8 -*-
"""测试用例批量配置更新 Mixin — TestCaseConfigUpdateMixin。

从 testcase_batch_service.py 按职责拆分，承担 config JSON 的批量写操作：
- 专属算法参数（_batch_update_algorithm_params）
- 播放设备（_batch_update_playback_devices）
- 声压（_batch_update_spl）
- 评价维度（_batch_update_dimensions，支持统一/逐轮模式）
- 背景噪声（_batch_update_noise）

统一的轮次遍历/过滤与 JSON 字段落库逻辑抽取为 _iter_selected_rounds /
_update_config_flagged，消除四处重复代码。
由 TestCaseBatchService 组合复用，不单独实例化。
"""
from __future__ import annotations

import logging

import sqlalchemy.orm.attributes

from shared.utils.query_utils import now_cst

logger = logging.getLogger(__name__)

# 逐轮配置中"最后一轮"的动态轮次号（按用例实际轮次数解析）
LAST_ROUND_KEY = '-1'

# targets 拼写别名：兼容前端单复数两种写法（interferer → interferers）
TARGET_ALIASES = {'interferer': 'interferers'}


class TestCaseConfigUpdateMixin:
    """测试用例批量配置更新 Mixin。"""

    # ---------- 公共辅助：轮次遍历 / JSON 字段落库 / 逐轮取值 ----------

    @staticmethod
    def _iter_selected_rounds(config, round_mode, round_numbers):
        """按 round_mode 遍历轮次：all/per_round 返回全部，specific 按轮次号过滤。

        仅产出 dict 类型轮次，非 dict 项自动跳过。
        """
        for round_item in config.get('rounds', []):
            if not isinstance(round_item, dict):
                continue
            rn = round_item.get('round_number') or round_item.get('roundNumber')
            if round_mode == 'specific' and rn not in round_numbers:
                continue
            yield round_item

    @staticmethod
    def _round_count(config):
        """用例实际轮次数（用于 '-1' 最后一轮的动态解析）。"""
        return len([r for r in config.get('rounds', []) if isinstance(r, dict)])

    @staticmethod
    def _get_round_value(round_values, rn, last_rn):
        """按轮次取逐轮配置：优先精确轮次号，最后一轮回退 LAST_ROUND_KEY 动态解析。

        round_values 形如 {'1': {...}, '3': {...}, '-1': {...}}（键为字符串）。
        """
        if not isinstance(round_values, dict) or not round_values:
            return None
        value = round_values.get(str(rn), round_values.get(rn))
        if value is None and last_rn and rn == last_rn:
            value = round_values.get(LAST_ROUND_KEY, round_values.get(-1))
        return value

    @classmethod
    def _normalize_targets(cls, targets):
        """归一化 targets 拼写（interferer → interferers），返回新列表。"""
        if not targets:
            return []
        return [TARGET_ALIASES.get(t, t) for t in targets]

    @classmethod
    def _round_targets(cls, rv, default_targets):
        """从逐轮配置提取 targets，缺省回退默认目标（并归一化拼写）。"""
        if isinstance(rv, dict) and rv.get('targets'):
            return cls._normalize_targets(rv['targets'])
        return cls._normalize_targets(default_targets)

    @staticmethod
    def _update_config_flagged(tc, config):
        """写回 config JSON 字段并标记 SQLAlchemy 变更、更新时间戳。"""
        tc.config = config
        sqlalchemy.orm.attributes.flag_modified(tc, 'config')
        tc.updated_at = now_cst()

    @staticmethod
    def _apply_spl_or_device_id(target, value, device_id=None):
        """向背景噪声/干扰人/声纹字典写入声压值与可选播放设备 ID。"""
        if device_id is not None:
            target['playback_device_id'] = device_id
        if value is not None:
            target['spl'] = value

    @staticmethod
    def _normalize_algorithm_params(algorithm_params):
        """把 algorithm_params（list/dict 两种形态）归一为 {field_code: field_value} 字典。"""
        ap_dict = {}
        if isinstance(algorithm_params, list):
            for item in algorithm_params:
                if isinstance(item, dict):
                    code = item.get('field_code') or item.get('fieldCode', '')
                    value = item.get('field_value') or item.get('fieldValue', '')
                    if code:
                        ap_dict[code] = value
        elif isinstance(algorithm_params, dict):
            ap_dict = algorithm_params
        return ap_dict

    @staticmethod
    def _params_to_list(ap_dict):
        """{field_code: field_value} → [{field_code, field_value}]。"""
        return [{'field_code': k, 'field_value': v} for k, v in ap_dict.items()]

    @staticmethod
    def _extract_device_id(payload):
        """从 dict{deviceId} 或字符串提取播放设备 ID。"""
        if isinstance(payload, dict):
            return payload.get('deviceId') or payload.get('device_id')
        return payload

    @staticmethod
    def _extract_value(payload):
        """从数字或 dict{value} 提取声压值。"""
        if isinstance(payload, bool):
            return payload
        if isinstance(payload, (int, float)):
            return float(payload)
        if isinstance(payload, dict):
            return payload.get('value')
        return payload

    @staticmethod
    def _extract_noise(payload):
        """从 dict{audioId/audio_id, spl, deviceIds/device_ids} 提取噪声三要素。

        返回 (audio_id, spl, device_ids)，device_ids 的 None 与 [] 区分"未提供/清空"。
        """
        if not isinstance(payload, dict):
            return None, None, None
        audio_id = payload.get('audioId') or payload.get('audio_id')
        spl = payload.get('spl')
        device_ids = payload.get('deviceIds')
        if device_ids is None:
            device_ids = payload.get('device_ids')
        return audio_id, spl, device_ids

    def _apply_device_to_round(self, round_item, device_id, targets):
        """把播放设备写入单轮内各目标（audio/segmentBackgroundNoise/interferers/voiceprint/轮次背景噪声）。"""
        targets = self._normalize_targets(targets)
        if device_id is None:
            return
        # 1. 目标人音频
        if 'audio' in targets:
            for audio_config in round_item.get('audios', []):
                audio_config['playback_device_id'] = device_id
        # 2-5. segment 级背景噪声 / 干扰人 / 声纹
        for audio_config in round_item.get('audios', []):
            if 'segmentBackgroundNoise' in targets:
                bn = audio_config.get('background_noise') or audio_config.get('backgroundNoise')
                if bn and isinstance(bn, dict):
                    bn['playback_device_id'] = device_id
            if 'interferers' in targets:
                for inf in audio_config.get('interferers', []):
                    if isinstance(inf, dict):
                        inf['playback_device_id'] = device_id
            if 'voiceprint' in targets:
                vp = audio_config.get('voiceprint')
                if vp and isinstance(vp, dict):
                    vp['playback_device_id'] = device_id
        # 轮次级背景噪声
        if 'caseBackgroundNoise' in targets:
            rbn = round_item.get('background_noise') or round_item.get('backgroundNoise')
            if rbn and isinstance(rbn, dict):
                if 'playback_device_ids' in rbn:
                    rbn['playback_device_ids'] = [device_id]
                elif 'device_ids' in rbn:
                    rbn['device_ids'] = [device_id]
                else:
                    rbn['playback_device_id'] = device_id

    @staticmethod
    def _apply_device_to_case_bn(config, device_id):
        """写入 config 级（整体）背景噪声的播放设备。"""
        if device_id is None:
            return
        cbn = config.get('background_noise')
        if cbn and isinstance(cbn, dict):
            if 'playback_device_ids' in cbn:
                cbn['playback_device_ids'] = [device_id]
            elif 'device_ids' in cbn:
                cbn['device_ids'] = [device_id]
            else:
                cbn['playback_device_id'] = device_id

    def _apply_spl_to_round(self, round_item, spl_value, targets):
        """把声压值写入单轮内各目标。"""
        targets = self._normalize_targets(targets)
        if spl_value is None:
            return
        if 'audio' in targets:
            for audio_config in round_item.get('audios', []):
                audio_config['spl'] = spl_value
        for audio_config in round_item.get('audios', []):
            if 'segmentBackgroundNoise' in targets:
                bn = audio_config.get('background_noise') or audio_config.get('backgroundNoise')
                if bn and isinstance(bn, dict):
                    bn['spl'] = spl_value
            if 'interferers' in targets:
                for inf in audio_config.get('interferers', []):
                    if isinstance(inf, dict):
                        inf['spl'] = spl_value
            if 'voiceprint' in targets:
                vp = audio_config.get('voiceprint')
                if vp and isinstance(vp, dict):
                    vp['spl'] = spl_value
        if 'caseBackgroundNoise' in targets:
            rbn = round_item.get('background_noise') or round_item.get('backgroundNoise')
            if rbn and isinstance(rbn, dict):
                rbn['spl'] = spl_value

    @staticmethod
    def _apply_spl_to_case_bn(config, spl_value):
        """写入 config 级（整体）背景噪声的声压。"""
        if spl_value is None:
            return
        cbn = config.get('background_noise')
        if cbn and isinstance(cbn, dict):
            cbn['spl'] = spl_value

    def _apply_noise_to_round(self, round_item, audio_id, spl, device_ids, targets):
        """把背景噪声写入单轮：轮次级 backgroundNoise + segment 级 background_noise + 干扰人。"""
        targets = self._normalize_targets(targets)
        if 'caseBackgroundNoise' in targets:
            rbn = round_item.get('backgroundNoise')
            if not isinstance(rbn, dict):
                rbn = {}
                round_item['backgroundNoise'] = rbn
            if audio_id is not None:
                rbn['audio_id'] = audio_id
            if spl is not None:
                rbn['spl'] = spl
            if device_ids is not None:
                rbn['device_ids'] = device_ids

        if 'segmentBackgroundNoise' in targets or 'interferers' in targets:
            for audio_config in round_item.get('audios', []):
                if 'segmentBackgroundNoise' in targets:
                    bn = audio_config.get('background_noise')
                    if not isinstance(bn, dict):
                        bn = {}
                        audio_config['background_noise'] = bn
                    if audio_id is not None:
                        bn['audio_id'] = audio_id
                    if spl is not None:
                        bn['spl'] = spl
                    if device_ids is not None:
                        bn['device_ids'] = device_ids
                if 'interferers' in targets:
                    for inf in audio_config.get('interferers', []):
                        if isinstance(inf, dict):
                            if audio_id is not None:
                                inf['audio_id'] = audio_id
                            if spl is not None:
                                inf['spl'] = spl
                            if device_ids is not None:
                                inf['playback_device_id'] = device_ids[0] if device_ids else ''

    @staticmethod
    def _apply_noise_to_case_bn(config, audio_id, spl, device_ids):
        """写入 config 级（整体）背景噪声：audio_id / spl / device_ids。"""
        cbn = config.get('background_noise')
        if not isinstance(cbn, dict):
            cbn = {}
            config['background_noise'] = cbn
        if audio_id is not None:
            cbn['audio_id'] = audio_id
        if spl is not None:
            cbn['spl'] = spl
        if device_ids is not None:
            cbn['device_ids'] = device_ids

    # ---------- 各批量配置更新动作 ----------

    def _batch_update_algorithm_params(self, data, common=None):
        """批量更新用例专属算法参数（全部轮次/指定轮次/逐轮设置 per_round）。"""
        ids = data.get('ids', [])
        algorithm_params = data.get('algorithm_params')
        round_values = data.get('round_values') or {}
        if algorithm_params is None and not round_values:
            return ("更新用例专属参数需要 'algorithm_params' 或 'round_values'", True)

        # 获取轮次范围
        round_mode = data.get('round_mode') or 'all'
        round_numbers = data.get('round_numbers') or []

        test_cases = self.repo.list_testcases_by_ids(ids)
        updated_count = 0
        for tc in test_cases:
            existing = tc.algorithm_params or []

            if round_mode == 'per_round':
                # 逐轮设置：仅 round_values 覆盖的轮次改动，未指定的轮次保留原参数
                last_rn = len([r for r in existing if isinstance(r, dict)])
                new_params_list = []
                seen_rounds = set()
                for item in existing:
                    if not isinstance(item, dict):
                        continue
                    rn = item.get('round_number', 1)
                    rv = self._get_round_value(round_values, rn, last_rn)
                    if rv is not None:
                        params = rv.get('params') if isinstance(rv, dict) and 'params' in rv else rv
                        item['params'] = self._params_to_list(self._normalize_algorithm_params(params))
                    new_params_list.append(item)
                    seen_rounds.add(rn)
                # 补齐 round_values 中出现但用例尚未有的轮次（-1 为动态键，跳过）
                for rn_key, rv in round_values.items():
                    try:
                        rn = int(rn_key)
                    except (TypeError, ValueError):
                        continue
                    if rn < 0 or rn in seen_rounds:
                        continue
                    params = rv.get('params') if isinstance(rv, dict) and 'params' in rv else rv
                    new_params_list.append({
                        'round_number': rn,
                        'params': self._params_to_list(self._normalize_algorithm_params(params)),
                    })
                    seen_rounds.add(rn)
                tc.algorithm_params = new_params_list
            else:
                ap_dict = self._normalize_algorithm_params(algorithm_params)
                new_params = self._params_to_list(ap_dict)

                if round_mode == 'all':
                    # 所有轮次统一设为同一组参数
                    max_round = max([r.get('round_number', 1) for r in existing if isinstance(r, dict)] or [1])
                    tc.algorithm_params = [
                        {'round_number': rn, 'params': new_params}
                        for rn in range(1, max_round + 1)
                    ]
                else:
                    # 只更新指定轮次，保留其他轮次原有参数
                    updated_map = {rn: False for rn in round_numbers}
                    for item in existing:
                        if not isinstance(item, dict):
                            continue
                        rn = item.get('round_number', 1)
                        if rn in round_numbers:
                            item['params'] = new_params
                            updated_map[rn] = True
                    # 追加不存在的轮次
                    for rn in round_numbers:
                        if not updated_map.get(rn):
                            existing.append({'round_number': rn, 'params': new_params})
                    tc.algorithm_params = existing

            tc.updated_at = now_cst()
            updated_count += 1
        self.repo.flush()
        return f"已成功更新 {updated_count} 个用例的专属参数"

    def _batch_update_playback_devices(self, data, common=None):
        """批量更新播放设备（目标人音频/segment 级/case 级背景噪声，支持逐轮设置 per_round）。"""
        ids = data.get('ids', [])
        playback_devices = data.get('playback_devices')
        # 逐轮设置：round_values = {轮次号: {deviceId, targets}}
        round_values = data.get('round_values') or {}
        # 整体（case 级）：只写 config.background_noise
        case_level = data.get('case_level')
        if playback_devices is None and not round_values and not case_level:
            return ("更新播放设备需要 'playback_devices' 或 'round_values'", True)

        # 获取轮次范围和层级目标
        round_mode = data.get('round_mode') or 'all'
        round_numbers = data.get('round_numbers') or []
        targets = self._normalize_targets(data.get('targets')) or ['audio']

        device_id = self._extract_device_id(playback_devices)

        test_cases = self.repo.list_testcases_by_ids(ids)
        updated_count = 0
        for tc in test_cases:
            if (tc.test_type or 'api') != 'e2e':
                continue
            if tc.config:
                config = tc.config.copy()
                rounds = config.get('rounds', [])
                last_rn = len([r for r in rounds if isinstance(r, dict)])

                if round_mode == 'per_round':
                    # 逐轮设置：每轮独立设备/目标，未指定的轮次保留原配置
                    for round_item in rounds:
                        if not isinstance(round_item, dict):
                            continue
                        rn = round_item.get('round_number') or round_item.get('roundNumber')
                        rv = self._get_round_value(round_values, rn, last_rn)
                        if not rv:
                            continue
                        r_device = self._extract_device_id(rv)
                        r_targets = self._round_targets(rv, targets)
                        self._apply_device_to_round(round_item, r_device, r_targets)
                else:
                    for round_item in self._iter_selected_rounds(config, round_mode, round_numbers):
                        self._apply_device_to_round(round_item, device_id, targets)

                # config 级（整体）背景噪声设备：case_level 优先，回退全局设备
                if 'caseBackgroundNoise' in targets:
                    cfg_device_id = self._extract_device_id(case_level) or device_id
                    self._apply_device_to_case_bn(config, cfg_device_id)

                self._update_config_flagged(tc, config)
            tc.updated_at = now_cst()
            updated_count += 1
        self.repo.flush()
        return f"已成功更新 {updated_count} 个用例的播放设备"

    def _batch_update_spl(self, data, common=None):
        """批量更新声压（数字/dict 统一模式 或 逐轮设置 per_round，写入各级音频配置）。"""
        ids = data.get('ids', [])
        spl_data = data.get('spl')
        round_values = data.get('round_values') or {}
        if spl_data is None and not round_values:
            return ("更新声压需要 'spl' 或 'round_values'", True)

        # 获取轮次范围和层级目标
        round_mode = data.get('round_mode') or 'all'
        round_numbers = data.get('round_numbers') or []
        targets = self._normalize_targets(data.get('targets')) or ['audio']
        # 整体（case 级）：只写 config.background_noise
        case_level = data.get('case_level')

        # 兼容 spl 为 float 或 dict
        spl_value = self._extract_value(spl_data)

        test_cases = self.repo.list_testcases_by_ids(ids)
        updated_count = 0
        for tc in test_cases:
            if (tc.test_type or 'api') != 'e2e':
                continue
            if tc.config:
                config = tc.config.copy()
                rounds = config.get('rounds', [])
                last_rn = len([r for r in rounds if isinstance(r, dict)])

                if round_mode == 'per_round':
                    # 逐轮设置：每轮独立声压/目标，未指定的轮次保留原配置
                    for round_item in rounds:
                        if not isinstance(round_item, dict):
                            continue
                        rn = round_item.get('round_number') or round_item.get('roundNumber')
                        rv = self._get_round_value(round_values, rn, last_rn)
                        if not rv:
                            continue
                        r_value = self._extract_value(rv)
                        r_targets = self._round_targets(rv, targets)
                        self._apply_spl_to_round(round_item, r_value, r_targets)
                else:
                    for round_item in self._iter_selected_rounds(config, round_mode, round_numbers):
                        self._apply_spl_to_round(round_item, spl_value, targets)

                # config 级（整体）背景噪声声压：case_level 优先，回退全局声压
                if 'caseBackgroundNoise' in targets:
                    cfg_value = self._extract_value(case_level)
                    if cfg_value is None:
                        cfg_value = spl_value
                    self._apply_spl_to_case_bn(config, cfg_value)

                self._update_config_flagged(tc, config)
            tc.updated_at = now_cst()
            updated_count += 1
        self.repo.flush()
        return f"已成功更新 {updated_count} 个用例的声压"

    def _batch_update_dimensions(self, data, common=None):
        """批量更新评价维度（统一模式 / 逐轮模式，含多轮整体评估维度）。"""
        ids = data.get('ids', [])
        dimensions_data = data.get('dimensions')

        # 获取轮次范围
        round_mode = data.get('round_mode') or 'all'
        round_numbers = data.get('round_numbers') or []
        # 逐轮设置模式：round_dimensions = {1: [...], 2: [...], "-1": [...]}
        # -1 代表"最后一轮"，按用例实际轮次数动态解析
        round_dimensions = data.get('round_dimensions') or {}
        # 多轮整体评估维度（config.dimensions）
        multi_dimensions = data.get('multi_dimensions')

        # 逐轮设置模式不需要 dimensions 参数（可能只需要 round_dimensions 和/或 multi_dimensions）
        # 允许空 dimensions（用于清空所有轮次维度）
        has_single_dims = dimensions_data is not None and len(dimensions_data) > 0
        has_round_dims = round_dimensions and len(round_dimensions) > 0
        has_multi_dims = multi_dimensions is not None

        # 统一模式：dimensions 可以是空列表（清空），但不能是 None 且没有 multi_dimensions
        if round_mode != 'per_round' and dimensions_data is None and not has_multi_dims:
            return ("更新评价维度需要 'dimensions' 或 'multi_dimensions'", True)

        # 逐轮模式：round_dimensions 至少要有数据（即使是空列表也需要有 key）
        if round_mode == 'per_round' and not has_round_dims and not has_multi_dims:
            return ("逐轮设置模式需要 'round_dimensions' 或 'multi_dimensions'", True)

        test_cases = self.repo.list_testcases_by_ids(ids)

        def _build_dim_list(dim_data):
            """从维度数据构建标准化的维度列表"""
            result = []
            for dim in dim_data:
                result.append({
                    'id': dim.get('id'),
                    'name': dim.get('name', ''),
                    'weight': dim.get('weight', 50),
                    'threshold': dim.get('threshold', 60)
                })
            return result

        def _get_round_dims(rn, last_rn):
            """获取轮次对应的维度列表，支持 -1 = 最后一轮"""
            rn_key = str(rn) if isinstance(round_dimensions, dict) else rn
            dims = round_dimensions.get(rn_key) or round_dimensions.get(rn) or []
            # 如果是最后一轮，叠加 -1 的维度
            if rn == last_rn and round_dimensions:
                last_key = '-1' if isinstance(round_dimensions, dict) else -1
                last_dims = round_dimensions.get(last_key) or round_dimensions.get(-1) or []
                if last_dims:
                    existing_ids = {d.get('id') for d in dims}
                    for d in last_dims:
                        if d.get('id') not in existing_ids:
                            dims = list(dims) + [d]
            return dims

        updated_count = 0
        for tc in test_cases:
            if tc.config:
                config = tc.config.copy()
                rounds = config.get('rounds', [])
                last_rn = len(rounds) if rounds else 0

                if round_mode == 'per_round':
                    # 逐轮设置模式：每个轮次独立设置维度
                    for round_item in rounds:
                        if not isinstance(round_item, dict):
                            continue
                        rn = round_item.get('round_number') or round_item.get('roundNumber')
                        round_dim_data = _get_round_dims(rn, last_rn)
                        new_dim_list = _build_dim_list(round_dim_data)
                        if 'evaluation' not in round_item:
                            round_item['evaluation'] = {}
                        round_item['evaluation']['dimensions'] = new_dim_list
                        logger.debug(f"[update_dimensions] 用例 {tc.id} 轮次 {rn} 设置维度 {len(new_dim_list)} 个")
                elif dimensions_data is not None:
                    # 统一模式：所有/指定轮次共用同一套维度（含空列表=清空）
                    new_dim_list = _build_dim_list(dimensions_data)
                    for round_item in rounds:
                        if not isinstance(round_item, dict):
                            continue
                        # 轮次过滤
                        rn = round_item.get('round_number') or round_item.get('roundNumber')
                        if round_mode == 'specific' and round_numbers:
                            is_selected = rn in round_numbers or \
                                (rn == last_rn and -1 in round_numbers)
                            if not is_selected:
                                continue
                        if 'evaluation' not in round_item:
                            round_item['evaluation'] = {}
                        round_item['evaluation']['dimensions'] = new_dim_list

                # 多轮整体评估维度（config.dimensions）：非 None 就写入（空列表=清空）
                if multi_dimensions is not None:
                    config['dimensions'] = _build_dim_list(multi_dimensions)
                    logger.debug(f"[update_dimensions] 用例 {tc.id} 设置整体评估维度 {len(multi_dimensions)} 个")

                self._update_config_flagged(tc, config)
            tc.updated_at = now_cst()
            updated_count += 1
        self.repo.flush()
        return f"已成功更新 {updated_count} 个用例的评价维度"

    def _batch_update_noise(self, data, common=None):
        """批量更新背景噪声配置（区分整体 case_level 与轮次维度）。

        - case_level（整体）：只写 config.background_noise（跨轮次的整体背景噪声）
        - round_values / 全局字段（轮次）：写 round 级 backgroundNoise、segment 级 background_noise、干扰人
        """
        ids = data.get('ids', [])
        audio_id = data.get('noise_audio_id')
        spl = data.get('noise_spl')
        device_ids = data.get('noise_device_ids') or []

        # 获取轮次范围和层级目标
        round_mode = data.get('round_mode') or 'all'
        round_numbers = data.get('round_numbers') or []
        targets = self._normalize_targets(data.get('targets')) or ['caseBackgroundNoise', 'segmentBackgroundNoise']
        # 逐轮设置：round_values = {轮次号: {audioId, spl, deviceIds, targets}}
        round_values = data.get('round_values') or {}
        # 整体（case 级）：只写 config.background_noise
        case_level = data.get('case_level')

        test_cases = self.repo.list_testcases_by_ids(ids)
        updated_count = 0
        for tc in test_cases:
            if (tc.test_type or 'api') != 'e2e':
                continue
            config = (tc.config or {}).copy()
            rounds = config.get('rounds', [])
            last_rn = len([r for r in rounds if isinstance(r, dict)])

            if round_mode == 'per_round':
                # 逐轮设置：每轮独立噪声，未指定的轮次保留原配置
                for round_item in rounds:
                    if not isinstance(round_item, dict):
                        continue
                    rn = round_item.get('round_number') or round_item.get('roundNumber')
                    rv = self._get_round_value(round_values, rn, last_rn)
                    if not rv or not isinstance(rv, dict):
                        continue
                    r_audio_id, r_spl, r_device_ids = self._extract_noise(rv)
                    r_targets = rv.get('targets') or targets
                    self._apply_noise_to_round(round_item, r_audio_id, r_spl, r_device_ids, r_targets)
            else:
                for round_item in self._iter_selected_rounds(config, round_mode, round_numbers):
                    self._apply_noise_to_round(round_item, audio_id, spl, device_ids, targets)

            # 整体（case 级）背景噪声：case_level 优先，回退全局噪声字段。
            # per_round 模式下整体噪声已由 case_level 承载，不回退全局字段
            # （避免把逐轮 mode 下的全局残留值误写进整体背景噪声）。
            cl_audio_id, cl_spl, cl_device_ids = self._extract_noise(case_level)
            cl_provided = any(v is not None for v in (cl_audio_id, cl_spl, cl_device_ids))
            if cl_provided:
                self._apply_noise_to_case_bn(config, cl_audio_id, cl_spl, cl_device_ids)
            elif 'caseBackgroundNoise' in targets and not (round_mode == 'per_round' and round_values):
                self._apply_noise_to_case_bn(config, audio_id, spl, device_ids)

            self._update_config_flagged(tc, config)
            updated_count += 1
        self.repo.flush()
        return f"已成功更新 {updated_count} 个用例的噪声配置"
