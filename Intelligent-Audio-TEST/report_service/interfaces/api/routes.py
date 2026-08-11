# -*- coding: utf-8 -*-
"""report_service HTTP API 路由（FastAPI APIRouter）

路由前缀：/api/reports
委托 application 层 handler：
- 写操作 -> ReportCommandHandler
- 读操作 -> ReportQueryHandler

路由列表：
    POST   /api/reports                  创建报告
    POST   /api/reports/generate         生成报告
    GET    /api/reports                  列出报告
    GET    /api/reports/<id>             获取报告
    GET    /api/reports/by_task/<task_id>  按任务获取报告
    GET    /api/reports/trend            获取趋势数据
    PUT    /api/reports/<id>/status      更新报告状态
    DELETE /api/reports/<id>             删除报告
    GET    /api/reports/<id>/summary     获取报告摘要
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from report_service.application.commands.report_commands import (
    CreateReportCommand,
    DeleteReportCommand,
    GenerateReportCommand,
    UpdateReportStatusCommand,
)
from report_service.application.handlers.report_handlers import (
    ReportCommandHandler,
    ReportQueryHandler,
)
from report_service.application.queries.report_queries import (
    GetReportByTaskQuery,
    GetReportQuery,
    GetReportSummaryQuery,
    GetTrendDataQuery,
    ListReportsQuery,
)
from report_service.domain.entities import ReportAggregate

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/reports', tags=['report'])


class CreateReportRequest(BaseModel):
    task_id: int
    report_type: str = 'standard'
    config: dict = {}


class GenerateReportRequest(BaseModel):
    task_id: int
    report_type: str = 'standard'


class UpdateReportStatusRequest(BaseModel):
    status: str


def _aggregate_to_dict(aggregate: Optional[ReportAggregate]) -> Optional[Dict[str, Any]]:
    """将 ReportAggregate 聚合根序列化为字典。"""
    if aggregate is None:
        return None
    return {
        'id': aggregate.id,
        'task_id': aggregate.task_id,
        'report_type': aggregate.report_type,
        'status': aggregate.status,
        'config': dict(aggregate.config) if aggregate.config else {},
        'created_at': str(aggregate.created_at) if aggregate.created_at is not None else None,
        'summaries': [
            {
                'id': s.id,
                'report_id': s.report_id,
                'metric_name': s.metric_name,
                'metric_value': s.metric_value,
                'metadata': dict(s.metadata) if s.metadata else {},
            }
            for s in aggregate.summaries
        ],
        'cases': [
            {
                'id': c.id,
                'report_id': c.report_id,
                'test_case_id': c.test_case_id,
                'result_summary': dict(c.result_summary) if c.result_summary else {},
                'score': c.score,
            }
            for c in aggregate.cases
        ],
        'metric_stats': [
            {
                'id': m.id,
                'report_id': m.report_id,
                'metric_name': m.metric_name,
                'avg': m.avg,
                'min': m.min,
                'max': m.max,
                'std_dev': m.std_dev,
                'sample_count': m.sample_count,
            }
            for m in aggregate.metric_stats
        ],
        'raw_data': [
            {
                'id': r.id,
                'report_id': r.report_id,
                'data_type': r.data_type,
                'data': dict(r.data) if r.data else {},
            }
            for r in aggregate.raw_data
        ],
    }


# ---- 写操作 ----

@router.post('')
def create_report(req: CreateReportRequest):
    """创建报告（pending 状态）。

    请求体 JSON：
        task_id: int      关联任务 ID
        report_type: str  报告类型（默认 standard）
        config: dict      报告配置（可选）
    """
    try:
        command = CreateReportCommand(
            task_id=req.task_id,
            report_type=req.report_type,
            config=req.config,
        )
        report_id = ReportCommandHandler().handle_create(command)
        return {'success': True, 'message': 'ok', 'data': {'report_id': report_id}}
    except Exception as e:
        logger.exception("create_report failed")
        return {'success': False, 'message': str(e)}


@router.post('/generate')
def generate_report(req: GenerateReportRequest):
    """生成报告（pending -> generating -> completed/failed）。

    请求体 JSON：
        task_id: int      关联任务 ID
        report_type: str  报告类型（默认 standard）
    """
    try:
        command = GenerateReportCommand(
            task_id=req.task_id,
            report_type=req.report_type,
        )
        report_id = ReportCommandHandler().handle_generate(command)
        if report_id is None:
            return {'success': False, 'message': 'generate failed'}
        return {'success': True, 'message': 'ok', 'data': {'report_id': report_id}}
    except Exception as e:
        logger.exception("generate_report failed")
        return {'success': False, 'message': str(e)}


@router.put('/{report_id}/status')
def update_report_status(report_id: int, req: UpdateReportStatusRequest):
    """更新报告状态。

    路径参数：
        report_id: 报告 ID

    请求体 JSON：
        status: str  目标状态（pending/generating/completed/failed）
    """
    try:
        if not req.status:
            return {'success': False, 'message': 'status is required'}
        command = UpdateReportStatusCommand(
            report_id=report_id,
            status=req.status,
        )
        ReportCommandHandler().handle_update_status(command)
        return {'success': True, 'message': 'ok', 'data': {'report_id': report_id, 'status': req.status}}
    except Exception as e:
        logger.exception("update_report_status failed")
        return {'success': False, 'message': str(e)}


@router.delete('/{report_id}')
def delete_report(report_id: int):
    """删除报告（软删除）。

    路径参数：
        report_id: 报告 ID
    """
    try:
        command = DeleteReportCommand(report_id=report_id)
        deleted = ReportCommandHandler().handle_delete(command)
        if not deleted:
            raise HTTPException(status_code=404, detail='report not found')
        return {'success': True, 'message': 'ok', 'data': {'report_id': report_id, 'deleted': True}}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_report failed")
        return {'success': False, 'message': str(e)}


# ---- 读操作 ----

@router.get('')
def list_reports(status: Optional[str] = Query(None), page: int = Query(1), page_size: int = Query(20)):
    """分页列出报告。

    查询参数：
        status:     str  可选状态过滤
        page:       int  页码（默认 1）
        page_size:  int  每页数量（默认 20）
    """
    try:
        query = ListReportsQuery(
            status=status,
            page=page,
            page_size=page_size,
        )
        aggregates = ReportQueryHandler().handle_list(query)
        return {'success': True, 'message': 'ok', 'data': {
            'items': [_aggregate_to_dict(a) for a in aggregates],
            'page': query.page,
            'page_size': query.page_size,
        }}
    except Exception as e:
        logger.exception("list_reports failed")
        return {'success': False, 'message': str(e)}


@router.get('/{report_id}')
def get_report(report_id: int):
    """按 ID 获取报告（不含子实体集合）。

    路径参数：
        report_id: 报告 ID
    """
    try:
        query = GetReportQuery(report_id=report_id)
        aggregate = ReportQueryHandler().handle_get(query)
        if aggregate is None:
            raise HTTPException(status_code=404, detail='report not found')
        return {'success': True, 'message': 'ok', 'data': _aggregate_to_dict(aggregate)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_report failed")
        return {'success': False, 'message': str(e)}


@router.get('/by_task/{task_id}')
def get_report_by_task(task_id: int):
    """按任务 ID 获取最新报告。

    路径参数：
        task_id: 任务 ID
    """
    try:
        query = GetReportByTaskQuery(task_id=task_id)
        aggregate = ReportQueryHandler().handle_get_by_task(query)
        if aggregate is None:
            raise HTTPException(status_code=404, detail='report not found')
        return {'success': True, 'message': 'ok', 'data': _aggregate_to_dict(aggregate)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_report_by_task failed")
        return {'success': False, 'message': str(e)}


@router.get('/trend')
def get_trend_data(
    type: Optional[str] = Query(None),
    task_id: Optional[int] = Query(None),
    limit: int = Query(50),
):
    """获取报告趋势数据。

    按 created_at 升序返回报告列表，每条含成功率/时长及与前一条的变化量。

    查询参数：
        type:     str  可选报告类型过滤
        task_id:  int  可选任务 ID 过滤
        limit:    int  最多返回条数（默认 50）
    """
    try:
        query = GetTrendDataQuery(
            report_type=type,
            task_id=task_id,
            limit=limit,
        )
        trend_data = ReportQueryHandler().handle_get_trend(query)
        return {'success': True, 'message': 'ok', 'data': {'trend_data': trend_data}}
    except Exception as e:
        logger.exception("get_trend_data failed")
        return {'success': False, 'message': str(e)}


@router.get('/{report_id}/summary')
def get_report_summary(report_id: int):
    """获取报告摘要（含子实体集合）。

    路径参数：
        report_id: 报告 ID
    """
    try:
        query = GetReportSummaryQuery(report_id=report_id)
        aggregate = ReportQueryHandler().handle_get_summary(query)
        if aggregate is None:
            raise HTTPException(status_code=404, detail='report not found')
        return {'success': True, 'message': 'ok', 'data': _aggregate_to_dict(aggregate)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_report_summary failed")
        return {'success': False, 'message': str(e)}
