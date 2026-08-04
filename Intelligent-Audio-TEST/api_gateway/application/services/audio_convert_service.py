import os
import uuid
import logging
from pydantic import ValidationError
from api_gateway.infrastructure.request_adapter import request
from shared.models.models import Audio, Tag, AudioAnnotation, AudioTag, TestCase, TestCaseGroup, PlaybackDevice
from shared.models.database import db
from shared.utils.response import success_response, error_response
from shared.utils.log_handler import log_not_emit
from shared.utils.query_utils import now_cst
from api_gateway.schemas.audio import ConvertFormatRequest
from api_gateway.application.services.audio_common import (
    retry_file_operation, get_relative_path,
)

logger = logging.getLogger(__name__)


class AudioConvertService:
    @staticmethod
    def _get_source_language_from_algorithm_params(algorithm_params):
        if not algorithm_params:
            return None
        for param in algorithm_params:
            if isinstance(param, dict):
                if param.get('field_code') == 'source_language':
                    return param.get('field_value')
            elif hasattr(param, 'field_code') and param.field_code == 'source_language':
                return param.field_value
        return None

    # 内部辅助方法：从文件列表构建 rounds 配置
    @staticmethod
    def _build_rounds_from_files(files, mode="multi_round", spl=65.0, playback_device_id=None):
        """从文件列表构建 rounds 配置。

        :param files: 文件列表，每项含 file_id / audio_id / filename
        :param mode: "multi_round"（每音频一轮）或 "single_round_multi_audio"（多音频同轮）
        :param spl: 干声压级
        :param playback_device_id: 播放设备 ID（E2E）
        :return: rounds 列表
        """
        if not files:
            return []

        def _make_audio_config(item, play_order):
            cfg = {
                "audio_id": item["audio_id"],
                "spl": spl,
                "play_order": play_order,
            }
            if playback_device_id:
                cfg["playback_device_id"] = playback_device_id
            return cfg

        if mode == "single_round_multi_audio":
            # 所有音频合并为一轮
            audios = [_make_audio_config(item, idx) for idx, item in enumerate(files)]
            return [{"round_number": 1, "audios": audios}]
        else:
            # multi_round: 每音频一轮
            rounds = []
            for idx, item in enumerate(files):
                rounds.append({
                    "round_number": idx + 1,
                    "audios": [_make_audio_config(item, 0)],
                })
            return rounds

    # 内部辅助方法：持久化音频标注，返回 raw_annotations_data（未剔除用例参数）供用例参数提取使用
    @staticmethod
    def _persist_annotations_and_raw(audio_id, annotations_from_request, algorithm_type):
        """把请求里的 annotations 写入 audio_annotations 表（同 code 覆盖旧记录），返回 raw_annotations_data。

        - 入库的 data 已剔除用例参数字段（只保留参考参数 + 元数据）
        - raw_annotations_data 保留完整原始标注，供 _create_test_case_from_audio 提取用例参数
        """
        from shared.models.models import AudioAnnotation
        # 查用例参数字段列表，用于从标注数据中剔除（标注表只保留参考参数 + 元数据）
        case_param_fields = set()
        if algorithm_type:
            from shared.models.algorithm_models import CaseAlgorithmParam
            # 查参考参数的 field_path 集合，这些字段不能从标注数据中剔除
            from shared.models.algorithm_models import AlgorithmReferenceParam
            ref_field_paths = set()
            ref_params = AlgorithmReferenceParam.query.filter_by(
                algorithm_type=algorithm_type, deleted=False
            ).all()
            for rp in ref_params:
                fp = rp.field_path or rp.code
                if fp:
                    if '[]' in fp:
                        seg_key = fp.split('[].')[1] if '[].' in fp else fp
                        ref_field_paths.add(seg_key)
                    else:
                        ref_field_paths.add(fp)

            case_params = CaseAlgorithmParam.query.filter_by(
                algorithm_type=algorithm_type, deleted=False
            ).all()
            for p in case_params:
                fp = p.field_path or p.param_code
                if fp and '[]' in fp:
                    seg_key = fp.split('[].')[1] if '[].' in fp else fp
                    # 跳过同时作为参考参数的字段，避免把参考参数也从标注中删除
                    if seg_key not in ref_field_paths:
                        case_param_fields.add(seg_key)
                else:
                    if fp not in ref_field_paths:
                        case_param_fields.add(fp)

        raw_annotations_data = []
        for ann in annotations_from_request or []:
            ann_format = ann.get('format', 'json')
            ann_data = ann.get('data', {}) or {}
            ann_code = ann.get('code', '')
            ann_source_lang = ann.get('source_language', '')
            ann_target_lang = ann.get('target_language', '')

            # 保留原始标注数据（未剔除用例参数），用于创建用例时提取用例参数
            raw_annotations_data.append({
                'code': ann_code,
                'data': ann_data,
            })

            # 从标注数据中剔除用例参数字段（只保留参考参数 + 元数据）
            if case_param_fields and isinstance(ann_data, dict):
                import copy as _copy
                ann_data_clean = _copy.deepcopy(ann_data)
                segments = ann_data_clean.get('segments', [])
                if isinstance(segments, list):
                    for seg in segments:
                        if isinstance(seg, dict):
                            for field_key in list(seg.keys()):
                                if field_key in case_param_fields:
                                    del seg[field_key]
                ann_data = ann_data_clean

            # 秒传/重新上传时，同 audio_id + code 的旧标注先软删再写新记录
            existing = AudioAnnotation.query.filter_by(
                audio_id=audio_id, code=ann_code, deleted=False
            ).first()
            if existing:
                existing.deleted = True
                db.session.flush()

            audio_annotation = AudioAnnotation(
                audio_id=audio_id,
                format=ann_format,
                code=ann_code,
                data=ann_data,
                source_language=ann_source_lang,
                target_language=ann_target_lang
            )
            db.session.add(audio_annotation)

        # flush 确保 annotation 写入数据库，后续 _create_test_case_from_audio
        # 调 apply_to_config → _preload_audio_data 时能查到这些 annotation
        if annotations_from_request:
            db.session.flush()

        return raw_annotations_data or None

    # 内部辅助方法：从音频创建测试用例
    @staticmethod
    def _create_test_case_from_audio(audio_id, test_types, audio_tags, playback_device_id=None, spl=65.0, noise_spl=60.0, noise_audio_id=None, group_name=None, dimensions_data=None, algorithm_type=None, algorithm_params=None, rounds_config=None, inherit_tags=True, raw_annotations=None):
        """
        根据音频创建测试用例，支持多测试类型（API和E2E）。

        :param audio_id: 音频ID（主音频，用于命名和描述）
        :param test_types: 测试类型列表，如 ['api', 'e2e']
        :param audio_tags: 音频标签列表
        :param playback_device_id: 播放设备ID（用于E2E测试）
        :param spl: 干声压级
        :param noise_spl: 噪声声压级
        :param noise_audio_id: 噪声音频ID
        :param group_name: 分组名称
        :param dimensions_data: 评估维度配置
        :param algorithm_type: 算法类型
        :param algorithm_params: 算法参数
        :param rounds_config: 完整的 rounds 配置（多轮用例）。传入时优先使用，跳过平面 config 构建。
        :param inherit_tags: 是否继承音频标签到用例（默认 True）
        """
        # 确保 test_types 是列表，并清理可能的空白字符
        if isinstance(test_types, str):
            test_types = [test_types.strip()]
        else:
            test_types = [tt.strip() if isinstance(tt, str) else tt for tt in test_types]

        logger.debug(f'_create_test_case_from_audio called, audio_id={audio_id}, test_types={test_types}, rounds_config={rounds_config}')

        audio = db.session.get(Audio, audio_id)
        if not audio or audio.deleted:
            return None

        # 使用提供的分组名称，如果没有则使用默认值
        effective_group_name = group_name if group_name else '音频上传生成'

        with db.session.no_autoflush:
            # 获取或创建分组
            group = TestCaseGroup.query.filter_by(name=effective_group_name).first()
            if not group:
                group = TestCaseGroup(
                    id=str(uuid.uuid4()),
                    name=effective_group_name,
                    description=f'通过音频上传自动创建的测试用例分组: {effective_group_name}'
                )
                db.session.add(group)
                db.session.flush()

            # 获取默认播放设备（如果需要E2E测试但没有指定设备）
            effective_playback_device_id = playback_device_id
            if 'e2e' in test_types and not effective_playback_device_id:
                default_device = PlaybackDevice.query.filter_by(device_type='dry', is_deleted=0).first()
                if default_device:
                    effective_playback_device_id = default_device.id

            # 创建测试用例名称（基础名）
            base_name = f"测试用例_{audio.name}"

            # 确保至少有一个 test_type
            if not test_types:
                test_types = ['api']

            created_tc_ids = []
            import copy

            for tt in test_types:
                # 每种 test_type 一个用例，名称加后缀区分
                if len(test_types) > 1:
                    test_case_name = f"{base_name}_{tt}"
                else:
                    test_case_name = base_name

                # 同名时加时间戳避免冲突
                existing = TestCase.query.filter_by(name=test_case_name, group_id=group.id, deleted=False).first()
                if existing:
                    test_case_name = f"{test_case_name}_{now_cst().strftime('%H%M%S')}"

                # ===== 构建 config =====
                # 统一走 rounds 架构，前端始终构建 rounds_config
                # 新设计：algorithm_params 和 reference_params 不在 config.rounds[] 中，存独立列
                if rounds_config:
                    rounds_resolved = copy.deepcopy(rounds_config)
                else:
                    # 兜底：前端未传 rounds_config 时构建最小 rounds
                    audio_config = {
                        "audio_id": audio_id,
                        "spl": spl if spl else 65.0,
                        "play_order": 0
                    }
                    if tt == 'e2e':
                        audio_config["playback_device_id"] = effective_playback_device_id
                    rounds_resolved = [{
                        "round_number": 1,
                        "audios": [audio_config],
                    }]

                # 从 rounds_resolved 中剥离 algorithm_params 到独立列
                algo_params_col = []
                import json as _json
                logger.debug(f'rounds_resolved before strip: {_json.dumps(rounds_resolved, ensure_ascii=False)[:500]}')
                log_not_emit('INFO', 'audio_controller', f'[DEBUG_STRIP] rounds_resolved before strip: {_json.dumps(rounds_resolved, ensure_ascii=False)[:500]}', category='audio')
                for round_item in rounds_resolved:
                    if not isinstance(round_item, dict):
                        continue
                    rn = round_item.get('round_number', 1)
                    # 剥离 algorithm_params / algorithmParams
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
                    # 剥离 reference_params_path / referenceParamsPath（不应在 config 中）
                    round_item.pop('reference_params_path', None)
                    round_item.pop('referenceParamsPath', None)

                logger.debug(f'rounds_resolved after strip: {_json.dumps(rounds_resolved, ensure_ascii=False)[:500]}')
                logger.debug(f'algo_params_col: {_json.dumps(algo_params_col, ensure_ascii=False)[:500]}')
                log_not_emit('INFO', 'audio_controller', f'[DEBUG_STRIP] rounds_resolved after strip: {_json.dumps(rounds_resolved, ensure_ascii=False)[:500]}', category='audio')
                log_not_emit('INFO', 'audio_controller', f'[DEBUG_STRIP] algo_params_col: {_json.dumps(algo_params_col, ensure_ascii=False)[:500]}', category='audio')

                # 兜底：前端传了平面 algorithm_params 但没 rounds_config 时
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

                # 把 audio_name 替换为真实的 audio_id
                # 前端构建 rounds 时音频还没上传完，只能用文件名占位；
                # 后端按 audio_name 匹配当前音频，同时查库补全其他已入库音频的 audio_id
                # （多轮上传最后一个音频 mergeChunks 时，其他音频已入库，可从数据库查到）
                audio_name_for_match = audio.name
                # 预查所有 audio_name → audio_id 映射（避免循环里重复查库）
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
                            found = Audio.query.filter_by(name=item_name, deleted=False).first()
                            if found:
                                audio_name_to_id[item_name] = found.id
                for round_item in rounds_resolved:
                    if not isinstance(round_item, dict):
                        continue
                    audios = round_item.get('audios', [])
                    if not isinstance(audios, list):
                        round_item['audios'] = []
                        audios = []
                    # algorithm_params 已剥离到独立列，不再写回 rounds
                    for audio_item in audios:
                        if not isinstance(audio_item, dict):
                            continue
                        # 已有 audio_id 的不覆盖
                        if audio_item.get('audio_id'):
                            continue
                        item_name = audio_item.get('audio_name') or ''
                        # 优先用当前音频匹配
                        if item_name == audio_name_for_match or not item_name:
                            audio_item['audio_id'] = audio_id
                        # 其次用预查映射补全
                        elif item_name in audio_name_to_id:
                            audio_item['audio_id'] = audio_name_to_id[item_name]

                # 从标注 JSON 提取 spl 和 playback_device_name，注入到每个 audio_item
                # 标注 segment 里可写 spl / playback_device_name / playback_device_id
                # playback_device_name 通过查表换成 playback_device_id
                # 四种模式都适用：单轮单音频、单轮多音频、多轮每轮单音频、多轮每轮多音频
                logger.info(f'raw_annotations is {"truthy" if raw_annotations else "falsy"}, len={len(raw_annotations) if raw_annotations else 0}')
                if raw_annotations:
                    # 预查设备名→ID 映射（避免循环里重复查库）
                    from shared.models.models import PlaybackDevice as _PlaybackDevice
                    dev_name_to_id = {}
                    all_devs = _PlaybackDevice.query.filter_by(is_deleted=0).all()
                    for d in all_devs:
                        dev_name_to_id.setdefault(d.name, d.id)

                    # 先从 rounds_config 里前端已传的 playback_device_name 查表换 ID
                    # （多轮场景下，非最后一个文件的标注不在 raw_annotations 里）
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
                                        # 优先用 playback_device_name 查表
                                        dev_name = (
                                            seg.get('playback_device_name')
                                            or seg.get('playbackDeviceName')
                                        )
                                        if dev_name and dev_name in dev_name_to_id:
                                            audio_item['playback_device_id'] = dev_name_to_id[dev_name]
                                            need_dev = False
                                        # 也支持直接写 playback_device_id
                                        elif not dev_name:
                                            v = seg.get('playback_device_id') or seg.get('playbackDeviceId')
                                            if v:
                                                audio_item['playback_device_id'] = v
                                                need_dev = False
                                    if not need_spl and not need_dev:
                                        break
                                if not need_spl and not need_dev:
                                    break
                        # 兜底：e2e 且仍缺 playback_device_id，用默认设备
                        if tt == 'e2e':
                            for audio_item in round_item.get('audios', []):
                                if isinstance(audio_item, dict) and not audio_item.get('playback_device_id'):
                                    audio_item['playback_device_id'] = effective_playback_device_id
                                if isinstance(audio_item, dict) and audio_item.get('spl') is None:
                                    audio_item['spl'] = spl if spl else 65.0

                # 后端按 test_type + scope 从原始标注提取用例参数（不依赖前端提取）
                if algorithm_type and raw_annotations:
                    from shared.models.algorithm_models import CaseAlgorithmParam
                    case_params_list = CaseAlgorithmParam.query.filter_by(
                        algorithm_type=algorithm_type, deleted=False
                    ).all()
                    # 按 scope 过滤：只取匹配当前 test_type 的参数
                    scoped_params = [
                        p for p in case_params_list
                        if p.scope == 'common' or p.scope == tt
                    ]
                    if scoped_params:
                        for round_item in rounds_resolved:
                            if not isinstance(round_item, dict):
                                continue
                            round_audios = round_item.get('audios', [])
                            if not isinstance(round_audios, list):
                                continue
                            # 收集该 round 涉及的 audio_id
                            round_audio_ids = [
                                a.get('audio_id') for a in round_audios
                                if isinstance(a, dict) and a.get('audio_id')
                            ]
                            if not round_audio_ids:
                                continue
                            # 从原始标注提取用例参数
                            extracted_params = []
                            for param in scoped_params:
                                param_code = param.param_code
                                field_path = param.field_path or param_code
                                ann_code = param.annotation_code or algorithm_type
                                # 找匹配的标注
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
                                        # field_path 不含 '[]' 时，自动补 'segments[].' 前缀
                                        effective_fp = field_path
                                        if 'segments[]' not in effective_fp:
                                            effective_fp = f'segments[].{effective_fp}'
                                        if 'segments[]' in effective_fp:
                                            parts = effective_fp.split('[].')
                                            arr_key = parts[0]
                                            field_key = parts[1] if len(parts) > 1 else None
                                            # NamingRequest 已把驼峰转成下划线，尝试两种 key
                                            def _get_seg_field(seg, key):
                                                if seg.get(key) is not None:
                                                    return seg.get(key)
                                                # 尝试驼峰转下划线
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
                                                    break
                                if value is not None:
                                    extracted_params.append({
                                        'field_code': param_code,
                                        'field_value': value
                                    })
                            # 合并到 algo_params_col 中对应轮（前端传来的优先，后端提取的补缺）
                            round_number = round_item.get('round_number', 1)
                            # 找到 algo_params_col 中对应轮的记录
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

                config = {
                    "source_audio": audio.name,
                    "auto_generated": True,
                    "rounds": rounds_resolved,
                }
                logger.debug(f'config rounds: {_json.dumps(config["rounds"], ensure_ascii=False)[:500]}')
                log_not_emit('INFO', 'audio_controller', f'[DEBUG_CONFIG] config rounds: {_json.dumps(config["rounds"], ensure_ascii=False)[:500]}', category='audio')
                # 噪声配置
                if (noise_spl and noise_spl > 0) or noise_audio_id:
                    config["background_noise"] = {
                        "audio_id": noise_audio_id,
                        "spl": noise_spl if noise_spl else 60.0
                    }
                # 评估维度：按当前 test_type 过滤
                # 前端给每条 dimension 加了 test_type 标记（'api'/'e2e'），
                # 没有 test_type 的视为通用维度，所有 test_type 都收
                # round_scope='single' 的维度写入 rounds[].evaluation.dimensions（每轮独立评估）
                # round_scope='multi' 的维度写入 config.dimensions（多轮聚合评估）
                if dimensions_data:
                    raw_dims = []
                    if isinstance(dimensions_data, dict):
                        raw_dims = dimensions_data.get('dimensions', [])
                    elif isinstance(dimensions_data, list):
                        raw_dims = dimensions_data
                    # 统一转换为 dict，确保 pydantic model 也能正确取 test_type
                    norm_dims = []
                    for d in raw_dims:
                        if isinstance(d, dict):
                            norm_dims.append(d)
                        elif hasattr(d, 'model_dump'):
                            norm_dims.append(d.model_dump(by_alias=False, exclude_none=True))
                        else:
                            norm_dims.append({'id': d})
                    filtered_dims = [
                        d for d in norm_dims
                        if not d.get('test_type') or d.get('test_type') == tt
                    ]
                    # 按 (id, round_scope) 组合去重
                    # 同一维度可以同时有 single 和 multi 两个 scope，分别写入不同位置
                    seen_keys = set()
                    unique_dims = []
                    for d in filtered_dims:
                        dim_id = d.get('id')
                        scope = d.get('round_scope', 'single')
                        key = (dim_id, scope)
                        if dim_id and key not in seen_keys:
                            seen_keys.add(key)
                            unique_dims.append(d)
                    # 按 round_scope 分发维度
                    single_round_dims = [d for d in unique_dims if d.get('round_scope', 'single') == 'single']
                    multi_round_dims = [d for d in unique_dims if d.get('round_scope') == 'multi']
                    # 单轮维度写入 rounds[].evaluation.dimensions
                    for round_item in rounds_resolved:
                        if isinstance(round_item, dict):
                            if 'evaluation' not in round_item:
                                round_item['evaluation'] = {}
                            round_item['evaluation']['dimensions'] = single_round_dims
                    # 多轮维度写入 config.dimensions（顶层聚合维度）
                    if multi_round_dims:
                        config['dimensions'] = multi_round_dims
                else:
                    # 确保 rounds 有 evaluation 结构
                    for round_item in rounds_resolved:
                        if isinstance(round_item, dict):
                            if 'evaluation' not in round_item:
                                round_item['evaluation'] = {}
                            if 'dimensions' not in round_item['evaluation']:
                                round_item['evaluation']['dimensions'] = []

                # 创建测试用例
                tc_id = str(uuid.uuid4())

                new_tc = TestCase(
                    id=tc_id,
                    name=test_case_name,
                    description=f"自动从音频 '{audio.name}' 创建的测试用例",
                    group_id=group.id,
                    test_type=tt,
                    algorithm_type=algorithm_type,
                    config=config,
                    algorithm_params=algo_params_col if algo_params_col else None
                )
                db.session.add(new_tc)
                log_not_emit('DEBUG', 'audio_controller', f'tc.algorithm_params={_json.dumps(algo_params_col, ensure_ascii=False)[:300]}', category='audio')
                log_not_emit('DEBUG', 'audio_controller', f'config.rounds[0] keys={list(config["rounds"][0].keys()) if config.get("rounds") else "no rounds"}', category='audio')
                # 继承音频的标签（受 inherit_tags 开关控制）
                if inherit_tags:
                    for tag_name in audio_tags:
                        tag = Tag.query.filter_by(name=tag_name).first()
                        if tag:
                            new_tc.tags.append(tag)

                # 同步生成参考参数（rounds 模式和平面模式都会真正生成文件）
                from shared.algorithm.reference_params_generator import ReferenceParamsGenerator
                ReferenceParamsGenerator.apply_to_config(new_tc)
                log_not_emit('DEBUG', 'audio_controller', f'new_tc.algorithm_params={_json.dumps(new_tc.algorithm_params, ensure_ascii=False)[:300] if new_tc.algorithm_params else "None"}', category='audio')
                log_not_emit('DEBUG', 'audio_controller', f'new_tc.reference_params={_json.dumps(new_tc.reference_params, ensure_ascii=False)[:300] if new_tc.reference_params else "None"}', category='audio')
                log_not_emit('DEBUG', 'audio_controller', f'config.rounds[0] keys={list(config["rounds"][0].keys()) if config.get("rounds") else "no rounds"}', category='audio')

                created_tc_ids.append(tc_id)

            # 不在这里 commit，交给调用者统一提交
            db.session.flush()
            # 返回完整列表，调用方可获取真实创建用例数
            return created_tc_ids

    # 音频格式转换
    @staticmethod
    def convert(audio_id):
        from pydub import AudioSegment
        audio = db.session.get(Audio, audio_id)
        if not audio or audio.deleted:
            return error_response("未找到音频文件", 404)

        data = request.get_json()
        if not data:
            return error_response("请求体不能为空")

        try:
            validated = ConvertFormatRequest.model_validate(data)
        except ValidationError as e:
            return error_response(f"参数验证失败: {e}")

        target_format = validated.format.lower()

        try:
            # 1. 准备路径
            old_path = audio.file_path
            upload_dir = os.path.dirname(old_path)
            new_filename = f"conv_{uuid.uuid4().hex}.{target_format}"
            new_path = os.path.join(upload_dir, new_filename)

            # 2. 执行转换 (使用 pydub)
            audio_seg = AudioSegment.from_file(old_path)
            audio_seg.export(new_path, format=target_format)

            # 3. 更新数据库记录 (统一用正斜杠存储 file_path)
            audio.file_path = new_path.replace('\\', '/')
            audio.format = target_format
            audio.size = os.path.getsize(new_path)
            audio.updated_at = now_cst()

            db.session.commit()
            return success_response({
                "id": audio.id,
                "format": target_format,
                "file_path": get_relative_path(new_path)
            }, f"音频已成功转换为 {target_format}")

        except Exception as e:
            return error_response(f"转换失败: {str(e)}")
