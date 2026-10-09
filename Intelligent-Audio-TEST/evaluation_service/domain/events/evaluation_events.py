# -*- coding: utf-8 -*-
"""评估上下文领域事件"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CaseEvaluated:
    """单用例评估完成事件"""
    task_id: int
    result_id: int
    test_case_id: str
    dimension_count: int = 0
    success: bool = True


@dataclass
class DimensionScored:
    """维度评分完成事件"""
    task_id: int
    result_id: int
    dimension_id: int
    score: Optional[float] = None
    dimension_value: Optional[str] = None


@dataclass
class ReevaluationSubmitted:
    """重新评估提交事件"""
    task_id: int
    reevaluate_type: str = "all"
    reextract_device_output: bool = False


@dataclass
class ReevaluationCompleted:
    """重新评估完成事件"""
    task_id: int
    success: bool = True
    message: str = ""


@dataclass
class DimensionResultDeleted:
    """维度评估结果删除事件"""
    result_ids: List[int] = field(default_factory=list)


@dataclass
class ThirdPartyEvalDispatched:
    """第三方评估请求已发出事件（8 步流程之①②审计：请求打包→传输）"""
    transfer_id: str
    task_id: Optional[int] = None
    test_case_id: Optional[str] = None
    dimensions: List[str] = field(default_factory=list)
    adapter: str = "multipart"
    src_zone: str = "B"
    dst_zone: str = "C"


@dataclass
class ThirdPartyEvalCompleted:
    """第三方评估完成事件（8 步流程之④⑤审计：结果回传→校验通过）"""
    transfer_id: str
    task_id: Optional[int] = None
    test_case_id: Optional[str] = None
    duration_ms: int = 0
    synced_back: bool = False


@dataclass
class ThirdPartyEvalFailed:
    """第三方评估失败事件（链路任一步失败，stage 标注失败环节）"""
    transfer_id: str
    task_id: Optional[int] = None
    test_case_id: Optional[str] = None
    stage: str = ""
    error: str = ""
