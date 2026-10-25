# -*- coding: utf-8 -*-
"""算法 API 参数与用例专属参数 Schema

API 参数 CRUD、用例专属参数创建/更新、用例参数提取请求 Schema。
"""
from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from api_gateway.schemas.base import APIModel


# ========== API 参数 ==========

class AlgorithmApiParamCreate(APIModel):
    """创建API参数请求"""
    algorithm_type: str = Field(..., description='关联算法类型')
    # INT-1756（C6a）：API 实例级作用域，缺省为算法类型级默认；
    # 存在性与 algorithm_type 一致性由网关写路径校验（DB 不建跨服务外键）。
    api_id: Optional[int] = Field(None, ge=1, description='API 实例ID（空=算法类型级默认）')
    param_code: str = Field(..., min_length=1, max_length=50, description='参数代码')
    param_name: Optional[str] = Field(None, max_length=100, description='参数显示名称')
    label: Optional[str] = Field(None, max_length=100, description='字段显示名称')
    param_type: str = Field(..., description='参数类型：text, audio_stream, audio_file, text_file, rttm, stm, json')
    direction: str = Field(default='input', description='方向：input, output')
    required: bool = Field(default=False, description='是否必填')
    default_value: Optional[str] = Field(None)
    options_source: Optional[str] = Field(None, description='选项来源')
    options_field: Optional[str] = Field(None, description='选项值字段')
    options_label_field: Optional[str] = Field(None, description='选项显示字段')
    validation_rules: Optional[str] = Field(None)
    help_text: Optional[str] = Field(None)
    ui_order: int = Field(default=0, ge=0, description='界面排序')
    hidden: bool = Field(default=False, description='是否隐藏')
    field_path: Optional[str] = Field(
        None, max_length=255,
        description='输出字段在厂商原始响应中的取值路径（点号 + 数组下标，'
                    '如 data.events[0].text；空 = 按 param_code 取顶层键）')


class AlgorithmApiParamUpdate(APIModel):
    """更新API参数请求"""
    api_id: Optional[int] = Field(None, ge=1, description='API 实例ID（空=不改）')
    param_code: Optional[str] = Field(None, max_length=50)
    param_name: Optional[str] = Field(None, max_length=100)
    label: Optional[str] = Field(None, max_length=100)
    param_type: Optional[str] = Field(None)
    direction: Optional[str] = Field(None)
    required: Optional[bool] = Field(None)
    default_value: Optional[str] = Field(None)
    options_source: Optional[str] = Field(None)
    options_field: Optional[str] = Field(None)
    options_label_field: Optional[str] = Field(None)
    validation_rules: Optional[str] = Field(None)
    help_text: Optional[str] = Field(None)
    ui_order: Optional[int] = Field(None)
    hidden: Optional[bool] = Field(None)
    field_path: Optional[str] = Field(None, max_length=255)


