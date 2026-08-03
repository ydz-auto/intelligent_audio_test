# -*- coding: utf-8 -*-
"""
参考参数生成器

职责：
- 根据算法类型和用例配置，从数据库读取参考参数配置
- 自动生成对应测试用例的参考参数（ASR文本、翻译文本、RTTM/STM标注等）
- 支持重叠播放场景的时间戳调整
- 提供参考参数值的获取接口
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Any
from shared.utils.storage import storage
from shared.models.database import db
from shared.models.models import Audio, AudioAnnotation
from shared.utils.log_handler import log_not_emit

# reference_params 文件存储到 OSS（ref_params bucket）
_REF_PARAMS_BUCKET = 'ref_params'


def _build_ref_params_key(case_id, round_number, filename=None):
    """构建参考参数 OSS key：{case_id}/{filename} 或 {case_id}/round_{round_number}.json"""
    if filename is None:
        filename = f"round_{round_number}.json"
    return f"{case_id}/{filename}"

# annotation data 中的已知顶层字段，其余字段视为额外字段并透传到参考参数
_KNOWN_DATA_KEYS = {'segments', 'text', 'annotations', 'timestamps', 'timestamps_global'}


def normalize_reference_params(params, test_type: str = 'api') -> List[Dict[str, Any]]:
    if not params:
        return []
    if isinstance(params, list):
        return [_normalize_single_ref_param(item, test_type) for item in params if isinstance(item, dict)]
    if isinstance(params, dict):
        if 'params' in params:
            return normalize_reference_params(params['params'], test_type)
        for key in ('default', 'api', 'e2e'):
            if key in params and isinstance(params[key], list):
                return normalize_reference_params(params[key], test_type)
        result = []
        for code, val in params.items():
            if isinstance(val, dict):
                item = dict(val)
                if 'code' not in item:
                    item['code'] = code
                result.append(_normalize_single_ref_param(item, test_type))
        return result
    return []


def _normalize_single_ref_param(param: Dict, test_type: str = 'api') -> Dict:
    if 'value' in param and param['value'] is not None:
        if 'api' in param or 'e2e' in param or 'test_type' in param:
            param = dict(param)
            param.pop('api', None)
            param.pop('e2e', None)
            param.pop('test_type', None)
        return param
    tt_value = param.get(test_type)
    if tt_value is not None and tt_value != '':
        param = dict(param)
        param['value'] = tt_value
        param.pop('api', None)
        param.pop('e2e', None)
        param.pop('test_type', None)
        return param
    for fallback in ('api', 'e2e'):
        fb_value = param.get(fallback)
        if fb_value is not None and fb_value != '':
            param = dict(param)
            param['value'] = fb_value
            param.pop('api', None)
            param.pop('e2e', None)
            param.pop('test_type', None)
            return param
    return param


class ReferenceParamsGenerator:
    """
    参考参数生成器
    
    根据算法类型和用例配置，自动生成参考参数
    双记录架构：每条记录独立生成，使用 value 字段存储
    
    采用子类策略模式，每个算法类型对应一个或多个生成器子类
    
    结构:
    [
        { "code": "asr_reference_text", "type": "text", "value": "..." },
        { "code": "translation_reference_text", "type": "text", "value": [...] },
        { "code": "asr_reference_rttm", "type": "rttm", "value": {...} }
    ]
    """

    @classmethod
    def generate(cls, test_case) -> list:
        """
        根据测试用例的算法类型和配置，自动生成参考参数列表
        
        逐轮生成：每个 round 用自己的 audios 和 algorithmParams 独立生成。
        返回所有 round 的参数合并列表（用于向后兼容的单一返回值）。
        
        Args:
            test_case: TestCase 模型对象，包含 algorithm_type 和 config
            
        Returns:
            参考参数列表，每个元素包含 code, type, value 等字段
        """
        if not test_case:
            log_not_emit('WARNING', 'reference_params_generator', 'generate called with None test_case', category='algorithm')
            return []
        
        config = test_case.config or {}
        rounds = config.get('rounds', [])
        
        if not rounds:
            return []
        
        # 逐轮生成，合并结果
        all_params = []
        for round_item in rounds:
            if isinstance(round_item, dict):
                round_params = cls.generate_for_round(test_case, round_item)
                all_params.extend(round_params)
        return all_params

    @classmethod
    def generate_for_round(cls, test_case, round_data: dict) -> list:
        """
        为单个 round 生成参考参数列表
        
        使用该 round 自己的 audios 列表和 algorithmParams 独立生成。
        
        Args:
            test_case: TestCase 模型对象
            round_data: 单个 round 的配置字典
            
        Returns:
            参考参数列表，每个元素包含 code, type, value 等字段
        """
        if not test_case or not round_data:
            return []
        
        algorithm_type = test_case.algorithm_type
        
        # 构建该 round 的 config 上下文
        config = test_case.config or {}
        config = config.copy()
        
        # 注入该 round 的 algorithm_params
        ap = round_data.get('algorithm_params')
        if ap:
            config['algorithm_params'] = ap
        
        # 注入该 round 的 audios（提取函数统一读 config.get('audios', [])）
        config['audios'] = round_data.get('audios', [])
        
        # 注入 test_type
        config['_record_test_type'] = getattr(test_case, 'test_type', 'api') or 'api'
        
        # 使用该 round 自己的音频列表
        round_audios = config['audios']
        audio_ids = [item.get('audio_id') for item in round_audios if item.get('audio_id')]
        
        round_number = round_data.get('round_number', '?')
        log_not_emit('DEBUG', 'reference_params_generator',
                     f'Generating reference params for round {round_number}, algorithm_type: {algorithm_type}, audio_ids: {audio_ids}',
                     category='algorithm')
        
        preload_context = cls._preload_audio_data(audio_ids)
        config['_preload_context'] = preload_context
        
        from shared.models.algorithm_models import AlgorithmReferenceParam
        
        ref_params = AlgorithmReferenceParam.query.filter_by(
            algorithm_type=algorithm_type,
            deleted=False
        ).all()
        
        if not ref_params:
            log_not_emit('WARNING', 'reference_params_generator',
                         f'No reference params found for algorithm: {algorithm_type}',
                         category='algorithm')
            return []
        
        result = []
        for ref_param in ref_params:
            try:
                param = cls._generate_single_param(config, ref_param)
                if param:
                    result.append(param)
            except Exception as e:
                log_not_emit('ERROR', 'reference_params_generator',
                             f'Error generating param {ref_param.code} for round {round_number}: {e}',
                             category='algorithm')
                continue
        
        log_not_emit('DEBUG', 'reference_params_generator',
                     f'Generated {len(result)} reference params for round {round_number}',
                     category='algorithm')
        return result
    
    @classmethod
    def _preload_audio_data(cls, audio_ids: List[int]) -> Dict[str, Any]:
        """
        批量预加载音频数据（性能优化核心方法）
        
        一次性查询所有音频的元数据和标注，避免 N+1 查询问题
        
        Args:
            audio_ids: 音频ID列表
            
        Returns:
            {
                'audio_map': {audio_id: Audio对象},
                'annotation_map': {audio_id: [AudioAnnotation对象列表]},
                'duration_map': {audio_id: 时长}
            }
        """
        if not audio_ids:
            return {'audio_map': {}, 'annotation_map': {}, 'duration_map': {}}
        
        audio_map = {}
        annotation_map = {}
        duration_map = {}
        
        audios = Audio.query.filter(Audio.id.in_(audio_ids)).all()
        audio_map = {a.id: a for a in audios}
        duration_map = {a.id: a.duration or 0.0 for a in audios}
        
        annotations = AudioAnnotation.query.filter(
            AudioAnnotation.audio_id.in_(audio_ids),
            AudioAnnotation.deleted == False
        ).all()
        
        for ann in annotations:
            annotation_map.setdefault(ann.audio_id, []).append(ann)
        
        log_not_emit('DEBUG', 'reference_params_generator', 
            f'Preloaded {len(audio_map)} audios, {len(annotations)} annotations for {len(audio_ids)} audio_ids', 
            category='algorithm')
        
        return {
            'audio_map': audio_map,
            'annotation_map': annotation_map,
            'duration_map': duration_map
        }
    
    @classmethod
    def _generate_single_param(cls, config: Dict, ref_param) -> Dict:
        """
        根据参考参数配置生成单个参数
        
        处理逻辑:
        1. 根据 param_type 判断是结构化数据(json/rttm/stm)还是文本
        2. 调用不同的提取函数获取值
        3. 组装完整的参数字典
        
        Args:
            config: 用例配置，包含 audios 等信息
            ref_param: AlgorithmReferenceParam 数据库模型对象
            
        Returns:
            参数字典，包含 code, type, value
        """
        code = ref_param.code
        param_type = ref_param.param_type
        annotation_code = ref_param.annotation_code
        annotation_format = ref_param.annotation_format
        field_path = getattr(ref_param, 'field_path', None)
        merge_mode = getattr(ref_param, 'merge_mode', None) or 'join'
        record_test_type = config.get('_record_test_type', 'api')
        
        # 兜底：field_path 为空但 code 非空时，按 segments[].<code> 取值
        if not field_path and code and param_type == 'text':
            field_path = f'segments[].{code}'
        
        log_not_emit('DEBUG', 'reference_params_generator', 
            f'_generate_single_param: code={code}, param_type={param_type}, annotation_code={annotation_code}, annotation_format={annotation_format}, field_path={field_path}, merge_mode={merge_mode}, record_test_type={record_test_type}', 
            category='algorithm')
        
        values = {}
        
        if field_path:
            # 按字段路径提取：从标注 data 中提取指定字段
            values = _extract_field_from_audios(
                config, field_path, merge_mode,
                annotation_code=annotation_code,
                annotation_format=annotation_format
            )
        elif annotation_code == 'translation' or (code and 'translation' in code.lower()):
            values = _extract_translation_from_audios(config)
        elif param_type in ['json', 'rttm', 'stm']:
            structured_values = _extract_annotation_with_overlap(
                config, 
                param_type,
                annotation_code=annotation_code,
                annotation_format=annotation_format
            )
            values = structured_values
        else:
            text_values = _extract_text_from_audios(
                config, 
                annotation_code=annotation_code, 
                annotation_format=annotation_format
            )
            values = text_values
        
        value = values.get(record_test_type)
        
        log_not_emit('DEBUG', 'reference_params_generator', 
            f'_generate_single_param: code={code}, value={value}', 
            category='algorithm')
        
        if not value:
            log_not_emit('DEBUG', 'reference_params_generator', 
                f'_generate_single_param: code={code} filtered out - value is empty', 
                category='algorithm')
            return None
        
        param = {
            'code': code,
            'type': param_type,
            'value': value
        }
        
        if annotation_code:
            param['annotation_code'] = annotation_code
        if annotation_format:
            param['annotation_format'] = annotation_format
        
        return param

    @classmethod
    def apply_to_config(cls, test_case) -> None:
        """
        将生成的参考参数应用到用例的 reference_params 独立列中
        
        逐轮生成：每个 round 用自己的 audios 独立生成 reference params，
        写入各自的文件，路径存入 test_case.reference_params 独立列（按轮分组）
        
        Args:
            test_case: TestCase 模型对象
            
        注意: 此方法会修改 test_case.reference_params 独立列，不再修改 test_case.config
        """
        if not test_case:
            log_not_emit('WARNING', 'reference_params_generator', 'apply_to_config called with None test_case', category='algorithm')
            return
        
        # 仅从 config 读取轮次列表（config 只含结构性字段，不再含 reference_params_path）
        config = test_case.config or {}
        rounds = config.get('rounds', [])
        import json as _json
        log_not_emit('INFO', 'reference_params_generator', f'[DEBUG_APPLY] config rounds before apply: {_json.dumps(rounds, ensure_ascii=False)[:500]}', category='algorithm')
        
        if not rounds:
            log_not_emit('WARNING', 'reference_params_generator', 'apply_to_config: no rounds found in config', category='algorithm')
            return
        
        log_not_emit('DEBUG', 'reference_params_generator', f'Applying reference params for test_case: {test_case.algorithm_type}, {len(rounds)} round(s)', category='algorithm')
        
        case_id = getattr(test_case, 'id', '') or str(id(test_case))

        # 收集每轮的 reference_params OSS key，最后赋值到独立列
        ref_params_list = []
        total_params = 0
        for round_item in rounds:
            if not isinstance(round_item, dict):
                continue

            round_number = round_item.get('round_number', 1)

            # 为该 round 独立生成 reference params
            round_params = cls.generate_for_round(test_case, round_item)
            if not round_params:
                log_not_emit('WARNING', 'reference_params_generator',
                             f'round {round_number}: no params generated', category='algorithm')
                continue

            round_params = normalize_reference_params(round_params)

            # 写入该 round 的独立 OSS 对象
            oss_key = _build_ref_params_key(case_id, round_number)

            try:
                data = json.dumps(round_params, ensure_ascii=False, indent=2).encode('utf-8')
                stored_path = storage.save_bytes(data, _REF_PARAMS_BUCKET, oss_key,
                                                 content_type='application/json')
                # 存储 path 收集到独立列结构，不再写入 config 的 round_item
                ref_params_list.append({
                    'round_number': round_number,
                    'reference_params_path': stored_path
                })
                total_params += len(round_params)
                log_not_emit('DEBUG', 'reference_params_generator',
                             f'round {round_number}: uploaded {len(round_params)} params to {stored_path}', category='algorithm')
            except Exception as e:
                log_not_emit('ERROR', 'reference_params_generator',
                             f'round {round_number}: failed to upload {_REF_PARAMS_BUCKET}/{oss_key}: {e}', category='algorithm')
        
        # 路径写入 reference_params 独立列，不再修改 config
        test_case.reference_params = ref_params_list

        log_not_emit('INFO', 'reference_params_generator', f'[DEBUG_APPLY] config rounds after apply: {_json.dumps(rounds, ensure_ascii=False)[:500]}', category='algorithm')
        log_not_emit('INFO', 'reference_params_generator', f'[DEBUG_APPLY] ref_params_list: {_json.dumps(ref_params_list, ensure_ascii=False)[:500]}', category='algorithm')
        log_not_emit('INFO', 'reference_params_generator', f'apply_to_config: {total_params} total params generated across {len(rounds)} round(s)', category='algorithm')

    @classmethod
    def on_audio_associated(cls, test_case, round_number: int) -> None:
        """
        音频关联到轮次时，自动重新生成该轮的参考参数文件
        
        轻量入口：仅重新生成指定轮次的 reference params，不影响其他轮次。
        
        Args:
            test_case: TestCase 模型对象（需含完整 config.rounds）
            round_number: 被关联音频的轮次号
            
        注意: 此方法会修改 test_case.reference_params 独立列中对应轮的记录，不再修改 test_case.config
        """
        if not test_case:
            log_not_emit('WARNING', 'reference_params_generator', 'on_audio_associated called with None test_case', category='algorithm')
            return
        
        # 从 config 读取轮次列表（仅用于获取 audios 等结构性字段）
        config = test_case.config or {}
        rounds = config.get('rounds', [])
        
        target_round = None
        for round_item in rounds:
            if isinstance(round_item, dict) and round_item.get('round_number') == round_number:
                target_round = round_item
                break
        
        if not target_round:
            log_not_emit('WARNING', 'reference_params_generator',
                         f'on_audio_associated: round {round_number} not found in config', category='algorithm')
            return
        
        # 为该轮重新生成 reference params
        round_params = cls.generate_for_round(test_case, target_round)
        if not round_params:
            log_not_emit('WARNING', 'reference_params_generator',
                         f'on_audio_associated: no params generated for round {round_number}', category='algorithm')
            return
        
        round_params = normalize_reference_params(round_params)
        
        # 写入 OSS
        case_id = getattr(test_case, 'id', '') or str(id(test_case))
        oss_key = _build_ref_params_key(case_id, round_number)

        try:
            data = json.dumps(round_params, ensure_ascii=False, indent=2).encode('utf-8')
            stored_path = storage.save_bytes(data, _REF_PARAMS_BUCKET, oss_key,
                                             content_type='application/json')
            # 存储 path 写入 reference_params 独立列中对应轮的记录，不再修改 config 中的 round_item
            ref_params_col = list(test_case.reference_params or [])
            found = False
            for item in ref_params_col:
                if isinstance(item, dict) and item.get('round_number') == round_number:
                    item['reference_params_path'] = stored_path
                    found = True
                    break
            if not found:
                # reference_params 列为 None 或没有该轮记录，追加一条
                ref_params_col.append({
                    'round_number': round_number,
                    'reference_params_path': stored_path
                })
            test_case.reference_params = ref_params_col
            log_not_emit('INFO', 'reference_params_generator',
                         f'on_audio_associated: round {round_number} uploaded {len(round_params)} params to oss://{_REF_PARAMS_BUCKET}/{oss_key}', category='algorithm')
        except Exception as e:
            log_not_emit('ERROR', 'reference_params_generator',
                         f'on_audio_associated: round {round_number} failed to upload oss://{_REF_PARAMS_BUCKET}/{oss_key}: {e}', category='algorithm')

    @classmethod
    def load_from_file(cls, filepath: str) -> list:
        """
        从 OSS 加载参考参数

        Args:
            filepath: 参考参数 OSS 对象 key

        Returns:
            参考参数列表，格式与 generate() 返回值相同
        """
        if not filepath:
            return []
        try:
            raw = storage.load_bytes(filepath)
            data = json.loads(raw.decode('utf-8'))
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            log_not_emit('ERROR', 'reference_params_generator',
                         f'Failed to load reference params from {filepath}: {e}', category='algorithm')
            return []

    @classmethod
    def get_reference_text(cls, reference_params_col, code: str) -> str:
        """
        从参考参数独立列获取参考文本（从 reference_params_path 文件加载）

        Args:
            reference_params_col: test_case.reference_params 的值，格式为 [{round_number, reference_params_path}]
            code: 参考参数代码 (如 'asr_reference_text')

        Returns:
            参考文本值
        """
        reference_params = cls.get_all_reference_params(reference_params_col)
        if not reference_params:
            return ''

        if code:
            for param in reference_params:
                if param.get('code') == code:
                    return param.get('value', '') or ''

        return ''

    @classmethod
    def get_all_reference_params(cls, reference_params_col) -> list:
        """
        获取所有参考参数（从 reference_params 独立列的 reference_params_path 文件加载）

        也支持直接传入 reference_params 列表（报告 adjusted_params 场景）。

        Args:
            reference_params_col: test_case.reference_params 的值，格式为 [{round_number, reference_params_path}]

        Returns:
            参考参数列表
        """
        if not reference_params_col:
            return []

        # 兼容旧调用方：如果传入的是 config dict（有 rounds 键），走旧逻辑从 config.rounds[].reference_params_path 读取
        if isinstance(reference_params_col, dict):
            # 直接传入的 reference_params（报告 adjusted_params 场景）
            direct_ref = reference_params_col.get('reference_params')
            if direct_ref:
                return normalize_reference_params(direct_ref)

            rounds = reference_params_col.get('rounds', [])
            if not rounds:
                return []

            all_refs = []
            for round_item in rounds:
                if not isinstance(round_item, dict):
                    continue
                ref_path = round_item.get('reference_params_path') or round_item.get('referenceParamsPath')
                if ref_path:
                    round_refs = cls.load_from_file(ref_path)
                    if round_refs:
                        rn = round_item.get('round_number') or round_item.get('roundNumber')
                        # 给每个参数注入 round_number，便于后续按轮次展示
                        for p in round_refs:
                            if isinstance(p, dict) and 'round_number' not in p:
                                p['round_number'] = rn
                        all_refs.extend(round_refs)
            return all_refs

        # 新格式：reference_params_col 是 [{round_number, reference_params_path}] 列表
        if isinstance(reference_params_col, list):
            # 兼容直接传入的 reference_params 参数列表（报告 adjusted_params 场景）
            # 如果列表元素是包含 code 字段的参数字典，视为直接传入的参数列表
            if reference_params_col and isinstance(reference_params_col[0], dict) and 'code' in reference_params_col[0]:
                return normalize_reference_params(reference_params_col)

            all_refs = []
            for item in reference_params_col:
                if not isinstance(item, dict):
                    continue
                ref_path = item.get('reference_params_path') or item.get('referenceParamsPath')
                if ref_path:
                    round_refs = cls.load_from_file(ref_path)
                    if round_refs:
                        rn = item.get('round_number') or item.get('roundNumber')
                        for p in round_refs:
                            if isinstance(p, dict) and 'round_number' not in p:
                                p['round_number'] = rn
                        all_refs.extend(round_refs)
            return all_refs

        return []

    @classmethod
    def get_reference_params_for_report(cls, reference_params_col) -> Dict[str, Any]:
        """
        获取用于报告展示的参考参数字典

        返回格式:
        {
            "asr_reference_text": {"code": "asr_reference_text", "type": "text", "value": "..."},
            "translation_reference_text": {"code": "translation_reference_text", "type": "text", "value": "..."},
            "rttm_ref": {"code": "rttm_ref", "type": "rttm", "value": {...}, "segments": [...], "text": "..."},
            "stm_ref": {"code": "stm_ref", "type": "stm", "value": {...}, "segments": [...], "text": "..."},
            ...
        }

        Args:
            reference_params_col: test_case.reference_params 的值，格式为 [{round_number, reference_params_path}]
            兼容旧调用方：也支持传入 config dict（有 rounds 键）

        Returns:
            按 code 分组的参考参数字典
        """
        result = {}
        reference_params = cls.get_all_reference_params(reference_params_col)
        
        if not reference_params:
            return result

        # 先按 code 分组，检测是否有多轮
        by_code = {}
        for param in reference_params:
            if not isinstance(param, dict):
                continue
            code = param.get('code')
            if not code:
                continue
            by_code.setdefault(code, []).append(param)

        for code, params in by_code.items():
            # 如果该 code 有多个轮次的参数，按 round_number 展开为 code@round:N
            has_multi_round = any(p.get('round_number') is not None for p in params) and len(params) > 1
            for param in params:
                rn = param.get('round_number')
                if has_multi_round and rn is not None:
                    key = f'{code}@round:{rn}'
                else:
                    key = code

                param_type = param.get('type', 'text')
                value = param.get('value')

                param_info = {
                    "code": code,
                    "type": param_type,
                    "value": value,
                }
                if rn is not None:
                    param_info["round_number"] = rn
                    param_info["label"] = f'{code} (第{rn}轮)'

                if param_type in ['rttm', 'stm'] and isinstance(value, dict):
                    param_info["segments"] = value.get('segments', [])
                    param_info["text"] = value.get('text', '')
                    param_info["json"] = value.get('json', '')

                if param.get('annotation_code'):
                    param_info["annotation_code"] = param.get('annotation_code')
                if param.get('annotation_format'):
                    param_info["annotation_format"] = param.get('annotation_format')

                result[key] = param_info

        return result


def _get_overlap_rate(config: Dict) -> float:
    """从用例配置获取重叠率"""
    algorithm_params = config.get('algorithm_params', {})
    if isinstance(algorithm_params, list):
        for p in algorithm_params:
            if p.get('field_code') == 'overlap_rate':
                value = p.get('field_value') or 0
                try:
                    return max(0.0, min(1.0, float(value)))
                except (ValueError, TypeError):
                    return 0
        return 0
    overlap_rate = algorithm_params.get('overlap_rate', 0)
    try:
        return max(0.0, min(1.0, float(overlap_rate)))
    except (ValueError, TypeError):
        return 0


def _get_overlap_time(config: Dict) -> float:
    """从用例配置获取重叠时间（秒）"""
    algorithm_params = config.get('algorithm_params', {})
    if isinstance(algorithm_params, list):
        for p in algorithm_params:
            if p.get('field_code') == 'overlap_time':
                value = p.get('field_value') or 0
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return 0
        return 0
    overlap_time = algorithm_params.get('overlap_time', 0)
    try:
        return max(0.0, float(overlap_time))
    except (ValueError, TypeError):
        return 0


def _extract_speakers_from_audio(audio_id: int, annotation_map: Dict = None) -> set:
    """
    从音频的diarization标注中提取所有speaker集合
    
    Args:
        audio_id: 音频ID
        annotation_map: 预加载的标注映射 {audio_id: [annotations]}，用于性能优化
        
    Returns:
        set: speaker标签集合，如 {'spk9', 'spk8'}
    """
    if not audio_id:
        return set()
    
    speakers = set()
    
    if annotation_map and audio_id in annotation_map:
        annotations = annotation_map[audio_id]
    else:
        annotations = AudioAnnotation.query.filter_by(
            audio_id=audio_id,
            deleted=False
        ).all()
    
    for ann in annotations:
        if not ann.data:
            continue
        
        if isinstance(ann.data, dict):
            segments = ann.data.get('segments', [])
            for seg in segments:
                if 'speaker' in seg and seg['speaker']:
                    speakers.add(seg['speaker'])
        elif isinstance(ann.data, list):
            for seg in ann.data:
                if isinstance(seg, dict) and 'speaker' in seg and seg['speaker']:
                    speakers.add(seg['speaker'])
    
    log_not_emit('DEBUG', 'reference_params_generator', 
        f'[_extract_speakers_from_audio] audio_id={audio_id}, speakers={speakers}', 
        category='algorithm')
    
    return speakers


def _calculate_speaker_aware_offsets(audios_config: List[Dict], overlap_rate: float, overlap_time: float = 0, preload_context: Dict = None) -> Dict[int, float]:
    """
    计算每个音频播放项的开始时间偏移（speaker感知版本）

    规则：
    - 相邻音频有共同speaker → 顺序播放（offset = prev_end_time）
    - 相邻音频无共同speaker → 按overlap_time或overlap_rate交叠

    Args:
        audios_config: 音频配置列表
        overlap_rate: 重叠率 (0.0-1.0)
        overlap_time: 重叠时间（秒），优先级高于 overlap_rate
        preload_context: 预加载数据上下文，用于性能优化

    Returns:
        {play_order: offset_seconds}
    """
    offsets = {}
    sorted_audios = sorted(audios_config, key=lambda x: x.get('play_order', 0))
    
    log_not_emit('DEBUG', 'reference_params_generator', 
        f'[_calculate_speaker_aware_offsets] START: overlap_rate={overlap_rate}, overlap_time={overlap_time}, audio_count={len(sorted_audios)}', 
        category='algorithm')
    
    annotation_map = preload_context.get('annotation_map', {}) if preload_context else {}
    duration_map = preload_context.get('duration_map', {}) if preload_context else {}
    
    audio_speakers = {}
    for audio_item in sorted_audios:
        audio_id = audio_item.get('audio_id')
        if audio_id:
            audio_speakers[audio_id] = _extract_speakers_from_audio(audio_id, annotation_map)
    
    log_not_emit('DEBUG', 'reference_params_generator', 
        f'[_calculate_speaker_aware_offsets] audio_speakers={audio_speakers}', 
        category='algorithm')
    
    cumulative_duration = 0.0
    prev_end_time = 0.0
    
    for i, audio_item in enumerate(sorted_audios):
        play_order = audio_item.get('play_order', 0)
        audio_id = audio_item.get('audio_id')
        
        audio_duration = 1.0
        if audio_id:
            if duration_map and audio_id in duration_map:
                audio_duration = duration_map[audio_id] or 1.0
            else:
                audio = db.session.get(Audio, audio_id)
                if audio and audio.duration:
                    audio_duration = audio.duration
        
        log_not_emit('DEBUG', 'reference_params_generator', 
            f'[_calculate_speaker_aware_offsets] i={i}, play_order={play_order}, audio_id={audio_id}, audio_duration={audio_duration}, cumulative_duration={cumulative_duration}, prev_end_time={prev_end_time}', 
            category='algorithm')
        
        if i == 0:
            offsets[play_order] = 0
            log_not_emit('DEBUG', 'reference_params_generator', 
                f'[_calculate_speaker_aware_offsets] i=0, first audio, offset=0', 
                category='algorithm')
        else:
            prev_audio_id = sorted_audios[i-1].get('audio_id')
            curr_speakers = audio_speakers.get(audio_id, set())
            prev_speakers = audio_speakers.get(prev_audio_id, set())
            
            has_common_speaker = len(curr_speakers & prev_speakers) > 0
            
            log_not_emit('DEBUG', 'reference_params_generator', 
                f'[_calculate_speaker_aware_offsets] i={i}, prev_audio_id={prev_audio_id}, prev_speakers={prev_speakers}, curr_speakers={curr_speakers}, has_common_speaker={has_common_speaker}', 
                category='algorithm')
            
            if has_common_speaker:
                offsets[play_order] = prev_end_time
                log_not_emit('DEBUG', 'reference_params_generator', 
                    f'[_calculate_speaker_aware_offsets] Has common speaker, sequential playback: offset=prev_end_time={prev_end_time}', 
                    category='algorithm')
            else:
                if overlap_time and overlap_time > 0:
                    offset_val = prev_end_time - overlap_time
                    if offset_val < 0:
                        log_not_emit('WARNING', 'reference_params_generator', 
                            f'[_calculate_speaker_aware_offsets] overlap_time={overlap_time} > prev_end_time={prev_end_time}, clamping offset to 0', 
                            category='algorithm')
                        offset_val = 0
                    offsets[play_order] = offset_val
                    log_not_emit('DEBUG', 'reference_params_generator', 
                        f'[_calculate_speaker_aware_offsets] Using overlap_time: offset=prev_end_time({prev_end_time}) - {overlap_time} = {offset_val}', 
                        category='algorithm')
                elif overlap_rate is not None and overlap_rate > 0:
                    offsets[play_order] = prev_end_time * (1 - overlap_rate)
                    log_not_emit('DEBUG', 'reference_params_generator', 
                        f'[_calculate_speaker_aware_offsets] Using overlap_rate: offset=prev_end_time({prev_end_time}) * {1 - overlap_rate} = {prev_end_time * (1 - overlap_rate)}', 
                        category='algorithm')
                else:
                    offsets[play_order] = prev_end_time
                    log_not_emit('DEBUG', 'reference_params_generator', 
                        f'[_calculate_speaker_aware_offsets] No overlap, offset=prev_end_time={prev_end_time}', 
                        category='algorithm')
        
        prev_end_time = offsets[play_order] + audio_duration
        cumulative_duration += audio_duration
        
        log_not_emit('DEBUG', 'reference_params_generator', 
            f'[_calculate_speaker_aware_offsets] After i={i}: prev_end_time={prev_end_time}, cumulative_duration={cumulative_duration}, offsets={offsets}', 
            category='algorithm')
    
    log_not_emit('DEBUG', 'reference_params_generator', 
        f'[_calculate_speaker_aware_offsets] FINAL: offsets={offsets}', 
        category='algorithm')
    
    return offsets


def _calculate_audio_offsets(audios_config: List[Dict], overlap_rate: float, overlap_time: float = 0) -> Dict[int, float]:
    """
    计算每个音频播放项的开始时间偏移

    链式交叠公式：
    - overlap_time > 0: offset = cumulative_offset - overlap_time
    - overlap_rate > 0: offset = cumulative_offset * (1 - overlap_rate)
    - 否则: offset = cumulative_offset（顺序播放）

    Args:
        audios_config: 音频配置列表
        overlap_rate: 重叠率 (0.0-1.0)
        overlap_time: 重叠时间（秒），优先级高于 overlap_rate

    Returns:
        {play_order: offset_seconds}
    """
    offsets = {}
    sorted_audios = sorted(audios_config, key=lambda x: x.get('play_order', 0))

    log_not_emit('DEBUG', 'reference_params_generator', f'[_calculate_audio_offsets] START: overlap_rate={overlap_rate}, overlap_time={overlap_time}, audio_count={len(sorted_audios)}', category='algorithm')

    cumulative_offset = 0.0

    for i, audio_item in enumerate(sorted_audios):
        play_order = audio_item.get('play_order', 0)
        audio_id = audio_item.get('audio_id')

        audio_duration = 1.0
        if audio_id:
            audio = db.session.get(Audio, audio_id)
            if audio and audio.duration:
                audio_duration = audio.duration

        log_not_emit('DEBUG', 'reference_params_generator', f'[_calculate_audio_offsets] i={i}, play_order={play_order}, audio_id={audio_id}, audio_duration={audio_duration}, cumulative_offset={cumulative_offset}', category='algorithm')

        if i == 0:
            offsets[play_order] = 0
            log_not_emit('DEBUG', 'reference_params_generator', f'[_calculate_audio_offsets] i=0, set offset=0', category='algorithm')
        else:
            if overlap_time and overlap_time > 0:
                offset_val = cumulative_offset - overlap_time
                if offset_val < 0:
                    log_not_emit('WARNING', 'reference_params_generator', f'[_calculate_audio_offsets] overlap_time={overlap_time} > cumulative_offset={cumulative_offset}, clamping offset to 0', category='algorithm')
                    offset_val = 0
                offsets[play_order] = offset_val
                log_not_emit('DEBUG', 'reference_params_generator', f'[_calculate_audio_offsets] Using overlap_time: offset={cumulative_offset} - {overlap_time} = {offset_val}', category='algorithm')
            elif overlap_rate is not None and overlap_rate > 0:
                offsets[play_order] = cumulative_offset * (1 - overlap_rate)
                log_not_emit('DEBUG', 'reference_params_generator', f'[_calculate_audio_offsets] Using overlap_rate: offset={cumulative_offset} * {1 - overlap_rate} = {cumulative_offset * (1 - overlap_rate)}', category='algorithm')
            else:
                offsets[play_order] = cumulative_offset
                log_not_emit('DEBUG', 'reference_params_generator', f'[_calculate_audio_offsets] No overlap, offset=cumulative_offset={cumulative_offset}', category='algorithm')
        
        if overlap_time and overlap_time > 0:
            cumulative_offset = cumulative_offset - overlap_time + audio_duration
        elif overlap_rate is not None and overlap_rate > 0:
            cumulative_offset += audio_duration * (1 - overlap_rate)
        else:
            cumulative_offset += audio_duration
        
        log_not_emit('DEBUG', 'reference_params_generator', f'[_calculate_audio_offsets] After i={i}: cumulative_offset={cumulative_offset}, offsets={offsets}', category='algorithm')
    
    log_not_emit('DEBUG', 'reference_params_generator', f'[_calculate_audio_offsets] FINAL: offsets={offsets}', category='algorithm')
    return offsets


def _adjust_segment_timestamps(segments: List[Dict], offset: float, play_order: int = None) -> List[Dict]:
    """调整片段的时间戳"""
    adjusted = []
    for seg in segments:
        new_seg = seg.copy()
        if 'start' in new_seg:
            new_seg['start'] = new_seg['start'] + offset
        if 'end' in new_seg:
            new_seg['end'] = new_seg['end'] + offset
        if play_order is not None:
            new_seg['play_order'] = play_order
        adjusted.append(new_seg)
    return adjusted


def _merge_annotation_segments(segments_list: List[List[Dict]]) -> List[Dict]:
    """合并多个标注片段列表，并按时间排序"""
    all_segments = []
    for segments in segments_list:
        all_segments.extend(segments)
    
    all_segments.sort(key=lambda x: (x.get('start', 0), x.get('play_order', 0)))
    return all_segments


def _extract_field_from_audios(config: Dict, field_path: str, merge_mode: str = 'join',
                                annotation_code: str = None, annotation_format: str = None) -> Dict[str, Any]:
    """
    从音频标注的 data 中按字段路径提取值
    
    field_path 格式:
    - 'model'          → 取 data['model']（顶层标量）
    - 'segments[].emotion' → 遍历 data['segments']，每项取 ['emotion']（数组字段）
    
    merge_mode:
    - 'join'    → 空格拼接成字符串（适用于 text 类型）
    - 'collect' → 收集成数组
    - 'first'   → 只取第一个音频的值
    """
    record_test_type = config.get('_record_test_type', 'api')
    result = {'api': None, 'e2e': None}
    
    audios_config = config.get('audios', [])
    if not audios_config:
        return result
    
    sorted_audios = sorted(audios_config, key=lambda x: x.get('play_order', 0))
    
    preload_context = config.get('_preload_context', {})
    annotation_map = preload_context.get('annotation_map', {})
    
    # field_path 不含 '[]' 时，自动补 'segments[].' 前缀（标注统一存为 segments 结构）
    if '[]' not in field_path:
        field_path = f'segments[].{field_path}'
    is_segment_field = True
    seg_key = field_path.split('[].')[1] if '[].' in field_path else None
    
    def _get_annotations_for_audio(audio_id: int, code: str = None, fmt: str = None) -> List:
        if annotation_map and audio_id in annotation_map:
            all_anns = annotation_map[audio_id]
            if code and fmt:
                filtered = [a for a in all_anns if a.code == code and a.format == fmt]
                if filtered:
                    return filtered
            if code:
                filtered = [a for a in all_anns if a.code == code]
                if filtered:
                    return filtered
            if fmt:
                filtered = [a for a in all_anns if a.format == fmt]
                if filtered:
                    return filtered
            return all_anns
        else:
            query = AudioAnnotation.query.filter_by(audio_id=audio_id, deleted=False)
            if code:
                query = query.filter_by(code=code)
            if fmt:
                query = query.filter_by(format=fmt)
            return query.all()
    
    collected_values = []
    
    for audio_item in sorted_audios:
        audio_id = audio_item.get('audio_id')
        if not audio_id:
            continue
        
        annotations = _get_annotations_for_audio(audio_id, annotation_code, annotation_format)
        if not annotations:
            annotations = _get_annotations_for_audio(audio_id)
        
        for ann in annotations:
            if not ann.data or not isinstance(ann.data, dict):
                continue
            
            if is_segment_field:
                segments = ann.data.get('segments', [])
                for seg in segments:
                    val = seg.get(seg_key) if seg_key else None
                    if val is not None:
                        collected_values.append(val)
            else:
                # 兜底：顶层取值（理论上不会走到，field_path 已自动补 segments[]. 前缀）
                val = ann.data.get(field_path)
                if val is not None:
                    collected_values.append(val)
                    break
        
        if merge_mode == 'first' and collected_values:
            break
    
    if not collected_values:
        return result
    
    if merge_mode == 'first':
        value = collected_values[0]
    elif merge_mode == 'collect':
        value = collected_values
    else:  # join
        value = ' '.join(str(v) for v in collected_values)
    
    result[record_test_type] = value
    return result


def _extract_text_from_audios(config: Dict, text_field: str = None, annotation_code: str = None, annotation_format: str = None) -> Dict[str, str]:
    """从音频配置中提取文本"""
    reference_texts = {'api': '', 'e2e': ''}
    
    audios_config = config.get('audios', [])
    if not audios_config:
        return reference_texts
    
    sorted_audios = sorted(audios_config, key=lambda x: x.get('play_order', 0))
    
    preload_context = config.get('_preload_context', {})
    annotation_map = preload_context.get('annotation_map', {})
    audio_map = preload_context.get('audio_map', {})
    
    # 新双记录架构：使用记录的 test_type
    record_test_type = config.get('_record_test_type', 'api')
    
    def _extract_text_from_annotation(ann: AudioAnnotation, target_test_type: str) -> str:
        """从单个标注中提取文本，支持多种格式"""
        if not ann.data:
            return ''
        
        if isinstance(ann.data, str):
            return ann.data
        
        actual_format = ann.format
        
        if actual_format == 'text':
            return ann.data.get('text', '')
        
        segments = ann.data.get('segments', [])
        text_parts = []
        for seg in segments:
            text = seg.get('text', '')
            if text:
                text_parts.append(text)
        return ' '.join(text_parts)
    
    def _get_annotations_for_audio_text(audio_id: int, code: str = None, fmt: str = None) -> List:
        if annotation_map and audio_id in annotation_map:
            all_anns = annotation_map[audio_id]
            if code and fmt:
                filtered = [a for a in all_anns if a.code == code and a.format == fmt]
                if filtered:
                    return filtered
            return all_anns
        else:
            query = AudioAnnotation.query.filter_by(audio_id=audio_id, deleted=False)
            if code:
                query = query.filter_by(code=code)
            if fmt:
                query = query.filter_by(format=fmt)
            return query.all()
    
    for audio_item in sorted_audios:
        audio_id = audio_item.get('audio_id')
        # 新双记录架构：使用记录的 test_type，而非音频的 test_type
        if not audio_id:
            continue
        
        extracted_text = ''
        
        if annotation_code and annotation_format:
            log_not_emit('DEBUG', 'reference_params_generator', 
                f'_extract_text_from_audios: trying exact match code={annotation_code}, format={annotation_format}', 
                category='algorithm')
            
            annotations = _get_annotations_for_audio_text(audio_id, annotation_code, annotation_format)
            
            log_not_emit('DEBUG', 'reference_params_generator', 
                f'_extract_text_from_audios: exact match found {len(annotations)} annotations', 
                category='algorithm')
            
            for ann in annotations:
                extracted_text = _extract_text_from_annotation(ann, record_test_type)
                if extracted_text:
                    break
            
            if not extracted_text:
                log_not_emit('DEBUG', 'reference_params_generator', 
                    f'_extract_text_from_audios: fallback - querying all annotations for audio_id={audio_id}', 
                    category='algorithm')
                
                annotations = _get_annotations_for_audio_text(audio_id)
                
                log_not_emit('DEBUG', 'reference_params_generator', 
                    f'_extract_text_from_audios: fallback found {len(annotations)} annotations', 
                    category='algorithm')
                
                for ann in annotations:
                    extracted_text = _extract_text_from_annotation(ann, record_test_type)
                    if extracted_text:
                        log_not_emit('DEBUG', 'reference_params_generator', 
                            f'_extract_text_from_audios: extracted from code={ann.code}, format={ann.format}', 
                            category='algorithm')
                        break
        elif text_field:
            if audio_map and audio_id in audio_map:
                audio = audio_map[audio_id]
            else:
                audio = db.session.get(Audio, audio_id)
            if audio:
                extracted_text = getattr(audio, text_field, None) or ""
        
        if extracted_text:
            reference_texts[record_test_type] += extracted_text + " "
    
    for t in ['api', 'e2e']:
        reference_texts[t] = reference_texts[t].strip()
    
    return reference_texts


def _segments_to_rttm(segments: List[Dict], file_id: str = "test") -> str:
    """将 segments 转换为标准 RTTM 文本格式"""
    lines = []
    for seg in segments:
        speaker = seg.get('speaker', 'spk0')
        start = seg.get('start', 0)
        end = seg.get('end', 0)
        duration = end - start
        lines.append(f"SPEAKER {file_id} 1 {start:.3f} {duration:.3f} <NA> <NA> {speaker} <NA> <NA>")
    return '\n'.join(lines)


def _segments_to_stm(segments: List[Dict], file_id: str = "test", channel: int = 1) -> str:
    """将 segments 转换为标准 STM 文本格式"""
    lines = []
    for seg in segments:
        speaker = seg.get('speaker', 'spk0')
        start = seg.get('start', 0)
        end = seg.get('end', 0)
        text = seg.get('text', '')
        lines.append(f"{file_id} {channel} {speaker} {start:.3f} {end:.3f} {text}")
    return '\n'.join(lines)


def _extract_annotation_with_overlap(config: Dict, format: str = 'rttm', annotation_code: str = None, annotation_format: str = None) -> Dict[str, Any]:
    """
    从音频提取标注数据，支持重叠播放时间戳调整
    
    核心功能:
    - 根据 format 参数提取 RTTM/STM 格式的标注数据
    - 支持重叠播放场景，自动调整每个音频的时间戳偏移
    - 分别返回 api 和 e2e 两类测试的参考数据
    
    处理流程:
    1. 从 config.audios 获取音频配置列表
    2. 根据重叠率 (overlap_rate) 计算每个音频的开始时间偏移
    3. 按 test_type (api/e2e) 分组处理
    4. 对每个音频查询对应标注，调整时间戳后合并
    5. 将 segments 转换为标准 RTTM/STM 文本格式
    
    Args:
        config: 用例配置，包含 audios, algorithm_params, case_id 等
        format: 标注格式 ('rttm' 或 'stm')
        annotation_code: 标注代码（可选，用于精确匹配，如 'asr', 'translation'）
        annotation_format: 标注格式（可选，用于精确匹配，如 'json', 'rttm'）
    
    Returns:
        {
            'api': {'segments': [...], 'format': 'rttm', 'text': '...', 'json': '...'},
            'e2e': {'segments': [...], 'format': 'rttm', 'text': '...', 'json': '...'}
        }
        - segments: 时间戳调整后的 JSON 结构化数据列表
        - text: 标准 RTTM/STM 文本格式字符串
        - json: segments 的 JSON 字符串形式
    """
    result = {
        'api': {'segments': [], 'format': format, 'text': '', 'json': ''},
        'e2e': {'segments': [], 'format': format, 'text': '', 'json': ''}
    }
    
    audios_config = config.get('audios', [])
    if not audios_config:
        log_not_emit('DEBUG', 'reference_params_generator', 'No audios config found, returning empty result', category='algorithm')
        return result
    
    case_id = config.get('case_id', 'test_case')
    
    preload_context = config.get('_preload_context', {})
    annotation_map = preload_context.get('annotation_map', {})
    
    overlap_rate = _get_overlap_rate(config)
    overlap_time = _get_overlap_time(config)
    log_not_emit('DEBUG', 'reference_params_generator', f'Extracting annotation with overlap_rate={overlap_rate}, overlap_time={overlap_time}, format={format}', category='algorithm')
    
    audio_offsets = _calculate_speaker_aware_offsets(audios_config, overlap_rate, overlap_time, preload_context)
    log_not_emit('DEBUG', 'reference_params_generator', f'audio_offsets={audio_offsets}, audios_config={audios_config}', category='algorithm')
    
    # 双记录架构：所有音频属于 record_test_type
    record_test_type = config.get('_record_test_type', 'api')
    sorted_audios = sorted(audios_config, key=lambda x: x.get('play_order', 0))
    
    def _get_annotations_for_audio(audio_id: int, code: str = None, fmt: str = None) -> List:
        if annotation_map and audio_id in annotation_map:
            all_anns = annotation_map[audio_id]
            if code and fmt:
                filtered = [a for a in all_anns if a.code == code and a.format == fmt]
                if filtered:
                    return filtered
            if fmt:
                filtered = [a for a in all_anns if a.format == fmt]
                if filtered:
                    return filtered
            if code:
                filtered = [a for a in all_anns if a.code == code]
                if filtered:
                    return filtered
            return all_anns
        else:
            query = AudioAnnotation.query.filter_by(audio_id=audio_id, deleted=False)
            if code:
                query = query.filter_by(code=code)
            if fmt:
                query = query.filter_by(format=fmt)
            return query.all()
    
    segments_list = []
    top_level_extra = {}
    
    for audio_item in sorted_audios:
        audio_id = audio_item.get('audio_id')
        play_order = audio_item.get('play_order', 0)
        if not audio_id:
            continue
        
        offset = audio_offsets.get(play_order, 0)

        # 收集 data 顶层的额外字段（非已知字段），平铺到参考参数
        for ann in _get_annotations_for_audio(audio_id):
            if ann.data and isinstance(ann.data, dict):
                for k, v in ann.data.items():
                    if k not in _KNOWN_DATA_KEYS:
                        top_level_extra[k] = v
        
        if annotation_code and annotation_format:
            annotations = _get_annotations_for_audio(audio_id, annotation_code, annotation_format)
            
            if not annotations:
                annotations = _get_annotations_for_audio(audio_id, fmt='json')
            
            if not annotations and annotation_format != 'rttm':
                annotations = _get_annotations_for_audio(audio_id, fmt='rttm')
            
            if not annotations and annotation_format != 'stm':
                annotations = _get_annotations_for_audio(audio_id, fmt='stm')
            
            for ann in annotations:
                if ann.data:
                    segments = ann.data.get('segments', [])
                    adjusted_segments = _adjust_segment_timestamps(segments, offset, play_order)
                    segments_list.append(adjusted_segments)
        else:
            annotations = _get_annotations_for_audio(audio_id, fmt=format)
            
            if not annotations:
                json_annotations = _get_annotations_for_audio(audio_id, fmt='json')
                for ann in json_annotations:
                    if ann.data:
                        segments = ann.data.get('segments', [])
                        adjusted_segments = _adjust_segment_timestamps(segments, offset, play_order)
                        segments_list.append(adjusted_segments)
            else:
                for ann in annotations:
                    if ann.data:
                        segments = ann.data.get('segments', [])
                        adjusted_segments = _adjust_segment_timestamps(segments, offset, play_order)
                        segments_list.append(adjusted_segments)
            
            if not segments_list and format != 'rttm':
                rttm_annotations = _get_annotations_for_audio(audio_id, fmt='rttm')
                for ann in rttm_annotations:
                    if ann.data:
                        segments = ann.data.get('segments', [])
                        adjusted_segments = _adjust_segment_timestamps(segments, offset, play_order)
                        segments_list.append(adjusted_segments)
            
            if not segments_list and format != 'stm':
                stm_annotations = _get_annotations_for_audio(audio_id, fmt='stm')
                for ann in stm_annotations:
                    if ann.data:
                        segments = ann.data.get('segments', [])
                        adjusted_segments = _adjust_segment_timestamps(segments, offset, play_order)
                        segments_list.append(adjusted_segments)
    
    merged_segments = _merge_annotation_segments(segments_list)
    
    if format == 'rttm':
        text_content = _segments_to_rttm(merged_segments, case_id)
    else:
        text_content = _segments_to_stm(merged_segments, case_id)
    
    value_data = {
        'segments': merged_segments,
        'text': text_content,
        'json': json.dumps(merged_segments, ensure_ascii=False),
        **top_level_extra
    }
    
    # 返回兼容结构，但仅 record_test_type 有值
    result = {'api': {'segments': [], 'text': '', 'json': '[]'}, 'e2e': {'segments': [], 'text': '', 'json': '[]'}}
    result[record_test_type] = value_data
    
    return result


def _extract_translation_from_audios(config: Dict) -> Dict[str, Any]:
    """
    从音频的标注数据生成翻译参考文本
    
    用途:
    - 用于翻译算法，提取所有音频的标注文本作为参考翻译
    
    处理逻辑:
    1. 收集所有音频具备的翻译方向（source_language + target_language 组合）
    2. 找出所有音频**共同具备**的翻译方向（交集）
    3. 只为共同翻译方向生成标注
    
    返回格式:
    {
        'api': [
            {'translation_direction': 'zh2en', 'source_language': 'zh', 'target_language': 'en', 'text': '...'},
            {'translation_direction': 'en2zh', 'source_language': 'en', 'target_language': 'zh', 'text': '...'}
        ],
        'e2e': [...]
    }
    
    Args:
        config: 用例配置，包含 audios, translation_direction, source_language, target_language
        
    Returns:
        {'api': [...], 'e2e': [...]} 每个翻译方向一个对象
    """
    result = {'api': [], 'e2e': []}

    audios_config = config.get('audios', [])
    if not audios_config:
        return result

    sorted_audios = sorted(audios_config, key=lambda x: x.get('play_order', 0))

    preload_context = config.get('_preload_context', {})
    annotation_map = preload_context.get('annotation_map', {})
    
    # 新双记录架构：使用记录的 test_type
    record_test_type = config.get('_record_test_type', 'api')
    
    def _get_annotations_for_translation(audio_id: int, source_lang: str = None, target_lang: str = None) -> List:
        if annotation_map and audio_id in annotation_map:
            all_anns = annotation_map[audio_id]
            if source_lang and target_lang:
                filtered = [a for a in all_anns 
                           if a.source_language == source_lang and a.target_language == target_lang]
                if filtered:
                    return filtered
            return all_anns
        else:
            query = AudioAnnotation.query.filter_by(audio_id=audio_id, deleted=False)
            if source_lang:
                query = query.filter_by(source_language=source_lang)
            if target_lang:
                query = query.filter_by(target_language=target_lang)
            return query.all()

    audio_directions = {}
    audio_count = 0
    
    for audio_item in sorted_audios:
        audio_id = audio_item.get('audio_id')
        if not audio_id:
            continue
        
        audio_count += 1
        annotations = _get_annotations_for_translation(audio_id)
        
        directions = set()
        for ann in annotations:
            if ann.source_language and ann.target_language:
                direction = f"{ann.source_language}2{ann.target_language}"
                directions.add((ann.source_language, ann.target_language, direction))
        
        if record_test_type not in audio_directions:
            audio_directions[record_test_type] = directions
        else:
            if audio_count == 1:
                audio_directions[record_test_type] = directions
            else:
                audio_directions[record_test_type] = audio_directions[record_test_type] & directions

    for t_type in ['api', 'e2e']:
        if t_type not in audio_directions or not audio_directions[t_type]:
            continue
        
        for source_lang, target_lang, direction in audio_directions[t_type]:
            text_content = ''
            
            for audio_item in sorted_audios:
                audio_id = audio_item.get('audio_id')
                if not audio_id:
                    continue
                
                annotations = _get_annotations_for_translation(audio_id, source_lang, target_lang)
                
                for ann in annotations:
                    if ann.data:
                        segments = ann.data.get('segments', [])
                        for seg in segments:
                            text = seg.get('text', '')
                            if text:
                                text_content += text + " "
            
            text_content = text_content.strip()
            if text_content:
                result[t_type].append({
                    'translation_direction': direction,
                    'source_language': source_lang,
                    'target_language': target_lang,
                    'text': text_content
                })

    return result


def _extract_annotation_from_audios(config: Dict, format: str = None) -> Dict[str, str]:
    """从音频的标注数据提取文本（按格式过滤）"""
    record_test_type = config.get('_record_test_type', 'api')
    reference_texts = {'api': '', 'e2e': ''}

    audios_config = config.get('audios', [])
    if not audios_config:
        return reference_texts

    sorted_audios = sorted(audios_config, key=lambda x: x.get('play_order', 0))

    for audio_item in sorted_audios:
        audio_id = audio_item.get('audio_id')
        if not audio_id:
            continue

        query = AudioAnnotation.query.filter_by(audio_id=audio_id, deleted=False)
        if format:
            query = query.filter_by(format=format)

        annotations = query.all()

        for ann in annotations:
            if ann.data:
                segments = ann.data.get('segments', [])
                for seg in segments:
                    text = seg.get('text', '')
                    if text:
                        reference_texts[record_test_type] += text + " "

    for t_type in ['api', 'e2e']:
        reference_texts[t_type] = reference_texts[t_type].strip()

    return reference_texts


def get_reference_params_generator() -> type:
    """获取参考参数生成器类"""
    return ReferenceParamsGenerator


def get_reference_value(
    param: Dict[str, Any],
    test_type: str,
    ref_type: str = None,
    algorithm_type: str = None,
    case_config: Dict[str, Any] = None
) -> Any:
    """根据用例配置获取参考参数的值
    
    支持:
    - 翻译参数: 根据 translation_direction 过滤
    - ASR/RTTM/STM 参数: 根据 source_language 过滤
    
    Args:
        param: 参考参数字典 {code, type, api: {}, e2e: {}}
               翻译参数 api/e2e 是列表: [{translation_direction, source_language, target_language, text}, ...]
        test_type: 测试类型 ('api' 或 'e2e')
        ref_type: 参考参数类型 (text, rttm_text, rttm_json, stm_text, stm_json)
        algorithm_type: 算法类型 (translation/asr/tts/speaker_recognition)
        case_config: 用例配置，包含 translation_direction, source_language 等
    
    Returns:
        对应格式的值
    """
    log_not_emit('DEBUG', 'reference_params_generator', f'get_reference_value: test_type={test_type}, ref_type={ref_type}, algorithm_type={algorithm_type}', category='algorithm')
    
    value = param.get('value')
    
    if value is None:
        log_not_emit('DEBUG', 'reference_params_generator', 'No value found for param, returning empty string', category='algorithm')
        return ''
    
    if isinstance(value, list):
        if not value:
            return ''

        # json 类型参数（如 pause）直接返回整个 list
        if ref_type == 'json':
            return value

        # 直接返回第一个可用项
        first_item = value[0]
        if isinstance(first_item, dict):
            return first_item.get('text', '')
        return str(first_item)
    
    if not ref_type or ref_type == 'text' or ref_type == 'audio':
        if isinstance(value, dict):
            return {
                'text': value.get('text', ''),
                'json': value.get('json', value.get('segments', []))
            }
        return {'text': str(value) if value else '', 'json': []}
    
    if ref_type in ['rttm_text', 'stm_text']:
        if isinstance(value, dict):
            return {
                'text': value.get('text', ''),
                'json': value.get('json', value.get('segments', []))
            }
        return {'text': str(value) if value else '', 'json': []}
    
    if ref_type in ['rttm_json', 'stm_json', 'rttm', 'stm']:
        if isinstance(value, dict):
            return {
                'text': value.get('text', ''),
                'segments': value.get('segments', [])
            }
        return {'text': '', 'segments': []}
    
    if isinstance(value, dict):
        return value.get('text', '')
    return value
