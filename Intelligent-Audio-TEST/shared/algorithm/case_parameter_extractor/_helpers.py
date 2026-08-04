# -*- coding: utf-8 -*-
"""case_parameter_extractor 包内部辅助函数与常量

将原 case_parameter_extractor.py 中的模块级辅助函数与常量拆分到此模块，
供各 mixin 及对外向后兼容导出使用。
"""

from typing import Dict, List, Any, Optional

# 参考参数存储的 OSS bucket 类别
_REF_PARAMS_BUCKET = 'ref_params'


def _get_algo_param(algorithm_params: Optional[List[Dict]], field_code: str, default=None):
    """从 algorithmParams [{field_code, field_value}] 数组中读取参数值

    Args:
        algorithm_params: [{field_code, field_value}] 格式的列表
        field_code: 要查找的字段代码
        default: 未找到时返回的默认值
    """
    if not algorithm_params:
        return default
    if isinstance(algorithm_params, list):
        for item in algorithm_params:
            if isinstance(item, dict) and item.get('field_code') == field_code:
                return item.get('field_value', default)
    return default


def _get_round_algo_params(algorithm_params_col: list, round_number: int) -> list:
    """从 test_cases.algorithm_params 列（按轮分组）中读取指定轮的 params

    Args:
        algorithm_params_col: [{round_number, params:[{field_code, field_value}]}]
        round_number: 轮次序号
    Returns:
        该轮的 params 列表 [{field_code, field_value}]，找不到返回 []
    """
    if not algorithm_params_col:
        return []
    for item in algorithm_params_col:
        if item.get('round_number') == round_number:
            return item.get('params', [])
    return []


def _normalize_algorithm_params(algorithm_params) -> Dict[str, Any]:
    """将 algorithm_params 统一转为 dict 格式 {field_code: field_value}

    支持输入:
    - dict: 直接返回
    - list of {field_code, field_value}: 转为 dict
    """
    if isinstance(algorithm_params, dict):
        return algorithm_params
    if isinstance(algorithm_params, list):
        result = {}
        for item in algorithm_params:
            if isinstance(item, dict) and 'field_code' in item:
                result[item['field_code']] = item.get('field_value')
        return result
    return {}


def _normalize_algorithm_params_to_list(algorithm_params) -> List[Dict]:
    """将 algorithm_params 统一转为 list 格式 [{field_code, field_value}]

    支持输入:
    - dict: {field_code: field_value, ...} 转为 list
    - list of {field_code, field_value}: 标准化后返回
    - list of {fieldCode, fieldValue}: 驼峰命名转为下划线
    - pydantic model: 调用 model_dump() 后提取
    """
    if not algorithm_params:
        return []
    if isinstance(algorithm_params, dict):
        return [{'field_code': k, 'field_value': v} for k, v in algorithm_params.items()]
    if isinstance(algorithm_params, list):
        result = []
        for item in algorithm_params:
            if hasattr(item, 'model_dump'):
                d = item.model_dump()
                fc = d.get('field_code') or d.get('fieldCode')
                fv = d.get('field_value', d.get('fieldValue'))
                if fc is not None:
                    result.append({'field_code': fc, 'field_value': fv})
                else:
                    result.append(d)
            elif isinstance(item, dict):
                fc = item.get('field_code') or item.get('fieldCode')
                fv = item.get('field_value', item.get('fieldValue'))
                if fc is not None:
                    result.append({'field_code': fc, 'field_value': fv})
                else:
                    result.append(item)
        return result
    return []
