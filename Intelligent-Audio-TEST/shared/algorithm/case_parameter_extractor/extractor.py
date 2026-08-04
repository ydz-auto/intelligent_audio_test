# -*- coding: utf-8 -*-
"""CaseParameterExtractor - 组合各 mixin 的最终实现类

原 case_parameter_extractor.py 中 CaseParameterExtractor 静态类被拆分为多个 mixin：
- CoreParamsMixin: loader 获取、算法类型/参数读取、统一接口 get_all_params
- DeviceApiParamsMixin: 设备/API 参数构建
- EvaluationParamsMixin: 评估参数构建（平面入口，兼容 rounds 顶层）
- ReferenceFileMixin: 参考参数文件加载（OSS / 本地）
- RoundEvaluationMixin: 轮次级评估参数提取（rounds-as-top-level）
- FormSchemaMixin: 算法表单 schema 生成
- DefaultOverlapMixin: 默认参数与重叠播放场景参数

通过多重继承组合所有方法，保持原 CaseParameterExtractor 的全部行为不变。
"""

from ._core_mixin import CoreParamsMixin
from ._device_api_mixin import DeviceApiParamsMixin
from ._evaluation_mixin import EvaluationParamsMixin
from ._reference_file_mixin import ReferenceFileMixin
from ._round_evaluation_mixin import RoundEvaluationMixin
from ._form_schema_mixin import FormSchemaMixin
from ._default_overlap_mixin import DefaultOverlapMixin


class CaseParameterExtractor(
    CoreParamsMixin,
    DeviceApiParamsMixin,
    EvaluationParamsMixin,
    ReferenceFileMixin,
    RoundEvaluationMixin,
    FormSchemaMixin,
    DefaultOverlapMixin,
):
    """
    用例参数提取器 - 静态类

    从用例配置中提取各类参数
    """


def get_parameter_extractor() -> "CaseParameterExtractor":
    """获取参数提取器"""
    return CaseParameterExtractor
