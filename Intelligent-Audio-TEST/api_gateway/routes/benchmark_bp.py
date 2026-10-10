"""Benchmark 排行路由 - BFF 路由层（D1 双轨排行）

只做 HTTP 接入 + 权限校验，委托给 application/services/benchmark/benchmark_service：
- BenchmarkService（写侧命令 + 读侧查询，gRPC 代理转发 report_service）

权限编码（设计文档 §9，冒号风格对齐现有编码）：
- benchmark:ranking:read / benchmark:ranking:compute
- benchmark:baseline:read / benchmark:baseline:write / benchmark:baseline:publish
- benchmark:mapping:manage
"""
from fastapi import APIRouter

from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.application.services.benchmark.benchmark_service import BenchmarkService
from api_gateway.routes._response import to_response

router = APIRouter()


def _handle(result):
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result


# ---------- 排行 ----------

@router.get('/ranking')
def get_ranking(_: None = require_permission('benchmark:ranking:read')):
    return _handle(BenchmarkService.get_ranking())


@router.get('/ranking/subjects')
def get_ranking_subjects(_: None = require_permission('benchmark:ranking:read')):
    return _handle(BenchmarkService.get_ranking_subjects())


@router.post('/ranking/compute')
def compute_ranking(_: None = require_permission('benchmark:ranking:compute')):
    return _handle(BenchmarkService.compute_ranking())


# ---------- 外部基线数据源 ----------

@router.get('/sources')
def list_sources(_: None = require_permission('benchmark:baseline:read')):
    return _handle(BenchmarkService.list_sources())


@router.post('/sources')
def create_source(_: None = require_permission('benchmark:baseline:write')):
    return _handle(BenchmarkService.create_source())


# ---------- 外部基线（导入即不可变快照） ----------

@router.get('/baselines')
def list_baselines(_: None = require_permission('benchmark:baseline:read')):
    return _handle(BenchmarkService.list_baselines())


@router.post('/baselines')
def import_baselines(_: None = require_permission('benchmark:baseline:publish')):
    return _handle(BenchmarkService.import_baselines())


@router.post('/baselines/version')
def publish_baseline_version(_: None = require_permission('benchmark:baseline:publish')):
    return _handle(BenchmarkService.publish_baseline_version())


# ---------- 指标映射 ----------

@router.get('/metric-mappings')
def list_metric_mappings(_: None = require_permission('benchmark:ranking:read')):
    return _handle(BenchmarkService.list_metric_mappings())


@router.post('/metric-mappings')
def create_metric_mapping(_: None = require_permission('benchmark:mapping:manage')):
    return _handle(BenchmarkService.create_metric_mapping())


@router.put('/metric-mappings/{mapping_id}')
def update_metric_mapping(mapping_id: int,
                          _: None = require_permission('benchmark:mapping:manage')):
    return _handle(BenchmarkService.update_metric_mapping(mapping_id))
