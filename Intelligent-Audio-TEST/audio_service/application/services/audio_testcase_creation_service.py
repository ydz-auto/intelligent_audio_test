# -*- coding: utf-8 -*-
"""音频测试用例创建应用服务（跨域协调）

从 audio_crud_service.py 中提取的测试用例创建相关逻辑：
- _create_test_case_from_audio
- _resolve_rounds_and_strip_params
- _inject_spl_and_device_from_annotations
- _extract_case_params_from_annotations
- _build_config_and_apply_dimensions（静态方法 → 实例方法）
- _refresh_test_cases_for_audios
"""
import copy
import json as _json
import logging

from shared.utils.query_utils import now_cst
from shared.utils.log_handler import log_not_emit
from audio_service.domain.repositories.audio_repository_abc import AudioRepositoryInterface
from audio_service.infrastructure.persistence.audio_repository import audio_repository
from audio_service.application.services.audio_annotation_service import audio_annotation_service

logger = logging.getLogger(__name__)


class AudioTestCaseCreationService:
    """音频测试用例创建应用服务（跨域协调）"""

    def __init__(self, repo: AudioRepositoryInterface = None):
        self.repo = repo or audio_repository
        self._annotation_service = audio_annotation_service
        # ACL 仓储（跨域只读/读写查询）
        from audio_service.infrastructure.acl.algorithm_acl_repository import (
            AlgorithmACLRepositoryImpl,
        )
        from audio_service.infrastructure.acl.playback_acl_repository import (
            PlaybackConfigACLRepositoryImpl,
        )
        from audio_service.infrastructure.acl.testcase_acl_repository import (
            TestCaseConfigACLRepositoryImpl,
        )
        self._algorithm_acl = AlgorithmACLRepositoryImpl()
        self._playback_acl = PlaybackConfigACLRepositoryImpl()
        self._testcase_acl = TestCaseConfigACLRepositoryImpl()

    def create_test_case_from_audio(self, audio_id, test_types, audio_tags,
                                    playback_device_id=None, spl=65.0, noise_spl=60.0,
                                    noise_audio_id=None, group_name=None,
                                    dimensions_data=None, algorithm_type=None,
                                    algorithm_params=None, rounds_config=None,
                                    inherit_tags=True, raw_annotations=None,
                                    noise_device_ids=None, case_background_noise=None):
        """从音频创建测试用例

        通过 ACL 仓储调用 gRPC TestCaseConfigService 创建测试用例（含分组/标签/参考参数），
        避免直接 import task_service PO。
        """
        if isinstance(test_types, str):
            test_types = [test_types.strip()]
        else:
            test_types = [tt.strip() if isinstance(tt, str) else tt for tt in test_types]

        audio = self.repo.get_audio(audio_id)
        if not audio:
            return None

        effective_group_name = group_name if group_name else '音频上传生成'

        effective_playback_device_id = playback_device_id
        if 'e2e' in test_types and not effective_playback_device_id:
            # 通过 ACL 仓储查找第一个 device_type='dry' 的播放设备
            devices = self._playback_acl.list_playback_devices()
            for dev in devices:
                if dev.get('device_type') == 'dry' and not dev.get('is_deleted'):
                    effective_playback_device_id = dev.get('id')
                    break

            if not effective_playback_device_id:
                raise ValueError(
                    "e2e 测试类型需要一个 device_type='dry' 的播放设备，"
                    "但未找到可用设备。请先在设备管理中配置播放设备。"
                )

        # 秒传场景下 audio.name 可能是旧的改名（如 "1.wav"），
        # 优先用 rounds_config 里前端传的 audio_name 作为用例名
        tc_audio_name = audio.name
        if rounds_config:
            for r in rounds_config:
                if not isinstance(r, dict):
                    continue
                for a in r.get('audios', []):
                    if isinstance(a, dict) and a.get('audio_name'):
                        tc_audio_name = a['audio_name']
                        break
                if tc_audio_name != audio.name:
                    break
        base_name = f"测试用例_{tc_audio_name}"
        if not test_types:
            test_types = ['api']

        created_tc_ids = []

        for tt in test_types:
            if len(test_types) > 1:
                test_case_name = f"{base_name}_{tt}"
            else:
                test_case_name = base_name

            # 名称冲突检查：通过 ACL 仓储 ListTestCases 搜索同名用例
            list_data = self._testcase_acl.list_testcases(
                page=1, per_page=50, keyword=test_case_name,
            )
            if list_data:
                for item in list_data.get('items', []):
                    if item.get('name') == test_case_name:
                        test_case_name = f"{test_case_name}_{now_cst().strftime('%H%M%S')}"
                        break

            rounds_resolved, algo_params_col = self._resolve_rounds_and_strip_params(
                tt, audio_id, audio, spl, effective_playback_device_id,
                rounds_config, algorithm_params
            )

            self._inject_spl_and_device_from_annotations(
                rounds_resolved, raw_annotations, tt, effective_playback_device_id, spl
            )

            self._extract_case_params_from_annotations(
                rounds_resolved, raw_annotations, algorithm_type, tt, algo_params_col
            )

            # 解析 segment 级背景噪声和干扰人：文件名→audio_id，设备名→device_ids/playback_device_id
            self._resolve_bg_noise_and_interferers_ids(rounds_resolved)

            # case 级背景噪声（rounds 外层）ID 解析
            if case_background_noise and isinstance(case_background_noise, dict):
                self._resolve_audio_field(case_background_noise)
                self._resolve_device_fields(case_background_noise)

            config = self._build_config_and_apply_dimensions(
                audio, rounds_resolved, dimensions_data, tt, noise_spl, noise_audio_id,
                noise_device_ids, case_background_noise
            )

            # 通过 ACL 仓储创建测试用例
            # （task_service 侧自动处理分组创建/标签关联/参考参数生成）
            create_data = {
                'name': test_case_name,
                'description': f"自动从音频 '{audio.name}' 创建的测试用例",
                'group': effective_group_name,
                'test_type': tt,
                'algorithm_type': algorithm_type,
                'config': config,
                'algorithm_params': algo_params_col if algo_params_col else None,
            }
            if inherit_tags and audio_tags:
                create_data['tags'] = list(audio_tags)

            log_not_emit('DEBUG', 'audio_controller',
                         f'tc.algorithm_params={_json.dumps(algo_params_col, ensure_ascii=False)[:300]}',
                         category='audio')

            resp_data = self._testcase_acl.create_testcase_config(create_data)
            if resp_data:
                tc_id = resp_data.get('id')
                if tc_id:
                    created_tc_ids.append(tc_id)

        return created_tc_ids

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
                        effective_fp = field_path
                        if 'segments[]' not in effective_fp:
                            effective_fp = f'segments[].{effective_fp}'
                        if 'segments[]' in effective_fp:
                            parts = effective_fp.split('[].')
                            arr_key = parts[0]
                            field_key = parts[1] if len(parts) > 1 else None

                            def _get_seg_field(seg, key):
                                if seg.get(key) is not None:
                                    return seg.get(key)
                                import re
                                snake = re.sub(r'([A-Z])', r'_\1', key).lower()
                                return seg.get(snake)

                            arr = data.get(arr_key, [])
                            if isinstance(arr, list) and field_key:
                                collected = [
                                    _get_seg_field(seg, field_key) for seg in arr
                                    if isinstance(seg, dict) and _get_seg_field(seg, field_key) is not None
                                ]
                                # 过滤掉空数组/空字符串（如 interferers: [] 不应算作有效值）
                                collected = [c for c in collected if not (isinstance(c, (list, str, dict)) and len(c) == 0)]
                                if collected:
                                    value = collected[0] if len(collected) == 1 else collected
                                    break
                if value is not None:
                    # 如果是 interferers 字段，对提取出的每个干扰人做 ID 解析
                    # （audio 文件名→audio_id, playback_device_name→playback_device_id）
                    if param_code == 'interferers' and isinstance(value, list):
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
                    extracted_params.append({'field_code': param_code, 'field_value': value})

            round_number = round_item.get('round_number', 1)
            round_ap_entry = None
            for entry in algo_params_col:
                if entry.get('round_number') == round_number:
                    round_ap_entry = entry
                    break
            if not round_ap_entry:
                round_ap_entry = {'round_number': round_number, 'params': []}
                algo_params_col.append(round_ap_entry)
            existing_codes = set(p.get('field_code') for p in round_ap_entry.get('params', []))
            for p in extracted_params:
                if p['field_code'] not in existing_codes:
                    round_ap_entry.setdefault('params', []).append(p)
                    existing_codes.add(p['field_code'])

    def _build_name_to_id_maps(self):
        """预查音频文件名→ID、设备名→ID 映射（用于 interferers/background_noise 的 ID 解析）。

        通过 ACL 仓储获取设备列表，避免直接 import PO。
        音频列表通过仓储分页获取前 1000 条构建映射，超出部分逐个查库兜底。
        """
        # 设备名→ID 映射
        dev_name_to_id = {}
        devices = self._playback_acl.list_playback_devices()
        for dev in devices:
            if not dev.get('is_deleted'):
                dev_name_to_id.setdefault(dev.get('name'), dev.get('id'))
        # 音频文件名→ID 映射（通过仓储批量查库，取前 1000 条）
        audio_name_to_id_map = {}
        try:
            pagination = self.repo.list_audios({'page': 1, 'per_page': 1000})
            items = getattr(pagination, 'items', []) or []
            for _a in items:
                _name = getattr(_a, 'name', None)
                if _name:
                    audio_name_to_id_map.setdefault(_name, getattr(_a, 'id', None))
                _orig = getattr(_a, 'original_filename', None)
                if _orig:
                    audio_name_to_id_map.setdefault(_orig, getattr(_a, 'id', None))
        except Exception:
            pass
        return audio_name_to_id_map, dev_name_to_id

    def _resolve_audio_field(self, payload, audio_name_to_id_map=None):
        """把 payload 里的 audio(文件名)/audio_name 转成 audio_id。"""
        if not isinstance(payload, dict):
            return
        if not payload.get('audio_id'):
            _fn = payload.get('audio') or payload.get('audio_name')
            if _fn:
                # 优先用预查映射
                if audio_name_to_id_map and _fn in audio_name_to_id_map:
                    payload['audio_id'] = audio_name_to_id_map[_fn]
                else:
                    # 逐个查库兜底
                    try:
                        found = self.repo.find_audio_by_name(_fn)
                        if found:
                            payload['audio_id'] = getattr(found, 'id', None)
                    except Exception:
                        pass

    def _resolve_device_fields(self, payload, dev_name_to_id=None):
        """把 payload 里的 playback_device_name(s)/device_names 转成 device_ids。"""
        if not isinstance(payload, dict):
            return
        if not payload.get('device_ids'):
            names = (
                payload.get('playback_device_names')
                or payload.get('device_names')
            )
            if names and isinstance(names, list):
                ids = []
                for n in names:
                    if not n:
                        continue
                    # 优先用预查映射
                    if dev_name_to_id and n in dev_name_to_id:
                        ids.append(dev_name_to_id[n])
                    else:
                        # 逐个查库兜底
                        try:
                            dev = self._playback_acl.find_playback_device_by_name(n)
                            if dev:
                                ids.append(dev.get('id'))
                        except Exception:
                            pass
                if ids:
                    payload['device_ids'] = ids
            else:
                single = payload.get('playback_device_name')
                if single:
                    if dev_name_to_id and single in dev_name_to_id:
                        payload['device_ids'] = [dev_name_to_id[single]]
                    else:
                        try:
                            dev = self._playback_acl.find_playback_device_by_name(single)
                            if dev:
                                payload['device_ids'] = [dev.get('id')]
                        except Exception:
                            pass

    def _resolve_bg_noise_and_interferers_ids(self, rounds_resolved):
        """解析 segment 级背景噪声和干扰人：文件名→audio_id，设备名→device_ids/playback_device_id。

        无论 raw_annotations 是否存在都执行（前端可能已直接在 rounds_config 中传入）。
        """
        audio_name_to_id_map, dev_name_to_id = self._build_name_to_id_maps()

        for round_item in rounds_resolved:
            if not isinstance(round_item, dict):
                continue
            # 轮次级背景噪声（round 级）
            _r_bg = round_item.get('background_noise')
            if isinstance(_r_bg, dict):
                self._resolve_audio_field(_r_bg, audio_name_to_id_map)
                self._resolve_device_fields(_r_bg, dev_name_to_id)
            for audio_item in round_item.get('audios', []):
                if not isinstance(audio_item, dict):
                    continue
                # segment 级背景噪声
                _seg_bg = audio_item.get('background_noise')
                if isinstance(_seg_bg, dict):
                    self._resolve_audio_field(_seg_bg, audio_name_to_id_map)
                    self._resolve_device_fields(_seg_bg, dev_name_to_id)
                # segment 级干扰人：audio→audio_id，playback_device_name→playback_device_id
                _interferers = audio_item.get('interferers')
                if isinstance(_interferers, list):
                    for _itf in _interferers:
                        if not isinstance(_itf, dict):
                            continue
                        # audio 文件名 → audio_id
                        if not _itf.get('audio_id'):
                            _fn = _itf.get('audio') or _itf.get('audio_name')
                            if _fn:
                                if _fn in audio_name_to_id_map:
                                    _itf['audio_id'] = audio_name_to_id_map[_fn]
                                else:
                                    try:
                                        found = self.repo.find_audio_by_name(_fn)
                                        if found:
                                            _itf['audio_id'] = getattr(found, 'id', None)
                                    except Exception:
                                        pass
                        # playback_device_name → playback_device_id
                        if not _itf.get('playback_device_id'):
                            _dn = _itf.get('playback_device_name')
                            if _dn:
                                if _dn in dev_name_to_id:
                                    _itf['playback_device_id'] = dev_name_to_id[_dn]
                                else:
                                    try:
                                        dev = self._playback_acl.find_playback_device_by_name(_dn)
                                        if dev:
                                            _itf['playback_device_id'] = dev.get('id')
                                    except Exception:
                                        pass

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

    def refresh_test_cases_for_audios(self, audio_ids, algorithm_type=None):
        """按 audio_id 反查 config.rounds[].audios[].audio_id 关联的 TestCase

        通过 ACL 仓储 ListTestCases 分页获取所有用例，在本地过滤出引用了
        目标 audio_id 的用例；再通过 ACL 仓储 UpdateTestCaseConfig 更新
        algorithm_params，由 task_service 侧触发参考参数刷新。
        """
        target_ids = set(audio_ids)

        # 分页获取所有测试用例，本地过滤出引用目标 audio_id 的用例
        affected_tcs = []
        page = 1
        per_page = 100
        while True:
            data = self._testcase_acl.list_testcases(
                page=page, per_page=per_page, include_deleted=False,
            )
            if not data:
                break

            items = data.get('items', [])
            total = data.get('total', 0)

            for tc in items:
                config = tc.get('config') or {}
                rounds = config.get('rounds', [])
                if not isinstance(rounds, list):
                    continue
                found = False
                for round_item in rounds:
                    if not isinstance(round_item, dict):
                        continue
                    for audio_item in round_item.get('audios', []):
                        if isinstance(audio_item, dict) and audio_item.get('audio_id') in target_ids:
                            found = True
                            break
                    if found:
                        break
                if found:
                    affected_tcs.append(tc)

            if page * per_page >= total or not items:
                break
            page += 1

        if not affected_tcs:
            return []

        refreshed_ids = []
        for tc in affected_tcs:
            tc_id = tc.get('id')
            tc_algo_type = algorithm_type or tc.get('algorithm_type')
            if tc_algo_type:
                case_params_list = self._algorithm_acl.list_case_params(tc_algo_type)

                tc_test_type = tc.get('type') or tc.get('test_type') or 'api'
                scoped_params = [
                    p for p in case_params_list
                    if p.get('scope') == 'common' or p.get('scope') == tc_test_type
                ]

                if scoped_params:
                    config = tc.get('config') or {}
                    rounds = config.get('rounds', [])
                    algo_params_col = tc.get('algorithm_params') or []

                    # 预查音频文件名→ID、设备名→ID 映射，用于 interferers 的 ID 解析
                    _audio_name_to_id_map, _dev_name_to_id = self._build_name_to_id_maps()

                    for round_item in rounds:
                        if not isinstance(round_item, dict):
                            continue
                        round_number = round_item.get('round_number', 1)
                        round_audios = round_item.get('audios', [])
                        if not isinstance(round_audios, list):
                            continue

                        round_audio_ids = [
                            a.get('audio_id') for a in round_audios
                            if isinstance(a, dict) and a.get('audio_id')
                        ]
                        if not round_audio_ids:
                            continue

                        raw_anns = []
                        for aid in round_audio_ids:
                            anns = self.repo.get_annotations_by_audio(aid)
                            for ann in anns:
                                raw_anns.append({
                                    'code': ann.code,
                                    'data': ann.data,
                                })

                        if not raw_anns:
                            continue

                        extracted_params = []
                        for param in scoped_params:
                            param_code = param.get('param_code')
                            field_path = param.get('field_path') or param_code
                            ann_code = param.get('annotation_code') or tc_algo_type
                            matched_anns = [a for a in raw_anns if a.get('code') == ann_code]
                            if not matched_anns:
                                matched_anns = raw_anns
                            value = None
                            for ann in matched_anns:
                                a_data = ann.get('data')
                                if a_data is None:
                                    continue
                                if isinstance(a_data, str):
                                    value = a_data
                                    break
                                if isinstance(a_data, dict):
                                    effective_fp = field_path
                                    if 'segments[]' not in effective_fp:
                                        effective_fp = f'segments[].{effective_fp}'
                                    if 'segments[]' in effective_fp:
                                        parts = effective_fp.split('[].')
                                        arr_key = parts[0]
                                        field_key = parts[1] if len(parts) > 1 else None

                                        def _get_seg_field(seg, key):
                                            if seg.get(key) is not None:
                                                return seg.get(key)
                                            import re
                                            snake = re.sub(r'([A-Z])', r'_\1', key).lower()
                                            return seg.get(snake)

                                        arr = a_data.get(arr_key, [])
                                        if isinstance(arr, list) and field_key:
                                            collected = [
                                                _get_seg_field(seg, field_key) for seg in arr
                                                if isinstance(seg, dict) and _get_seg_field(seg, field_key) is not None
                                            ]
                                            # 过滤掉空数组/空字符串（如 interferers: [] 不应算作有效值）
                                            collected = [c for c in collected if not (isinstance(c, (list, str, dict)) and len(c) == 0)]
                                            if collected:
                                                value = collected[0] if len(collected) == 1 else collected
                                                break
                            if value is not None:
                                # 如果是 interferers 字段，对提取出的每个干扰人做 ID 解析
                                # （audio 文件名→audio_id, playback_device_name→playback_device_id）
                                if param_code == 'interferers' and isinstance(value, list):
                                    for _itf in value:
                                        if not isinstance(_itf, dict):
                                            continue
                                        if not _itf.get('audio_id'):
                                            _fn = _itf.get('audio') or _itf.get('audio_name')
                                            if _fn and _fn in _audio_name_to_id_map:
                                                _itf['audio_id'] = _audio_name_to_id_map[_fn]
                                        if not _itf.get('playback_device_id'):
                                            _dn = _itf.get('playback_device_name')
                                            if _dn and _dn in _dev_name_to_id:
                                                _itf['playback_device_id'] = _dev_name_to_id[_dn]
                                extracted_params.append({
                                    'field_code': param_code,
                                    'field_value': value
                                })

                        round_ap_entry = None
                        for entry in algo_params_col:
                            if entry.get('round_number') == round_number:
                                round_ap_entry = entry
                                break
                        if not round_ap_entry:
                            round_ap_entry = {'round_number': round_number, 'params': []}
                            algo_params_col.append(round_ap_entry)
                        existing_codes = set(
                            p.get('field_code') for p in round_ap_entry.get('params', [])
                        )
                        for p in extracted_params:
                            if p['field_code'] not in existing_codes:
                                round_ap_entry.setdefault('params', []).append(p)
                                existing_codes.add(p['field_code'])

                    # 通过 ACL 仓储 UpdateTestCaseConfig 更新 algorithm_params
                    # （task_service 侧会自动触发 ReferenceParamsGenerator.apply_to_config）
                    update_data = {'algorithm_params': algo_params_col}
                    self._testcase_acl.update_testcase_config(str(tc_id), update_data)

            refreshed_ids.append(tc_id)

        return refreshed_ids


# 模块级实例
audio_testcase_creation_service = AudioTestCaseCreationService()
