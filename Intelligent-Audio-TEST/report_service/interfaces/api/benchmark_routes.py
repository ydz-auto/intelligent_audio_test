# -*- coding: utf-8 -*-
"""report_service Benchmark HTTP API 路由（FastAPI APIRouter）

路由前缀：/api/benchmarks（api_gateway 挂载为 /api/v1/benchmarks）
委托 application 层 handler（严格 CQRS）：
- 写操作 -> BenchmarkCommandHandler（排行计算 / 数据源 / 基线导入 / 映射更新）
- 读操作 -> BenchmarkQueryHandler（只读 ReadModel，无写副作用）

路由列表（设计文档 §7）：
    POST /api/benchmarks/ranking/compute        全量重算排行（设计文档 §7.1）
    GET  /api/benchmarks/ranking                排行查询（suite/category/metricCode/source/...）
    GET  /api/benchmarks/ranking/subjects       参与排行的被测主体列表
    GET  /api/benchmarks/sources                数据源列表
    POST /api/benchmarks/sources                创建数据源
    GET  /api/benchmarks/baselines              基线条目列表（当前生效版本）
    POST /api/benchmarks/baselines              批量导入基线（导入即不可变快照，幂等）
    POST /api/benchmarks/baselines/version      发布新基线版本（同导入语义，兼容设计文档路由）
    GET  /api/benchmarks/metric-mappings        指标映射列表
    POST /api/benchmarks/metric-mappings        创建指标映射（dimension_name 唯一）
    PUT  /api/benchmarks/metric-mappings/{id}   更新指标映射
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from report_service.application.commands.benchmark_commands import (
    ComputeBenchmarkRankingCommand,
    CreateBenchmarkMetricMappingCommand,
    CreateBenchmarkSourceCommand,
    ImportBenchmarkBaselinesCommand,
    UpdateBenchmarkMetricMappingCommand,
)
from report_service.application.handlers.benchmark_handlers import (
    BenchmarkCommandHandler,
    BenchmarkQueryHandler,
)
from report_service.application.queries.benchmark_queries import (
    GetBenchmarkRankingQuery,
    GetBenchmarkRankingSubjectsQuery,
    ListBenchmarkBaselinesQuery,
    ListBenchmarkMetricMappingsQuery,
    ListBenchmarkSourcesQuery,
)
from report_service.domain.entities.benchmark import BaselineDraftEntry

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/benchmarks', tags=['benchmark'])

_command_handler = BenchmarkCommandHandler()
_query_handler = BenchmarkQueryHandler()


class BenchmarkCommandRequest(BaseModel):
    """排行计算请求（全字段可选 = 全量重算）。"""
    suite: Optional[str] = None
    category: Optional[str] = None
    source: Optional[str] = None


class BenchmarkSourceCreateRequest(BaseModel):
    name: str
    provider: str = ''
    source_type: str = 'manual'
    url: str = ''
    version: str = ''
    description: str = ''
    created_by: str = ''


class BenchmarkBaselineEntryRequest(BaseModel):
    """外部基线条目（camelCase 与 snake_case 双兼容由 APIModel 层约定，此处保持 snake_case）。"""
    model_config = {'populate_by_name': True}

    model_name: str = Field(..., alias='modelName')
    metric_code: str = Field(..., alias='metricCode')
    value: float
    vendor: str = ''
    metric_name: str = Field('', alias='metricName')
    unit: str = ''
    direction: str = ''
    scenario_tags: List[str] = Field(default_factory=list, alias='scenarioTags')
    sample_size: Optional[int] = Field(None, alias='sampleSize')
    metric_date: str = Field('', alias='metricDate')


class BenchmarkBaselineImportRequest(BaseModel):
    source_id: int = Field(..., alias='sourceId')
    category: str
    entries: List[BenchmarkBaselineEntryRequest]
    published_by: str = Field('', alias='publishedBy')

    model_config = {'populate_by_name': True}


class BenchmarkMetricMappingCreateRequest(BaseModel):
    dimension_name: str = Field(..., alias='dimensionName')
    metric_code: str = Field(..., alias='metricCode')
    metric_name: str = Field('', alias='metricName')
    unit: str = ''
    direction: str
    scenario_tags: List[str] = Field(default_factory=list, alias='scenarioTags')
    active: bool = True

    model_config = {'populate_by_name': True}


class BenchmarkMetricMappingUpdateRequest(BaseModel):
    metric_name: Optional[str] = Field(None, alias='metricName')
    unit: Optional[str] = None
    direction: Optional[str] = None
    scenario_tags: Optional[List[str]] = Field(None, alias='scenarioTags')
    active: Optional[bool] = None

    model_config = {'populate_by_name': True}


# ---------- 排行 ----------

@router.post('/ranking/compute')
def compute_ranking(req: BenchmarkCommandRequest):
    command = ComputeBenchmarkRankingCommand(
        suite=(req.suite or '').strip() or None,
        category=(req.category or '').strip() or None,
        source=(req.source or '').strip() or None,
    )
    return _command_handler.handle_compute_ranking(command)


@router.get('/ranking')
def get_ranking(
    suite: str = Query(''),
    category: str = Query(''),
    metric_code: str = Query('', alias='metricCode'),
    source: str = Query(''),
    published_task_id: Optional[int] = Query(None, alias='publishedTaskId'),
    subject_name: str = Query('', alias='subjectName'),
):
    return _query_handler.handle_get_ranking(GetBenchmarkRankingQuery(
        suite=suite or None,
        category=category or None,
        metric_code=metric_code or None,
        source=source or None,
        published_task_id=published_task_id,
        subject_name=subject_name or None,
    ))


@router.get('/ranking/subjects')
def get_ranking_subjects(suite: str = Query('')):
    return _query_handler.handle_get_ranking_subjects(
        GetBenchmarkRankingSubjectsQuery(suite=suite or None))


# ---------- 外部基线数据源 ----------

@router.get('/sources')
def list_sources(
    page: int = Query(1),
    per_page: int = Query(10, alias='perPage'),
    source_type: str = Query('', alias='sourceType'),
):
    return _query_handler.handle_list_sources(ListBenchmarkSourcesQuery(
        page=page, per_page=per_page, source_type=source_type or None))


@router.post('/sources')
def create_source(req: BenchmarkSourceCreateRequest):
    command = CreateBenchmarkSourceCommand(
        name=req.name, provider=req.provider, source_type=req.source_type,
        url=req.url, version=req.version, description=req.description,
        created_by=req.created_by,
    )
    return _command_handler.handle_create_source(command)


# ---------- 外部基线导入（导入即不可变快照） ----------

@router.get('/baselines')
def list_baselines(
    category: str = Query(''),
    metric_code: str = Query('', alias='metricCode'),
    source_id: Optional[int] = Query(None, alias='sourceId'),
    page: int = Query(1),
    per_page: int = Query(20, alias='perPage'),
):
    return _query_handler.handle_list_baselines(ListBenchmarkBaselinesQuery(
        category=category or None, metric_code=metric_code or None,
        source_id=source_id, page=page, per_page=per_page))


def _run_baseline_import(req: BenchmarkBaselineImportRequest) -> Dict[str, Any]:
    entries = [
        BaselineDraftEntry(
            model_name=e.model_name, metric_code=e.metric_code, value=e.value,
            vendor=e.vendor, metric_name=e.metric_name, unit=e.unit,
            direction=e.direction, scenario_tags=e.scenario_tags,
            sample_size=e.sample_size, metric_date=e.metric_date,
        )
        for e in req.entries
    ]
    command = ImportBenchmarkBaselinesCommand(
        source_id=req.source_id, category=req.category,
        entries=entries, published_by=req.published_by,
    )
    return _command_handler.handle_import_baselines(command)


@router.post('/baselines')
def import_baselines(req: BenchmarkBaselineImportRequest):
    return _run_baseline_import(req)


@router.post('/baselines/version')
def publish_baseline_version(req: BenchmarkBaselineImportRequest):
    """发布新基线版本：导入即发布为不可变快照（与 /baselines 同语义，兼容设计文档 §7.2 路由）。"""
    return _run_baseline_import(req)


# ---------- 指标映射 ----------

@router.get('/metric-mappings')
def list_metric_mappings(active_only: bool = Query(False, alias='activeOnly')):
    return _query_handler.handle_list_metric_mappings(
        ListBenchmarkMetricMappingsQuery(active_only=active_only))


@router.post('/metric-mappings')
def create_metric_mapping(req: BenchmarkMetricMappingCreateRequest):
    command = CreateBenchmarkMetricMappingCommand(
        dimension_name=req.dimension_name, metric_code=req.metric_code,
        metric_name=req.metric_name, unit=req.unit, direction=req.direction,
        scenario_tags=req.scenario_tags, active=req.active,
    )
    return _command_handler.handle_create_metric_mapping(command)


@router.put('/metric-mappings/{mapping_id}')
def update_metric_mapping(mapping_id: int, req: BenchmarkMetricMappingUpdateRequest):
    command = UpdateBenchmarkMetricMappingCommand(
        mapping_id=mapping_id, metric_name=req.metric_name, unit=req.unit,
        direction=req.direction, scenario_tags=req.scenario_tags, active=req.active,
    )
    return _command_handler.handle_update_metric_mapping(command)
