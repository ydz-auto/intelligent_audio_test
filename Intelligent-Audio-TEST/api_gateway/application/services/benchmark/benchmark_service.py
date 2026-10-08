# -*- coding: utf-8 -*-
"""Benchmark 排行网关服务（CQRS）

按 DDD 原则，网关不直接操作 DB，通过 gRPC 调用 report_service
BenchmarkConfigService（由 grpc_proxies 代理转发）。
"""
import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.infrastructure.grpc_proxies import benchmark_config_service
from api_gateway.schemas.benchmark import (
    BenchmarkBaselineImportRequest,
    BenchmarkMetricMappingUpdateRequest,
    BenchmarkRankingComputeRequest,
    BenchmarkSourceCreateRequest,
)

logger = logging.getLogger(__name__)

_benchmark_acl = benchmark_config_service

_SOURCE_FILTER_VALUES = ('platform_test', 'external_import')


def _parse_query_params():
    """查询参数解析（request.args → 扁平 dict）"""
    return {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}


class BenchmarkService:
    """Benchmark 排行网关服务（CQRS）。"""

    # ---------- 写侧 ----------

    @staticmethod
    def compute_ranking():
        try:
            req = BenchmarkRankingComputeRequest.model_validate(request.get_json(silent=True) or {})
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", code=ErrorCode.INVALID_PARAMS, http_code=400)
        result = _benchmark_acl.compute_ranking(req.model_dump(by_alias=False, exclude_none=True))
        if not result.get('success'):
            return error_response(
                result.get('message', '排行计算失败'),
                code=result.get('code', ErrorCode.OPERATION_FAILED), http_code=400)
        return success_response(result.get('data'), result.get('message', '排行计算完成'))

    @staticmethod
    def create_source():
        try:
            req = BenchmarkSourceCreateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", code=ErrorCode.INVALID_PARAMS, http_code=400)
        result = _benchmark_acl.create_source(req.model_dump(by_alias=False, exclude_none=True))
        if not result.get('success'):
            return error_response(
                result.get('message', '创建数据源失败'),
                code=result.get('code', ErrorCode.OPERATION_FAILED), http_code=400)
        return success_response(result.get('data'), result.get('message', '数据源创建成功'), http_code=201)

    @staticmethod
    def _import_baselines():
        try:
            req = BenchmarkBaselineImportRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", code=ErrorCode.INVALID_PARAMS, http_code=400)
        result = _benchmark_acl.import_baselines(req.model_dump(by_alias=False, exclude_none=True))
        if not result.get('success'):
            return error_response(
                result.get('message', '基线导入失败'),
                code=result.get('code', ErrorCode.OPERATION_FAILED),
                http_code=400,
                detail=(result.get('data') or {}).get('errors') or None,
            )
        return success_response(result.get('data'), result.get('message', '基线导入成功'), http_code=201)

    @staticmethod
    def import_baselines():
        """批量导入外部基线（导入即不可变快照新版本，幂等）。"""
        return BenchmarkService._import_baselines()

    @staticmethod
    def publish_baseline_version():
        """发布新基线版本（与导入同语义，兼容设计文档 §7.2 路由）。"""
        return BenchmarkService._import_baselines()

    @staticmethod
    def update_metric_mapping(mapping_id: int):
        try:
            req = BenchmarkMetricMappingUpdateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", code=ErrorCode.INVALID_PARAMS, http_code=400)
        result = _benchmark_acl.update_metric_mapping(
            mapping_id, req.model_dump(by_alias=False, exclude_none=True))
        if not result.get('success'):
            return error_response(
                result.get('message', '更新指标映射失败'),
                code=result.get('code', ErrorCode.OPERATION_FAILED), http_code=400)
        return success_response(result.get('data'), result.get('message', '指标映射已更新'))

    # ---------- 读侧 ----------

    @staticmethod
    def get_ranking():
        params = _parse_query_params()
        source = (params.get('source') or '').strip().lower()
        if source and source not in _SOURCE_FILTER_VALUES:
            return error_response(
                'source 筛选参数仅支持 platform_test / external_import',
                code=ErrorCode.INVALID_PARAMS, http_code=400)
        result = _benchmark_acl.get_ranking({
            'suite': (params.get('suite') or '').strip(),
            'category': (params.get('category') or '').strip(),
            'metric_code': (params.get('metricCode') or params.get('metric_code') or '').strip(),
            'source': source,
            'published_task_id': params.get('publishedTaskId') or params.get('published_task_id'),
            'subject_name': (params.get('subjectName') or params.get('subject_name') or '').strip(),
        })
        if not result.get('success'):
            return error_response(result.get('message', '查询排行失败'), code=result.get('code', 500))
        return success_response(result.get('data'))

    @staticmethod
    def get_ranking_subjects():
        params = _parse_query_params()
        result = _benchmark_acl.get_ranking_subjects({'suite': (params.get('suite') or '').strip()})
        if not result.get('success'):
            return error_response(result.get('message', '查询被测主体失败'), code=result.get('code', 500))
        return success_response(result.get('data'))

    @staticmethod
    def list_sources():
        params = _parse_query_params()
        result = _benchmark_acl.list_sources({
            'page': params.get('page', 1),
            'per_page': params.get('perPage', params.get('per_page', 10)),
            'source_type': (params.get('sourceType') or params.get('source_type') or '').strip(),
        })
        if not result.get('success'):
            return error_response(result.get('message', '查询数据源失败'), code=result.get('code', 500))
        return success_response(result.get('data'))

    @staticmethod
    def list_baselines():
        params = _parse_query_params()
        result = _benchmark_acl.list_baselines({
            'category': (params.get('category') or '').strip(),
            'metric_code': (params.get('metricCode') or params.get('metric_code') or '').strip(),
            'source_id': params.get('sourceId') or params.get('source_id'),
            'page': params.get('page', 1),
            'per_page': params.get('perPage', params.get('per_page', 20)),
        })
        if not result.get('success'):
            return error_response(result.get('message', '查询基线失败'), code=result.get('code', 500))
        return success_response(result.get('data'))

    @staticmethod
    def list_metric_mappings():
        params = _parse_query_params()
        result = _benchmark_acl.list_metric_mappings({
            'active_only': (params.get('activeOnly') or params.get('active_only') or '') in ('true', 'True', '1'),
        })
        if not result.get('success'):
            return error_response(result.get('message', '查询指标映射失败'), code=result.get('code', 500))
        return success_response(result.get('data'))
