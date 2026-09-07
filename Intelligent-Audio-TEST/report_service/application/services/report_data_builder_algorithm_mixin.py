# -*- coding: utf-8 -*-
"""报告数据构建器 —— 算法结果构建 Mixin。

从 report_data_builder.py 拆分而来，承载：
- build_algorithm_results_for_result: 为单个 TestResult 构建 algorithm_results 扁平列表
  （合并 aux 辅助参数 + 设备/API 原始结果，供报告页和详情页共用）
- _normalize_audio_path: 音频路径转静态资源相对路径辅助
"""
from shared.utils.audio_path_utils import normalize_audio_path
from shared.domain import algorithm_result_builder as _algo_result_builder


class ReportDataAlgorithmMixin:
    """algorithm_results 构建：aux 参数提取 + 策略化算法结果组装。

    收敛后统一走 shared.domain.algorithm_result_builder，本类保留对外方法名
    以兼容 _result_group_mixin / case_mixin 等既有调用方。
    """

    @staticmethod
    def build_algorithm_results_for_result(
        result, resource, algo_res, result_data, aux_params_map,
        dim_result_rows, output_fields, algorithm_type
    ):
        """为单个 TestResult 构建 algorithm_results 扁平列表（委托共享组件）。"""
        return _algo_result_builder.build_algorithm_results_for_result(
            result, resource, algo_res, result_data,
            aux_params_map, dim_result_rows, output_fields, algorithm_type,
            normalize_audio_path_fn=ReportDataAlgorithmMixin._normalize_audio_path,
        )

    @staticmethod
    def _normalize_audio_path(abs_path):
        """将音频文件的绝对路径转换为相对 STATIC_BASE_PATH 的相对路径。"""
        try:
            from shared.infrastructure.config import Config
            static_base = getattr(Config, 'STATIC_BASE_PATH', '')
            return normalize_audio_path(abs_path, static_base)
        except Exception:
            return abs_path
