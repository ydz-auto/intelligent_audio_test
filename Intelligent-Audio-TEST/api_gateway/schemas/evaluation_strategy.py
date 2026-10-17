# -*- coding: utf-8 -*-
"""评估策略 Schema（INT-590：整体评估维度+全局背景噪声 抽为可复用策略）。

策略 config 与用例 config.dimensions / config.background_noise 同构
（复用现有协议字段，非宽松 Dict）。维度条目结构化声明
round_scope / llmJudgeConfig，保证回显不丢。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import ConfigDict, Field

from api_gateway.schemas.base import APIModel
from api_gateway.schemas.common import PaginatedData


class EvaluationStrategyDimensionItem(APIModel):
    """策略维度条目 — 与用例 config.dimensions 同构。

    llmJudgeConfig：LLM Judge 配置（model/promptTemplate），目前仅前端 UI
    概念，后端评估实际取维度 input_params 默认值（endpoint_worker.py:350）；
    本卡结构化该字段不影响执行，标注未消费。
    """
    model_config = ConfigDict(extra='allow')

    id: Optional[int] = Field(None)
    name: Optional[str] = Field(None)
    display_name: Optional[str] = Field(None)
    weight: Optional[float] = Field(None)
    threshold: Optional[float] = Field(None)
    # 多轮整体评估口径：multi=整体评估（config.dimensions 口径），
    # single/per_round=逐轮口径（rounds[].evaluation.dimensions）
    round_scope: Optional[str] = Field(None, validation_alias='roundScope')
    # LLM Judge 配置（仅前端 UI 概念，后端评估未消费，标注）
    llmJudgeConfig: Optional[Dict[str, Any]] = Field(None)


class EvaluationStrategyConfig(APIModel):
    """策略配置 — {dimensions, background_noise}，与用例 config 同构。"""
    model_config = ConfigDict(extra='allow')

    dimensions: Optional[List[EvaluationStrategyDimensionItem]] = Field(default_factory=list)
    background_noise: Optional[Dict[str, Any]] = Field(None)


class EvaluationStrategyCreateSchema(APIModel):
    """创建评估策略请求体。"""
    name: str = Field(...)
    description: Optional[str] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    enabled: Optional[bool] = Field(True)
    config: EvaluationStrategyConfig = Field(...)


class EvaluationStrategyUpdateSchema(APIModel):
    """更新评估策略请求体（P1：编辑不回灌已引用用例，用例/任务均快照语义）。"""
    name: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    enabled: Optional[bool] = Field(None)
    config: Optional[EvaluationStrategyConfig] = Field(None)


class EvaluationStrategyListItem(APIModel):
    """策略列表项 — 含 referenced_case_count（列表展示 + 删保护同源）。"""
    id: str = Field(...)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    enabled: bool = Field(...)
    config: EvaluationStrategyConfig = Field(default_factory=EvaluationStrategyConfig)
    referenced_case_count: int = Field(0)
    created_by_user_id: Optional[int] = Field(None)
    updated_by_user_id: Optional[int] = Field(None)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)


class EvaluationStrategyListData(PaginatedData[EvaluationStrategyListItem]):
    pass


class EvaluationStrategyDetailData(APIModel):
    """策略详情。"""
    id: str = Field(...)
    name: str = Field(...)
    description: Optional[str] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    enabled: bool = Field(...)
    config: EvaluationStrategyConfig = Field(default_factory=EvaluationStrategyConfig)
    referenced_case_count: int = Field(0)
    created_by_user_id: Optional[int] = Field(None)
    updated_by_user_id: Optional[int] = Field(None)
    created_at: Optional[str] = Field(None)
    updated_at: Optional[str] = Field(None)


class EvaluationStrategyListQuery(APIModel):
    """策略列表查询参数。"""
    page: int = Field(1, ge=1)
    per_page: int = Field(10)
    keyword: Optional[str] = Field(None)
    algorithm_type: Optional[str] = Field(None)
    # 启用状态过滤：""=全部，"true"/"false"（三态字符串）
    enabled: Optional[str] = Field(None)
