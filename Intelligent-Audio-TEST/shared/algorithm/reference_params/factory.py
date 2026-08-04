# -*- coding: utf-8 -*-
"""
工厂函数
"""

from typing import Dict, Any
from shared.utils.log_handler import log_not_emit

from .generator import ReferenceParamsGenerator


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
