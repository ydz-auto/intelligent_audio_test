# -*- coding: utf-8 -*-
"""算法结果构建公共组件 —— report_service / task_service 共用。

承载：
- build_algorithm_results_for_result: 为单个 TestResult 构建 algorithm_results 扁平列表
  （合并 aux 辅助参数 + 设备/API 原始结果，供报告页和详情页共用）
- collect_aux_values: aux 辅助参数值收集器（按 field_path 从响应中提取）

消除 task_service._build_algorithm_results_for_result 与
report_service.ReportDataBuilder.build_algorithm_results_for_result 的整份复制。
"""
import json

from shared.utils.path_extractor import extract_by_path
from shared.constants.device_fields import DEVICE_FIELDS
from shared.utils.audio_path_utils import normalize_audio_path
from shared.domain.algorithm_result_strategy import AlgorithmStrategyFactory
from shared.models.common_enums import FieldType


def _param_get(p, key, default=None):
    """兼容 dict 与 ORM 两种参数对象取值。"""
    return p.get(key, default) if isinstance(p, dict) else getattr(p, key, default)


def collect_aux_values(resp_data, aux_entries):
    """从已解析的响应数据中按 field_path 提取 aux 参数值。

    Args:
        resp_data: 已解析的响应 dict（如 api_raw_response 反序列化结果）
        aux_entries: 维度 aux 参数列表，每项为 {"param": dict|ORM, "dimension_name": str}

    Returns:
        dict: {param_code: value}，仅收集提取成功（非 None）的项。
    """
    if not isinstance(resp_data, dict):
        return {}
    values = {}
    for aux_info in aux_entries or []:
        p = aux_info['param']
        param_code = _param_get(p, 'param_code')
        field_path = _param_get(p, 'field_path')
        if not param_code or not field_path:
            continue
        value = extract_by_path(resp_data, field_path)
        if value is not None:
            values[param_code] = value
    return values


def build_algorithm_results_for_result(
    result, resource, algo_res, result_data, aux_params_map,
    dim_result_rows, output_fields, algorithm_type,
    normalize_audio_path_fn=None,
):
    """为单个 TestResult 构建 algorithm_results 扁平列表。

    合并 aux 辅助参数 + 设备/API 原始结果，供报告页和详情页共用。
    轮次映射等报告特有逻辑由调用方在返回结果后自行处理，本函数保持单一职责。

    Args:
        result: TestResult 对象（dict 或 ORM，当前仅作签名占位）
        resource: 设备/API 名称
        algo_res: algorithm_result (dict)
        result_data: 完整 result_data (dict 或 None)
        aux_params_map: {dimension_id: [{param, dimension_name}, ...]}
        dim_result_rows: 该 TestResult 的维度结果行列表（dict 或 ORM 均可）
        output_fields: 算法输出字段列表
        algorithm_type: 算法类型
        normalize_audio_path_fn: 音频路径规范化函数（缺省用 shared Config）

    Returns:
        list[dict]: algorithm_results 扁平列表
    """
    algorithm_results = []

    if not (algo_res or result_data):
        return algorithm_results

    # ── 1. 构建 param_code → (dimension_name, field_type) 全局映射 ──
    param_to_dim = {}
    param_to_type = {}
    if aux_params_map:
        for _dim_id, aux_list in aux_params_map.items():
            for aux_info in aux_list:
                p = aux_info['param']
                param_code = _param_get(p, 'param_code')
                if param_code:
                    param_to_dim[param_code] = aux_info['dimension_name']
                    param_to_type[param_code] = _param_get(p, 'field_type', FieldType.TEXT.value)

    # ── 2. 提取 aux 辅助参数值 ──
    aux_values = {}

    # 2a. 从 evaluation_data 提取
    if result_data:
        eval_data = result_data.get('evaluation_data') or result_data.get('eval_data') or {}
        if isinstance(eval_data, dict):
            for param_code in param_to_dim:
                if param_code in eval_data:
                    aux_values[param_code] = eval_data[param_code]

    # 2b. 从 api_raw_response 补充（兼容旧数据兜底）
    for dr in dim_result_rows:
        raw_resp = dr.get('api_raw_response') if isinstance(dr, dict) else getattr(dr, 'api_raw_response', None)
        if not raw_resp:
            continue
        if isinstance(raw_resp, str):
            try:
                raw_resp = json.loads(raw_resp)
            except Exception:
                continue
        dim_id = (dr.get('dimension_id') or dr.get('id')) if isinstance(dr, dict) else getattr(dr, 'dimension_id', None)
        entries = aux_params_map.get(dim_id, []) if aux_params_map else []
        for param_code, value in collect_aux_values(raw_resp, entries).items():
            if param_code not in aux_values:
                aux_values[param_code] = value

    # 输出 aux 参数
    for param_code, param_value in aux_values.items():
        if param_value is None:
            continue
        algorithm_results.append({
            'device': resource,
            'param_code': param_code,
            'param_type': param_to_type.get(param_code, FieldType.TEXT.value),
            'label': param_code,
            'value': param_value,
            'dimension_name': param_to_dim.get(param_code),
        })

    # ── 3. 提取设备/API 原始执行结果 ──
    combined_data = {**(algo_res or {}), **(result_data or {})}

    # 通过策略模式消除 algorithm_type 硬编码分支
    strategy = AlgorithmStrategyFactory.get_strategy(algorithm_type)
    algorithm_results.extend(strategy.process_algorithm_result(
        combined_data=combined_data,
        output_fields=output_fields,
        resource=resource,
        device_fields=DEVICE_FIELDS,
        algo_res=algo_res,
        result_data=result_data,
        normalize_audio_path_fn=normalize_audio_path_fn or _default_normalize_audio_path,
    ))

    return algorithm_results


def _default_normalize_audio_path(abs_path):
    """默认音频路径规范化：绝对路径 → 相对 shared STATIC_BASE_PATH 的相对路径。"""
    try:
        from shared.infrastructure.config import Config
        return normalize_audio_path(abs_path, getattr(Config, 'STATIC_BASE_PATH', ''))
    except Exception:
        return abs_path
