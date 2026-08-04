# -*- coding: utf-8 -*-
"""
参考参数辅助函数和常量
"""

from typing import Dict, List, Any

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
