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
from shared.clients.grpc_clients import (
    algo_generate_reference_params,
    algo_get_all_reference_params,
    algo_get_reference_params_for_report,
)
from audio_service.domain.repositories.audio_repository_abc import AudioRepositoryInterface
from audio_service.infrastructure.persistence.audio_repository import audio_repository
from audio_service.application.services.audio_annotation_service import audio_annotation_service

logger = logging.getLogger(__name__)


class AudioTestCaseCreationService:
    """音频测试用例创建应用服务（跨域协调）"""

    def __init__(self, repo: AudioRepositoryInterface = None):
        self.repo = repo or audio_repository
        self._annotation_service = audio_annotation_service

    def create_test_case_from_audio(self, audio_id, test_types, audio_tags,
                                    playback_device_id=None, spl=65.0, noise_spl=60.0,
                                    noise_audio_id=None, group_name=None,
                                    dimensions_data=None, algorithm_type=None,
                                    algorithm_params=None, rounds_config=None,
                                    inherit_tags=True, raw_annotations=None,
                                    noise_device_ids=None):
        """从音频创建测试用例

        通过 gRPC TestCaseConfigService 创建测试用例（含分组/标签/参考参数），
        避免直接 import task_service PO。
        """
        from shared.clients.grpc_clients import get_testcase_config_service_stub, get_playback_config_service_stub
        from shared.proto import task_service_pb2 as task_pb, device_service_pb2 as _e2e_pb
        from shared.utils.grpc_json import loads as _loads, dumps as _dumps

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
            # 通过 gRPC 查找第一个 device_type='dry' 的播放设备
            try:
                stub = get_playback_config_service_stub()
                resp = stub.ListPlaybackDevices(_e2e_pb.ListPlaybackDevicesRequest())
                if resp.success:
                    data = _loads(resp.data, {}) or {}
                    devices = data.get('devices', []) or data.get('items', []) or []
                    for dev in devices:
                        if dev.get('device_type') == 'dry' and not dev.get('is_deleted'):
                            effective_playback_device_id = dev.get('id')
                            break
            except Exception:
                pass

            if not effective_playback_device_id:
                raise ValueError(
                    "e2e 测试类型需要一个 device_type='dry' 的播放设备，"
                    "但未找到可用设备。请先在设备管理中配置播放设备。"
                )

        base_name = f"测试用例_{audio.name}"
        if not test_types:
            test_types = ['api']

        created_tc_ids = []

        for tt in test_types:
            if len(test_types) > 1:
                test_case_name = f"{base_name}_{tt}"
            else:
                test_case_name = base_name

            # 名称冲突检查：通过 gRPC ListTestCases 搜索同名用例
            try:
                stub = get_testcase_config_service_stub()
                list_req = task_pb.ListTestCasesRequest(
                    page=1, per_page=50, keyword=test_case_name,
                )
                list_resp = stub.ListTestCases(list_req)
                if list_resp.success:
                    list_data = _loads(list_resp.data, {})
                    for item in list_data.get('items', []):
                        if item.get('name') == test_case_name:
                            test_case_name = f"{test_case_name}_{now_cst().strftime('%H%M%S')}"
                            break
            except Exception:
                pass

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

            config = self._build_config_and_apply_dimensions(
                audio, rounds_resolved, dimensions_data, tt, noise_spl, noise_audio_id,
                noise_device_ids
            )

            # 通过 gRPC CreateTestCaseConfig 创建测试用例
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

            try:
                stub = get_testcase_config_service_stub()
                req = task_pb.CreateTestCaseConfigRequest(data=_dumps(create_data))
                resp = stub.CreateTestCaseConfig(req)
                if resp.success:
                    resp_data = _loads(resp.data, {})
                    tc_id = resp_data.get('id')
                    if tc_id:
                        created_tc_ids.append(tc_id)
                else:
                    logger.error(f"创建测试用例失败: {resp.message}")
            except Exception as e:
                logger.error(f"CreateTestCaseConfig gRPC 调用失败: {e}")

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

        audio_name_for_match = audio.name
        audio_name_to_id = {}
        for round_item in rounds_resolved:
            if not isinstance(round_item, dict):
                continue
            for audio_item in round_item.get('audios', []):
                if not isinstance(audio_item, dict):
                    continue
                item_name = audio_item.get('audio_name') or ''
                if item_name and not audio_item.get('audio_id') and item_name not in audio_name_to_id:
                    found = self.repo.find_audio_by_name(item_name)
                    if found:
                        audio_name_to_id[item_name] = found.id
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
                if item_name == audio_name_for_match or not item_name:
                    audio_item['audio_id'] = audio_id
                elif item_name in audio_name_to_id:
                    audio_item['audio_id'] = audio_name_to_id[item_name]

        return rounds_resolved, algo_params_col

    def _inject_spl_and_device_from_annotations(self, rounds_resolved, raw_annotations,
                                                  tt, effective_playback_device_id, spl):
        """从标注 JSON 提取 spl 和 playback_device_name

        通过 gRPC ListPlaybackDevices 获取设备 name→id 映射，避免直接 import PO。
        """
        if not raw_annotations:
            return
        from shared.clients.grpc_clients import get_playback_config_service_stub
        from shared.proto import device_service_pb2 as _e2e_pb
        from shared.utils.grpc_json import loads as _loads

        dev_name_to_id = {}
        try:
            stub = get_playback_config_service_stub()
            resp = stub.ListPlaybackDevices(_e2e_pb.ListPlaybackDevicesRequest())
            if resp.success:
                data = _loads(resp.data, {}) or {}
                devices = data.get('devices', []) or data.get('items', []) or []
                for dev in devices:
                    if not dev.get('is_deleted'):
                        dev_name_to_id.setdefault(dev.get('name'), dev.get('id'))
        except Exception:
            pass

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

        通过 gRPC 调用 algorithm_service.ListCaseParams 获取参数，避免直接 import PO。
        """
        if not (algorithm_type and raw_annotations):
            return
        from shared.clients.grpc_clients import get_algorithm_definition_service_stub
        from shared.proto import algorithm_service_pb2 as _algo_pb
        from shared.utils.grpc_json import loads as _grpc_loads

        try:
            stub = get_algorithm_definition_service_stub()
            resp = stub.ListCaseParams(_algo_pb.ListCaseParamsRequest(algorithm_type=algorithm_type))
            case_params_list = []
            if resp.success:
                data = _grpc_loads(resp.data, {}) or {}
                case_params_list = data.get('parameters', []) or []
        except Exception:
            case_params_list = []

        scoped_params = [p for p in case_params_list if p.get('scope') == 'common' or p.get('scope') == tt]
        if not scoped_params:
            return

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
                                if collected:
                                    value = collected[0] if len(collected) == 1 else collected
                                    break
                if value is not None:
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

    def _build_config_and_apply_dimensions(self, audio, rounds_resolved, dimensions_data, tt,
                                            noise_spl, noise_audio_id, noise_device_ids=None):
        """构建 config 字典，应用噪声配置和评估维度"""
        config = {
            'source_audio': audio.name,
            'auto_generated': True,
            'rounds': rounds_resolved,
        }
        if (noise_spl and noise_spl > 0) or noise_audio_id:
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

        通过 gRPC ListTestCases 分页获取所有用例，在本地过滤出引用了
        目标 audio_id 的用例；再通过 gRPC UpdateTestCaseConfig 更新
        algorithm_params，由 task_service 侧触发参考参数刷新。
        """
        from shared.clients.grpc_clients import get_testcase_config_service_stub, get_algorithm_definition_service_stub
        from shared.proto import task_service_pb2 as task_pb, algorithm_service_pb2 as _algo_pb
        from shared.utils.grpc_json import loads as _loads, dumps as _dumps

        target_ids = set(audio_ids)

        # 分页获取所有测试用例，本地过滤出引用目标 audio_id 的用例
        affected_tcs = []
        page = 1
        per_page = 100
        while True:
            try:
                stub = get_testcase_config_service_stub()
                req = task_pb.ListTestCasesRequest(
                    page=page, per_page=per_page, include_deleted=False,
                )
                resp = stub.ListTestCases(req)
            except Exception as e:
                logger.error(f"ListTestCases gRPC 调用失败 (page={page}): {e}")
                break

            if not resp.success:
                logger.error(f"ListTestCases gRPC 返回失败: {resp.message}")
                break

            data = _loads(resp.data, {})
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

            if page * per_page >= total:
                break
            page += 1

        if not affected_tcs:
            return []

        refreshed_ids = []
        for tc in affected_tcs:
            tc_id = tc.get('id')
            tc_algo_type = algorithm_type or tc.get('algorithm_type')
            if tc_algo_type:
                try:
                    algo_stub = get_algorithm_definition_service_stub()
                    algo_resp = algo_stub.ListCaseParams(_algo_pb.ListCaseParamsRequest(algorithm_type=tc_algo_type))
                    case_params_list = []
                    if algo_resp.success:
                        algo_data = _loads(algo_resp.data, {}) or {}
                        case_params_list = algo_data.get('parameters', []) or []
                except Exception:
                    case_params_list = []

                tc_test_type = tc.get('type') or tc.get('test_type') or 'api'
                scoped_params = [
                    p for p in case_params_list
                    if p.get('scope') == 'common' or p.get('scope') == tc_test_type
                ]

                if scoped_params:
                    config = tc.get('config') or {}
                    rounds = config.get('rounds', [])
                    algo_params_col = tc.get('algorithm_params') or []

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
                                            if collected:
                                                value = collected[0] if len(collected) == 1 else collected
                                                break
                            if value is not None:
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

                    # 通过 gRPC UpdateTestCaseConfig 更新 algorithm_params
                    # （task_service 侧会自动触发 ReferenceParamsGenerator.apply_to_config）
                    update_data = {'algorithm_params': algo_params_col}
                    try:
                        stub = get_testcase_config_service_stub()
                        req = task_pb.UpdateTestCaseConfigRequest(
                            tc_id=str(tc_id),
                            data=_dumps(update_data),
                        )
                        resp = stub.UpdateTestCaseConfig(req)
                        if not resp.success:
                            logger.warning(f"更新用例 {tc_id} algorithm_params 失败: {resp.message}")
                    except Exception as e:
                        logger.warning(f"UpdateTestCaseConfig gRPC 调用失败 ({tc_id}): {e}")

            refreshed_ids.append(tc_id)

        return refreshed_ids


# 模块级实例
audio_testcase_creation_service = AudioTestCaseCreationService()
