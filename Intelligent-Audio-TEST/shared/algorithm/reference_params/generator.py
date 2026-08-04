# -*- coding: utf-8 -*-
"""
参考参数生成器类
"""

import json
from typing import Dict, List, Any
from shared.infrastructure.storage import storage
from shared.models.database import db
from shared.models.models import Audio, AudioAnnotation
from shared.utils.log_handler import log_not_emit

from .helpers import (
    _REF_PARAMS_BUCKET,
    _build_ref_params_key,
    normalize_reference_params,
)
from .extractors import (
    _extract_field_from_audios,
    _extract_text_from_audios,
    _extract_annotation_with_overlap,
    _extract_translation_from_audios,
)


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
