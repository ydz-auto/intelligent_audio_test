# -*- coding: utf-8 -*-
"""报告数据构建器 —— 算法结果构建 Mixin。

从 report_data_builder.py 拆分而来，承载：
- build_algorithm_results_for_result: 为单个 TestResult 构建 algorithm_results 扁平列表
  （合并 aux 辅助参数 + 设备/API 原始结果，供报告页和详情页共用）
- _normalize_audio_path: 音频路径转静态资源相对路径辅助
"""
import json

from shared.utils.path_extractor import extract_by_path
from shared.constants.device_fields import DEVICE_FIELDS
from shared.utils.audio_path_utils import normalize_audio_path
from shared.domain.algorithm_result_strategy import AlgorithmStrategyFactory


class ReportDataAlgorithmMixin:
    """algorithm_results 构建：aux 参数提取 + 策略化算法结果组装。"""

    @staticmethod
    def build_algorithm_results_for_result(
        result, resource, algo_res, result_data, aux_params_map,
        dim_result_rows, output_fields, algorithm_type
    ):
        """为单个 TestResult 构建 algorithm_results 扁平列表。

        合并 aux 辅助参数 + 设备/API 原始结果，供报告页和详情页共用。

        Args:
            result: TestResult 对象（dict 或 ORM，仅用于取 result.id）
            resource: 设备/API 名称
            algo_res: algorithm_result (dict)
            result_data: 完整 result_data (dict 或 None)
            aux_params_map: {dimension_id: [{param, dimension_name}, ...]}
            dim_result_rows: 该 TestResult 的 TestResultDimension 行列表
            output_fields: 算法输出字段列表
            algorithm_type: 算法类型

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
                    param_code = p.get('param_code') if isinstance(p, dict) else getattr(p, 'param_code', None)
                    if param_code:
                        param_to_dim[param_code] = aux_info['dimension_name']
                        param_to_type[param_code] = p.get('field_type', 'text') if isinstance(p, dict) else getattr(p, 'field_type', 'text')

        # ── 2. 提取 aux 辅助参数值 ──
        aux_values = {}

        # 2a. 从 evaluation_data 提取
        if result_data:
            eval_data = result_data.get('evaluation_data') or result_data.get('eval_data') or {}
            if isinstance(eval_data, dict):
                for param_code in param_to_dim:
                    if param_code in eval_data:
                        aux_values[param_code] = eval_data[param_code]

        # 2b. 从 api_raw_response 补充
        for dr in dim_result_rows:
            raw_resp = dr.get('api_raw_response') if isinstance(dr, dict) else getattr(dr, 'api_raw_response', None)
            if not raw_resp:
                continue
            if isinstance(raw_resp, str):
                try:
                    raw_resp = json.loads(raw_resp)
                except Exception:
                    continue
            dim_id = dr.get('dimension_id') if isinstance(dr, dict) else getattr(dr, 'dimension_id', None)
            for aux_info in (aux_params_map.get(dim_id, []) if aux_params_map else []):
                p = aux_info['param']
                param_code = p.get('param_code') if isinstance(p, dict) else getattr(p, 'param_code', None)
                if not param_code or param_code in aux_values:
                    continue
                field_path = p.get('field_path') if isinstance(p, dict) else getattr(p, 'field_path', None)
                value = extract_by_path(raw_resp, field_path)
                if value is not None:
                    aux_values[param_code] = value

        # 输出 aux 参数
        for param_code, param_value in aux_values.items():
            if param_value is None:
                continue
            algorithm_results.append({
                'device': resource,
                'param_code': param_code,
                'param_type': param_to_type.get(param_code, 'text'),
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
            normalize_audio_path_fn=ReportDataAlgorithmMixin._normalize_audio_path,
        ))

        return algorithm_results

    @staticmethod
    def _normalize_audio_path(abs_path):
        """将音频文件的绝对路径转换为相对 STATIC_BASE_PATH 的相对路径。"""
        try:
            from shared.infrastructure.config import Config
            static_base = getattr(Config, 'STATIC_BASE_PATH', '')
            return normalize_audio_path(abs_path, static_base)
        except Exception:
            return abs_path
