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


class TestCaseConfigUpdateMixin:
    """测试用例批量配置更新 Mixin。"""

    # ---------- 公共辅助：轮次遍历 / JSON 字段落库 ----------

    @staticmethod
    def _iter_selected_rounds(config, round_mode, round_numbers):
        """按 round_mode 遍历轮次：all 返回全部，specific 按轮次号过滤。

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

    # ---------- 各批量配置更新动作 ----------

    def _batch_update_algorithm_params(self, data, common=None):
        """批量更新用例专属算法参数（支持全部轮次/指定轮次）。"""
        ids = data.get('ids', [])
        algorithm_params = data.get('algorithm_params')
        if algorithm_params is None:
            return ("更新用例专属参数需要 'algorithm_params'", True)

        # 获取轮次范围
        round_mode = data.get('round_mode') or 'all'
        round_numbers = data.get('round_numbers') or []

        test_cases = self.repo.list_testcases_by_ids(ids)
        updated_count = 0
        for tc in test_cases:
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

            new_params = [{'field_code': k, 'field_value': v} for k, v in ap_dict.items()]

            if round_mode == 'all':
                # 所有轮次统一设为同一组参数
                existing = tc.algorithm_params or []
                max_round = max([r.get('round_number', 1) for r in existing if isinstance(r, dict)] or [1])
                tc.algorithm_params = [
                    {'round_number': rn, 'params': new_params}
                    for rn in range(1, max_round + 1)
                ]
            else:
                # 只更新指定轮次，保留其他轮次原有参数
                existing = tc.algorithm_params or []
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
        """批量更新播放设备（目标人音频/segment 级/case 级背景噪声）。"""
        ids = data.get('ids', [])
        playback_devices = data.get('playback_devices')
        if playback_devices is None:
            return ("更新播放设备需要 'playback_devices'", True)

        # 获取轮次范围和层级目标
        round_mode = data.get('round_mode') or 'all'
        round_numbers = data.get('round_numbers') or []
        targets = data.get('targets') or ['audio']

        device_id = playback_devices.get('deviceId') or playback_devices.get('device_id')

        test_cases = self.repo.list_testcases_by_ids(ids)
        updated_count = 0
        for tc in test_cases:
            if (tc.test_type or 'api') != 'e2e':
                continue
            if tc.config:
                config = tc.config.copy()

                for round_item in self._iter_selected_rounds(config, round_mode, round_numbers):
                    # 1. 目标人音频
                    if 'audio' in targets and device_id is not None:
                        for audio_config in round_item.get('audios', []):
                            audio_config['playback_device_id'] = device_id

                    # 2-5. segment 级背景噪声/干扰人/声纹
                    for audio_config in round_item.get('audios', []):
                        if 'segmentBackgroundNoise' in targets and device_id is not None:
                            bn = audio_config.get('background_noise') or audio_config.get('backgroundNoise')
                            if bn and isinstance(bn, dict):
                                bn['playback_device_id'] = device_id
                        if 'interferers' in targets and device_id is not None:
                            for inf in audio_config.get('interferers', []):
                                if isinstance(inf, dict):
                                    inf['playback_device_id'] = device_id
                        if 'voiceprint' in targets and device_id is not None:
                            vp = audio_config.get('voiceprint')
                            if vp and isinstance(vp, dict):
                                vp['playback_device_id'] = device_id

                    # 4. case 级 / round 级背景噪声
                    if 'caseBackgroundNoise' in targets and device_id is not None:
                        rbn = round_item.get('background_noise') or round_item.get('backgroundNoise')
                        if rbn and isinstance(rbn, dict):
                            if 'playback_device_ids' in rbn:
                                rbn['playback_device_ids'] = [device_id]
                            elif 'device_ids' in rbn:
                                rbn['device_ids'] = [device_id]
                            else:
                                rbn['playback_device_id'] = device_id

                # config 级背景噪声
                if 'caseBackgroundNoise' in targets and device_id is not None:
                    cbn = config.get('background_noise')
                    if cbn and isinstance(cbn, dict):
                        if 'playback_device_ids' in cbn:
                            cbn['playback_device_ids'] = [device_id]
                        elif 'device_ids' in cbn:
                            cbn['device_ids'] = [device_id]
                        else:
                            cbn['playback_device_id'] = device_id

                self._update_config_flagged(tc, config)
            tc.updated_at = now_cst()
            updated_count += 1
        self.repo.flush()
        return f"已成功更新 {updated_count} 个用例的播放设备"

    def _batch_update_spl(self, data, common=None):
        """批量更新声压（支持数值或 dict 形式，写入各级音频配置）。"""
        ids = data.get('ids', [])
        spl_data = data.get('spl')
        if spl_data is None:
            return ("更新声压需要 'spl'", True)

        # 获取轮次范围和层级目标
        round_mode = data.get('round_mode') or 'all'
        round_numbers = data.get('round_numbers') or []
        targets = data.get('targets') or ['audio']

        # 兼容 spl 为 float 或 dict
        if isinstance(spl_data, (int, float)):
            spl_value = float(spl_data)
        else:
            spl_value = spl_data.get('value')

        test_cases = self.repo.list_testcases_by_ids(ids)
        updated_count = 0
        for tc in test_cases:
            if (tc.test_type or 'api') != 'e2e':
                continue
            if tc.config:
                config = tc.config.copy()

                for round_item in self._iter_selected_rounds(config, round_mode, round_numbers):
                    # 1. 目标人音频
                    if 'audio' in targets:
                        for audio_config in round_item.get('audios', []):
                            if spl_value is not None:
                                audio_config['spl'] = spl_value

                    # 2 & 3. segment 级背景噪声 / 干扰人 / 声纹（在 audio 内部）
                    for audio_config in round_item.get('audios', []):
                        # segment 级背景噪声
                        if 'segmentBackgroundNoise' in targets:
                            bn = audio_config.get('background_noise') or audio_config.get('backgroundNoise')
                            if bn and isinstance(bn, dict):
                                if spl_value is not None:
                                    bn['spl'] = spl_value
                        # 干扰人
                        if 'interferers' in targets:
                            for inf in audio_config.get('interferers', []):
                                if isinstance(inf, dict) and spl_value is not None:
                                    inf['spl'] = spl_value
                        # 声纹
                        if 'voiceprint' in targets:
                            vp = audio_config.get('voiceprint')
                            if vp and isinstance(vp, dict) and spl_value is not None:
                                vp['spl'] = spl_value

                    # 4. case 级 / round 级背景噪声
                    if 'caseBackgroundNoise' in targets:
                        rbn = round_item.get('background_noise') or round_item.get('backgroundNoise')
                        if rbn and isinstance(rbn, dict) and spl_value is not None:
                            rbn['spl'] = spl_value

                # config 级背景噪声
                if 'caseBackgroundNoise' in targets:
                    cbn = config.get('background_noise')
                    if cbn and isinstance(cbn, dict) and spl_value is not None:
                        cbn['spl'] = spl_value

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
        """批量更新背景噪声配置（round/case/config 级 + segment 级/干扰人）。"""
        ids = data.get('ids', [])
        audio_id = data.get('noise_audio_id')
        spl = data.get('noise_spl')
        device_ids = data.get('noise_device_ids') or []

        # 获取轮次范围和层级目标
        round_mode = data.get('round_mode') or 'all'
        round_numbers = data.get('round_numbers') or []
        targets = data.get('targets') or ['caseBackgroundNoise', 'segmentBackgroundNoise']

        test_cases = self.repo.list_testcases_by_ids(ids)
        updated_count = 0
        for tc in test_cases:
            if (tc.test_type or 'api') != 'e2e':
                continue
            config = (tc.config or {}).copy()

            for round_item in self._iter_selected_rounds(config, round_mode, round_numbers):
                # round 级 / case 级背景噪声
                if 'caseBackgroundNoise' in targets:
                    if 'backgroundNoise' not in round_item:
                        round_item['backgroundNoise'] = {}
                    if audio_id is not None:
                        round_item['backgroundNoise']['audio_id'] = audio_id
                    if spl is not None:
                        round_item['backgroundNoise']['spl'] = spl
                    if device_ids is not None:
                        round_item['backgroundNoise']['device_ids'] = device_ids

                # segment 级背景噪声 + 干扰人
                if 'segmentBackgroundNoise' in targets or 'interferers' in targets:
                    for audio_config in round_item.get('audios', []):
                        if 'segmentBackgroundNoise' in targets:
                            bn = audio_config.get('background_noise') or audio_config.get('backgroundNoise')
                            if bn is None:
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

            # config 级背景噪声
            if 'caseBackgroundNoise' in targets:
                cbn = config.get('background_noise')
                if cbn is None:
                    cbn = {}
                    config['background_noise'] = cbn
                if audio_id is not None:
                    cbn['audio_id'] = audio_id
                if spl is not None:
                    cbn['spl'] = spl
                if device_ids is not None:
                    cbn['device_ids'] = device_ids

            self._update_config_flagged(tc, config)
            updated_count += 1
        self.repo.flush()
        return f"已成功更新 {updated_count} 个用例的噪声配置"