class AlgorithmApiParamItem(APIModel):
    """API参数项"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    algorithm_type: str
    param_code: str
    param_name: Optional[str]
    label: Optional[str]
    param_type: str
    direction: str
    required: bool
    default_value: Optional[Any]
    options_source: Optional[str]
    options_field: Optional[str]
    options_label_field: Optional[str]
    validation: Optional[Any]
    help_text: Optional[str]
    ui_order: int
    hidden: bool
    field_path: Optional[str] = None


class AlgorithmApiParamListResponse(APIModel):
    """API参数列表响应"""
    data: List[AlgorithmApiParamItem]
    total: int


# ========== 用例专属参数 ==========

class CaseAlgorithmParamCreate(APIModel):
    """创建用例专属参数请求"""
    algorithm_type: str = Field(..., description='关联算法类型')
    param_code: str = Field(..., min_length=1, max_length=50, description='参数代码')
    param_name: Optional[str] = Field(None, max_length=100, description='参数显示名称')
    label: Optional[str] = Field(None, max_length=100, description='字段显示名称')
    param_type: str = Field(default='text', description='参数类型：text, number, textarea, slider, switch, audio_select, device_select, json')
    required: bool = Field(default=False, description='是否必填')
    default_value: Optional[str] = Field(None, description='默认值（JSON格式）')
    help_text: Optional[str] = Field(None)
    ui_order: int = Field(default=0, ge=0, description='界面排序')
    hidden: bool = Field(default=False, description='是否隐藏')
    scope: str = Field(default='common', max_length=10, pattern=r'^(common|api|e2e)$', description='参数适用范围 (common/api/e2e)')
    min_value: Optional[float] = Field(None, description='最小值 (slider/number)')
    max_value: Optional[float] = Field(None, description='最大值 (slider/number)')
    step: Optional[float] = Field(None, description='步长 (slider/number)')
    unit: Optional[str] = Field(None, max_length=20, description='单位显示 (如 cm, dB, s)')
    annotation_code: Optional[str] = Field(None, max_length=100, description='关联的音频标注代码（为空时默认同算法类型）')
    field_path: Optional[str] = Field(None, max_length=255, description='标注数据字段路径（为空时默认同参数代码）')


class CaseAlgorithmParamUpdate(APIModel):
    """更新用例专属参数请求"""
    param_name: Optional[str] = Field(None, max_length=100)
    label: Optional[str] = Field(None, max_length=100)
    param_type: Optional[str] = Field(None)
    required: Optional[bool] = Field(None)
    default_value: Optional[str] = Field(None)
    help_text: Optional[str] = Field(None)
    ui_order: Optional[int] = Field(None)
    hidden: Optional[bool] = Field(None)
    scope: Optional[str] = Field(None, max_length=10, pattern=r'^(common|api|e2e)$', description='参数适用范围 (common/api/e2e)')
    min_value: Optional[float] = Field(None, description='最小值 (slider/number)')
    max_value: Optional[float] = Field(None, description='最大值 (slider/number)')
    step: Optional[float] = Field(None, description='步长 (slider/number)')
    unit: Optional[str] = Field(None, max_length=20, description='单位显示 (如 cm, dB, s)')
    annotation_code: Optional[str] = Field(None, max_length=100, description='关联的音频标注代码（为空时默认同算法类型）')
    field_path: Optional[str] = Field(None, max_length=255, description='标注数据字段路径（为空时默认同参数代码）')


# ========== 用例参数请求（统一入口） ==========

class CaseParamCreateRequest(APIModel):
    """创建用例专属参数请求"""
    algorithm_type: str = Field(...)
    param_code: str = Field(...)
    param_name: Optional[str] = Field(None)
    label: Optional[str] = Field(None)
    param_type: str = Field(default='text')
    required: bool = Field(default=False)
    default_value: Optional[str] = Field(None)
    options_source: Optional[str] = Field(None)
    options_field: Optional[str] = Field(None)
    options_label_field: Optional[str] = Field(None)
    help_text: Optional[str] = Field(None)
    ui_order: int = Field(default=0)
    hidden: bool = Field(default=False)
    scope: str = Field(default='common', max_length=10, pattern=r'^(common|api|e2e)$', description='参数适用范围 (common/api/e2e)')


class CaseParamUpdateRequest(APIModel):
    """更新用例专属参数请求"""
    param_name: Optional[str] = Field(None)
    label: Optional[str] = Field(None)
    param_type: Optional[str] = Field(None)
    required: Optional[bool] = Field(None)
    default_value: Optional[str] = Field(None)
    options_source: Optional[str] = Field(None)
    options_field: Optional[str] = Field(None)
    options_label_field: Optional[str] = Field(None)
    help_text: Optional[str] = Field(None)
    ui_order: Optional[int] = Field(None)
    hidden: Optional[bool] = Field(None)
    scope: Optional[str] = Field(None, max_length=10, pattern=r'^(common|api|e2e)$', description='参数适用范围 (common/api/e2e)')


class ExtractParamsRequest(APIModel):
    """提取用例算法参数请求"""
    case_config: Dict[str, Any] = Field(default={})
