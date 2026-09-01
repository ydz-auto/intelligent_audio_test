# -*- coding: utf-8 -*-
"""测试用例创建 - 标注数据处理 Mixin

从 audio_testcase_creation_service.py 拆分出的职责：
- _inject_spl_and_device_from_annotations：从标注 JSON 提取 spl 和 playback_device_name
- _extract_case_params_from_annotations：从原始标注提取用例参数
"""
import re


class CreationAnnotationMixin:
    """原始标注（raw_annotations）数据注入与参数提取职责"""

    def _inject_spl_and_device_from_annotations(self, rounds_resolved, raw_annotations,
                                                  tt, effective_playback_device_id, spl):
        """从标注 JSON 提取 spl 和 playback_device_name

        通过 ACL 仓储 ListPlaybackDevices 获取设备 name→id 映射，避免直接 import PO。
        """
        if not raw_annotations:
            return

        dev_name_to_id = {}
        devices = self._playback_acl.list_playback_devices()
        for dev in devices:
            if not dev.get('is_deleted'):
                dev_name_to_id.setdefault(dev.get('name'), dev.get('id'))

        for round_item in rounds_resolved:
            if not isinstance(round_item, dict):
                continue
            for audio_item in round_item.get('audios', []):
                if not isinstance(audio_item, dict):
                    continue
                if not audio_item.get('playback_device_id'):
                    dev_name = audio_item.get('playback_device_name')
                    if dev_name and dev_name in dev_name_to_id:
                        audio_item['playback_device_id'] = dev_name_to_id[dev_name]

        for round_item in rounds_resolved:
            if not isinstance(round_item, dict):
                continue
            for audio_item in round_item.get('audios', []):
                if not isinstance(audio_item, dict):
                    continue
                need_spl = audio_item.get('spl') is None
                need_dev = not audio_item.get('playback_device_id')
                if not need_spl and not need_dev:
                    continue
                for ann in raw_annotations:
                    data = ann.get('data')
                    if not isinstance(data, dict):
                        continue
                    segments = data.get('segments', [])
                    if not isinstance(segments, list):
                        continue
                    for seg in segments:
                        if not isinstance(seg, dict):
                            continue
                        if need_spl and audio_item.get('spl') is None:
                            v = seg.get('spl')
                            if v is not None:
                                try:
                                    audio_item['spl'] = float(v)
                                except (TypeError, ValueError):
                                    audio_item['spl'] = v
                                need_spl = False
                        if need_dev and not audio_item.get('playback_device_id'):
                            dev_name = seg.get('playback_device_name') or seg.get('playbackDeviceName')
                            if dev_name and dev_name in dev_name_to_id:
                                audio_item['playback_device_id'] = dev_name_to_id[dev_name]
                                need_dev = False
                            elif not dev_name:
                                v = seg.get('playback_device_id') or seg.get('playbackDeviceId')
                                if v:
                                    audio_item['playback_device_id'] = v
                                    need_dev = False
                        if not need_spl and not need_dev:
                            break
                    if not need_spl and not need_dev:
                        break
            if tt == 'e2e':
                for audio_item in round_item.get('audios', []):
                    if isinstance(audio_item, dict) and not audio_item.get('playback_device_id'):
                        audio_item['playback_device_id'] = effective_playback_device_id
                    if isinstance(audio_item, dict) and audio_item.get('spl') is None:
                        audio_item['spl'] = spl if spl else 65.0

    def _extract_case_params_from_annotations(self, rounds_resolved, raw_annotations,
                                               algorithm_type, tt, algo_params_col):
        """从原始标注提取用例参数

        通过 ACL 仓储调用 algorithm_service.ListCaseParams 获取参数，避免直接 import PO。
        """
        if not (algorithm_type and raw_annotations):
            return

        case_params_list = self._algorithm_acl.list_case_params(algorithm_type)

        scoped_params = [p for p in case_params_list if p.get('scope') == 'common' or p.get('scope') == tt]
        if not scoped_params:
            return

        # 预查音频文件名→ID、设备名→ID 映射，用于 interferers 的 ID 解析
        audio_name_to_id_map, dev_name_to_id = self._build_name_to_id_maps()

        for round_item in rounds_resolved:
            if not isinstance(round_item, dict):
                continue
            round_audios = round_item.get('audios', [])
            if not isinstance(round_audios, list):
                continue
            round_audio_ids = [a.get('audio_id') for a in round_audios if isinstance(a, dict) and a.get('audio_id')]
            if not round_audio_ids:
                continue
            extracted_params = []
            for param in scoped_params:
                param_code = param.get('param_code')
                field_path = param.get('field_path') or param_code
                ann_code = param.get('annotation_code') or algorithm_type
                matched_anns = [a for a in raw_annotations if a.get('code') == ann_code]
                if not matched_anns:
                    matched_anns = raw_annotations
                value = None
                for ann in matched_anns:
                    data = ann.get('data')
                    if data is None:
                        continue
                    if isinstance(data, str):
                        value = data
                        break
                    if isinstance(data, dict):
                        value = self._extract_field_value_from_annotation_data(
                            data, field_path
                        )
                        if value is not None:
                            break
                if value is not None:
                    # 如果是 interferers 字段，对提取出的每个干扰人做 ID 解析
                    # （audio 文件名→audio_id, playback_device_name→playback_device_id）
                    if param_code == 'interferers' and isinstance(value, list):
                        self._resolve_interferer_ids(value, audio_name_to_id_map, dev_name_to_id)
                    extracted_params.append({'field_code': param_code, 'field_value': value})

            round_number = round_item.get('round_number', 1)
            round_ap_entry = self._ensure_round_params_entry(algo_params_col, round_number)
            existing_codes = set(p.get('field_code') for p in round_ap_entry.get('params', []))
            for p in extracted_params:
                if p['field_code'] not in existing_codes:
                    round_ap_entry.setdefault('params', []).append(p)
                    existing_codes.add(p['field_code'])

    @staticmethod
    def _get_seg_field(seg, key):
        """从 segment 字典取字段：优先精确 key，其次驼峰转蛇形兜底"""
        if seg.get(key) is not None:
            return seg.get(key)
        snake = re.sub(r'([A-Z])', r'_\1', key).lower()
        return seg.get(snake)

    @classmethod
    def _extract_field_value_from_annotation_data(cls, data, field_path):
        """从标注 data 字典按 field_path（segments[].xxx 形式）提取首个有效值。

        过滤掉空数组/空字符串（如 interferers: [] 不应算作有效值）。
        """
        effective_fp = field_path
        if 'segments[]' not in effective_fp:
            effective_fp = f'segments[].{effective_fp}'
        if 'segments[]' in effective_fp:
            parts = effective_fp.split('[].')
            arr_key = parts[0]
            field_key = parts[1] if len(parts) > 1 else None

            arr = data.get(arr_key, [])
            if isinstance(arr, list) and field_key:
                collected = [
                    cls._get_seg_field(seg, field_key) for seg in arr
                    if isinstance(seg, dict) and cls._get_seg_field(seg, field_key) is not None
                ]
                collected = [c for c in collected if not (isinstance(c, (list, str, dict)) and len(c) == 0)]
                if collected:
                    return collected[0] if len(collected) == 1 else collected
        return None

    @staticmethod
    def _resolve_interferer_ids(value, audio_name_to_id_map, dev_name_to_id):
        """对 interferers 列表中每个干扰人做 ID 解析。

        audio 文件名→audio_id, playback_device_name→playback_device_id。
        """
        for _itf in value:
            if not isinstance(_itf, dict):
                continue
            if not _itf.get('audio_id'):
                _fn = _itf.get('audio') or _itf.get('audio_name')
                if _fn and _fn in audio_name_to_id_map:
                    _itf['audio_id'] = audio_name_to_id_map[_fn]
            if not _itf.get('playback_device_id'):
                _dn = _itf.get('playback_device_name')
                if _dn and _dn in dev_name_to_id:
                    _itf['playback_device_id'] = dev_name_to_id[_dn]

    @staticmethod
    def _ensure_round_params_entry(algo_params_col, round_number):
        """获取（或创建）algo_params_col 中指定轮次的参数条目"""
        for entry in algo_params_col:
            if entry.get('round_number') == round_number:
                return entry
        round_ap_entry = {'round_number': round_number, 'params': []}
        algo_params_col.append(round_ap_entry)
        return round_ap_entry
