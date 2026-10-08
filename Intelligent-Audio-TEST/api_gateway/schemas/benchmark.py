"""Benchmark 排行 Schema（api_gateway 请求模型）

字段以 snake_case 定义（APIModel alias_generator=to_camel 使请求体同时接受
camelCase 与 snake_case）；基线条目 model_name/metric_code 为必填。
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from api_gateway.schemas.base import APIModel


class BenchmarkRankingComputeRequest(APIModel):
    """排行计算请求（全字段可选 = 全量重算；不支持按任务范围，见设计文档 §7.1）"""
    suite: Optional[str] = Field(None)
    category: Optional[str] = Field(None)
    source: Optional[str] = Field(None, description='platform_test / external_import')


class BenchmarkBaselineEntryRequest(APIModel):
    """外部基线条目"""
    model_name: str = Field(..., description='模型名')
    metric_code: str = Field(..., description='排行指标代码')
    value: float = Field(..., description='指标值')
    vendor: str = Field('')
    metric_name: str = Field('')
    unit: str = Field('')
    direction: str = Field('', description='lower_is_better / higher_is_better')
    scenario_tags: List[str] = Field(default_factory=list)
    sample_size: Optional[int] = Field(None)
    metric_date: str = Field('')


class BenchmarkBaselineImportRequest(APIModel):
    """外部基线批量导入请求（导入即不可变快照新版本）"""
    source_id: int = Field(...)
    category: str = Field(..., description='asr / voice_llm / tts / translation')
    entries: List[BenchmarkBaselineEntryRequest] = Field(default_factory=list)
    published_by: str = Field('')


class BenchmarkSourceCreateRequest(APIModel):
    """外部基线数据源创建请求"""
    name: str = Field(...)
    provider: str = Field('')
    source_type: str = Field('manual', description='official / third_party / self_test / manual')
    url: str = Field('')
    version: str = Field('')
    description: str = Field('')
    created_by: str = Field('')


class BenchmarkMetricMappingUpdateRequest(APIModel):
    """指标映射更新请求（仅提交需更新的字段）"""
    metric_name: Optional[str] = Field(None)
    unit: Optional[str] = Field(None)
    direction: Optional[str] = Field(None)
    scenario_tags: Optional[List[str]] = Field(None)
    active: Optional[bool] = Field(None)
