# -*- coding: utf-8 -*-
"""report_service gRPC servicer

ReportServicer: 报告 CRUD / 生成 / 查询（CreateReport / UpdateReport /
DeleteReport / BatchActionReports / ListReports / GetReportDetail /
GetReportByTask / GenerateReport / UpdateReportStatus）

继承 report_service_pb2_grpc.ReportConfigServiceServicer，
每个方法委托 application 层 handler。
"""
from __future__ import annotations

import logging
from contextlib import nullcontext
from typing import Any, Dict, List, Optional

from shared.proto import report_service_pb2 as report_pb
from shared.proto import report_service_pb2_grpc as report_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps, fold_business_code

from report_service.domain.request_budget import RequestBudget, budget_from_grpc_context

from report_service.application.commands.report_commands import (
    CreateReportCommand,
    DeleteReportCommand,
    GenerateReportCommand,
    UpdateReportCommand,
    UpdateReportStatusCommand,
)
from report_service.application.commands.benchmark_commands import (
    ComputeBenchmarkRankingCommand,
    CreateBenchmarkMetricMappingCommand,
    CreateBenchmarkReportCommand,
    CreateBenchmarkSourceCommand,
    ImportBenchmarkBaselinesCommand,
    UpdateBenchmarkMetricMappingCommand,
)
from report_service.application.handlers.report_handlers import (
    ReportCommandHandler,
    ReportQueryHandler,
)
from report_service.application.queries.benchmark_queries import (
    GetBenchmarkRankingQuery,
    GetBenchmarkRankingSubjectsQuery,
    GetBenchmarkReportQuery,
    ListBenchmarkBaselinesQuery,
    ListBenchmarkMetricMappingsQuery,
    ListBenchmarkReportsQuery,
    ListBenchmarkSourcesQuery,
)
from report_service.application.queries.report_queries import (
    GetReportByTaskQuery,
    GetReportProgressQuery,
    GetReportQuery,
    GetReportSummaryQuery,
    ListReportBriefsByTaskIdsQuery,
    ListReportsQuery,
    split_report_types,
)
from report_service.domain.entities import ReportAggregate
from report_service.domain.entities.benchmark import BaselineDraftEntry
from report_service.application.services.report_share_service import (
    report_share_service,
)
from report_service.application.services.report_task_name_enricher import (
    enrich_task_names,
)
from report_service.application.services.report_export_history_service import (
    report_export_history_service,
)

logger = logging.getLogger(__name__)

# 批量删除单次上限（对齐旧库 ReportBatchDeleteRequest max_length=100）
MAX_BATCH_DELETE = 100


def _budget_scope(context):
    """把 gRPC 调用的剩余时限注入请求预算（INT-1572 返工二轮）。

    报告链路由多个阶段共享网关的一次调用截止（默认 60s）：跨域用例取数若按固定
    整批截止收尾，会把后续的结果聚合顶过截止。这里把剩余时限记进请求上下文，
    ACL 按「剩余 - 预留」分配（见 domain/request_budget.py）。无 context（单测 /
    进程内调用）时返回空上下文，各阶段用配置的固定兜底值。
    """
    seconds = budget_from_grpc_context(context)
    return RequestBudget(seconds) if seconds is not None else nullcontext()


def _aggregate_to_dict(aggregate: Optional[ReportAggregate]) -> Optional[Dict[str, Any]]:
    """将 ReportAggregate 聚合根序列化为字典。

    Args:
        aggregate: 报告聚合根（可能为 None）

    Returns:
        包含报告元数据的字典；aggregate 为 None 时返回 None
    """
    if aggregate is None:
        return None
    config = dict(aggregate.config) if aggregate.config else {}
    # 报告名来自聚合根 name（PO.name 列），config.name 为历史约定兜底，
    # 提升为顶层字段供 task_service/api_gateway 等消费方直接读取
    return {
        'id': aggregate.id,
        'task_id': aggregate.task_id,
        'name': aggregate.name or config.get('name') or '',
        'description': config.get('description') or '',
        # 对外契约字段名与 PO 列名保持一致（report_type 为聚合根内部命名）
        'type': aggregate.report_type,
        'report_type': aggregate.report_type,
        'status': aggregate.status,
        'config': config,
        # 文本结论（update 落 config，读取时回传，供前端编辑回显）
        'analysis': config.get('analysis') or '',
        'conclusion': config.get('conclusion') or config.get('analysis') or '',
        'created_at': str(aggregate.created_at) if aggregate.created_at is not None else None,
        # INT-423 数据可见性：透出 visibility/owner，供网关路由级 owner 校验与前端徽标
        'visibility': getattr(aggregate, 'visibility', None) or 'shared',
        'created_by_user_id': getattr(aggregate, 'created_by_user_id', None),
        # INT-141：回收站展示字段
        'deleted': bool(getattr(aggregate, 'deleted', False)),
        'deleted_at': str(aggregate.deleted_at) if getattr(aggregate, 'deleted_at', None) else None,
        'deleted_by_user_id': getattr(aggregate, 'deleted_by_user_id', None),
        # 详情接口输出完整摘要（all_metrics/case_categories/all_case_tags/...），
        # 列表等场景无 full_summary 时回退为扁平统计（对齐 api_gateway ReportListItem.summary）
        'summary': aggregate.full_summary if aggregate.full_summary else aggregate.flat_summary(),
        # 子实体集合（仅 summary 查询时填充）
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


class ReportServicer(report_grpc.ReportConfigServiceServicer):
    """报告服务 gRPC servicer

    继承 report_service_pb2_grpc.ReportConfigServiceServicer，
    每个 RPC 方法委托 application 层：
    - 写操作 -> ReportCommandHandler
    - 读操作 -> ReportQueryHandler
    """

    def __init__(self) -> None:
        """初始化 servicer，延迟创建 command/query handler。"""
        self._command_handler: Optional[ReportCommandHandler] = None
        self._query_handler: Optional[ReportQueryHandler] = None

    @property
    def command_handler(self) -> ReportCommandHandler:
        """延迟初始化命令处理器。"""
        if self._command_handler is None:
            self._command_handler = ReportCommandHandler()
        return self._command_handler

    @property
    def query_handler(self) -> ReportQueryHandler:
        """延迟初始化查询处理器。"""
        if self._query_handler is None:
            self._query_handler = ReportQueryHandler()
        return self._query_handler

    @staticmethod
    def _resp(success: bool, message: str = '', data: Any = None, code: int = 0) -> report_pb.ReportConfigResponse:
        """构造统一响应。

        code: HTTP 语义业务码（INT-971：GetSharedReport 错误 404/410/401/403；0 = 200）。
        """
        # INT-566 P1-5：失败响应把业务码折进 data JSON，网关代理按 data.code 提升映射 HTTP 状态
        if not success:
            data = fold_business_code(data, code)
        return report_pb.ReportConfigResponse(
            success=success,
            message=message,
            data=_dumps(data) if data is not None else '',
            code=code,
        )

    # ---- 写操作 ----

    def CreateReport(self, request, context=None):
        """创建报告（pending 状态）。

        请求字段（proto CreateReportRequest）：
            data: str  JSON：{task_id, report_type, config, name, ...}

        Returns:
            ReportConfigResponse
        """
        try:
            data = _loads(getattr(request, 'data', ''), {}) or {}
            command = CreateReportCommand(
                task_id=data.get('task_id'),
                report_type=data.get('report_type') or 'standard',
                config=data.get('config') or {},
                visibility=data.get('visibility'),
            )
            report_id = self.command_handler.handle_create(command)
            return self._resp(True, 'ok', {'report_id': report_id})
        except Exception as e:
            logger.exception("CreateReport failed")
            return self._resp(False, str(e), {})

    def UpdateReport(self, request, context=None):
        """更新报告字段。

        请求字段（proto UpdateReportRequest）：
            report_id: int  报告 ID
            data: str      JSON：更新字段（name/title/description/
                           analysis/conclusion/status/summary）

        对齐旧库 PUT /reports/{id}：主表字段 + 摘要快照一并落库。
        """
        try:
            data = _loads(getattr(request, 'data', ''), {}) or {}
            # name/title、analysis/conclusion 分别取先提供者（对齐旧库 pick 语义）
            name = data['name'] if 'name' in data else data.get('title')
            analysis = data['analysis'] if 'analysis' in data else data.get('conclusion')
            command = UpdateReportCommand(
                report_id=getattr(request, 'report_id'),
                name=name,
                description=data.get('description'),
                analysis=analysis,
                status=data.get('status'),
                summary=data.get('summary'),
                # INT-466：可见性切换（data 携带 visibility 时更新；None 不更新）
                visibility=data.get('visibility'),
            )
            updated = self.command_handler.handle_update(command)
            return self._resp(updated, 'ok' if updated else 'report not found', {
                'report_id': getattr(request, 'report_id'),
                'updated': updated,
            })
        except Exception as e:
            logger.exception("UpdateReport failed")
            return self._resp(False, str(e), {})

    def DeleteReport(self, request, context=None):
        """删除报告（软删除）。

        请求字段（proto DeleteReportRequest）：
            report_id: int   报告 ID
            hard_delete: bool 是否硬删除
        """
        try:
            command = DeleteReportCommand(
                report_id=getattr(request, 'report_id'),
            )
            # 先查询报告关联的 task_id，用于重新生成
            # 注意：需在删除前查询，软删后 get_by_id 会过滤已删除记录
            task_id = None
            try:
                aggregate = self.query_handler.handle_get(GetReportQuery(report_id=command.report_id))
                if aggregate:
                    task_id = aggregate.task_id
            except Exception:
                pass
            deleted = self.command_handler.handle_delete(command)
            return self._resp(
                deleted,
                'ok' if deleted else 'report not found',
                {'report_id': command.report_id, 'deleted': deleted, 'task_id': task_id},
            )
        except Exception as e:
            logger.exception("DeleteReport failed")
            return self._resp(False, str(e), {})

    def BatchActionReports(self, request, context=None):
        """批量删除报告。

        请求字段（proto BatchActionReportsRequest）：
            data: str  JSON：{ids: [int]（兼容历史 report_ids 键）,
                              action: 'delete', hard_delete: bool}

        对齐旧库 POST /reports/batch-delete：
        - ids 字段与网关对齐（历史 report_ids 键兼容读取）
        - hard_delete=True 硬删除（含子表级联），否则软删除
        - 单次上限 100 条
        - 删 0 条不得返回成功（守卫：字段不匹配/ID 不存在时不得假成功）
        """
        try:
            data = _loads(getattr(request, 'data', ''), {}) or {}
            report_ids = data.get('ids')
            if report_ids is None:
                report_ids = data.get('report_ids') or []
            action = data.get('action') or 'delete'
            if action != 'delete':
                return self._resp(False, f'不支持的操作: {action}', {})
            if not report_ids or not isinstance(report_ids, list):
                return self._resp(False, 'ids 列表不能为空', {})
            if len(report_ids) > MAX_BATCH_DELETE:
                return self._resp(False, '单次最多删除100个报告', {})

            hard = bool(data.get('hard_delete', False))
            # INT-423 批量逐行过滤：私有非 owner 行跳过（镜像 purge filter 口径，
            # 不整批放行）；被跳过行按 deleted=False 记入 items
            from shared.infrastructure.user_context import (
                get_current_user_id,
                get_current_user_is_admin,
            )
            from shared.infrastructure.visibility_filter import filter_visible_owners
            visible_ids = set(filter_visible_owners(
                self.query_handler.repository.list_report_visibility_rows(report_ids),
                get_current_user_id(),
                get_current_user_is_admin(),
            ))
            results = []
            for rid in report_ids:
                if rid not in visible_ids:
                    results.append({'report_id': rid, 'deleted': False})
                    continue
                command = DeleteReportCommand(report_id=rid, hard=hard)
                ok = self.command_handler.handle_delete(command)
                results.append({'report_id': rid, 'deleted': ok})
            deleted_count = sum(1 for r in results if r['deleted'])
            if deleted_count == 0:
                return self._resp(False, '未找到指定的测试报告，无需删除', {
                    'deleted_count': 0,
                    'items': results,
                })
            return self._resp(True, f'成功删除 {deleted_count} 个测试报告', {
                'deleted_count': deleted_count,
                'items': results,
            })
        except Exception as e:
            logger.exception("BatchActionReports failed")
            return self._resp(False, str(e), {})

    def GenerateReport(self, request, context=None):
        """生成报告（pending -> generating -> completed/failed）。

        请求字段（proto GenerateReportRequest）：
            task_id: int      关联任务 ID
            report_type: str  报告类型
            data: str         JSON：额外参数
        """
        try:
            command = GenerateReportCommand(
                task_id=getattr(request, 'task_id'),
                report_type=getattr(request, 'report_type', None) or 'standard',
            )
            report_id = self.command_handler.handle_generate(command)
            return self._resp(
                report_id is not None,
                'ok' if report_id is not None else 'generate failed',
                {'report_id': report_id},
            )
        except Exception as e:
            logger.exception("GenerateReport failed")
            return self._resp(False, str(e), {})

    def GenerateTaskReport(self, request, context=None):
        """生成任务报告。"""
        try:
            result = self.command_handler.handle_generate_task_report(
                task_id=getattr(request, 'task_id'),
                name=getattr(request, 'name', None) or None,
                description=getattr(request, 'description', None) or None,
            )
            return self._resp(
                result.get('success', False),
                result.get('message', ''),
                result.get('data'),
            )
        except Exception as e:
            logger.exception("GenerateTaskReport failed")
            return self._resp(False, str(e), {})

    def GenerateCompareReport(self, request, context=None):
        """生成对比报告。"""
        try:
            data = _loads(getattr(request, 'data', ''), {}) or {}
            with _budget_scope(context):
                result = self.command_handler.handle_generate_compare_report(
                    task_ids=data.get('task_ids', []),
                    name=data.get('name'),
                    description=data.get('description'),
                )
            return self._resp(
                result.get('success', False),
                result.get('message', ''),
                result.get('data'),
            )
        except Exception as e:
            logger.exception("GenerateCompareReport failed")
            return self._resp(False, str(e), {})

    def GenerateSecondaryCompareReport(self, request, context=None):
        """生成二次对比报告。"""
        try:
            data = _loads(getattr(request, 'data', ''), {}) or {}
            with _budget_scope(context):
                result = self.command_handler.handle_generate_secondary_compare_report(
                    report_ids=data.get('report_ids', []),
                    description=data.get('description'),
                )
            return self._resp(
                result.get('success', False),
                result.get('message', ''),
                result.get('data'),
            )
        except Exception as e:
            logger.exception("GenerateSecondaryCompareReport failed")
            return self._resp(False, str(e), {})

    def UpdateReportStatus(self, request, context=None):
        """更新报告状态（状态流转）。

        请求字段（proto UpdateReportStatusRequest）：
            report_id: int  报告 ID
            status: str     目标状态
        """
        try:
            command = UpdateReportStatusCommand(
                report_id=getattr(request, 'report_id'),
                status=getattr(request, 'status', None) or 'pending',
            )
            self.command_handler.handle_update_status(command)
            return self._resp(True, 'ok', {
                'report_id': command.report_id,
                'status': command.status,
            })
        except Exception as e:
            logger.exception("UpdateReportStatus failed")
            return self._resp(False, str(e), {})

    # ---- 读操作 ----

    def GetReportDetail(self, request, context=None):
        """按 ID 查询报告详情（不含子实体集合）。

        请求字段（proto GetReportDetailRequest）：
            report_id: int  报告 ID
        """
        try:
            query = GetReportQuery(
                report_id=getattr(request, 'report_id'),
            )
            aggregate = self.query_handler.handle_get(query)
            data = _aggregate_to_dict(aggregate)
            # INT-1776：任务名补名（单条一次 RPC；失败 / 超时降级为 ''）
            if data is not None:
                enrich_task_names([data])
            return self._resp(
                aggregate is not None,
                'ok' if aggregate is not None else 'report not found',
                data,
                # INT-566 P1-5：不存在/私有非 owner → 业务码 404（防探测口径）
                code=0 if aggregate is not None else 404,
            )
        except Exception as e:
            logger.exception("GetReportDetail failed")
            return self._resp(False, str(e), None)

    def GetReportByTask(self, request, context=None):
        """按任务 ID 查询最新报告。

        请求字段（proto GetReportByTaskRequest）：
            task_id: int  任务 ID
        """
        try:
            query = GetReportByTaskQuery(
                task_id=getattr(request, 'task_id'),
            )
            aggregate = self.query_handler.handle_get_by_task(query)
            data = _aggregate_to_dict(aggregate)
            # INT-1776：任务名补名（单条一次 RPC；失败 / 超时降级为 ''）
            if data is not None:
                enrich_task_names([data])
            return self._resp(
                aggregate is not None,
                'ok' if aggregate is not None else 'report not found',
                data,
            )
        except Exception as e:
            logger.exception("GetReportByTask failed")
            return self._resp(False, str(e), None)

    def GetReportProgress(self, request, context=None):
        """查询报告生成进度。

        请求字段（proto GetReportProgressRequest）：
            report_id: int  报告 ID
        """
        try:
            query = GetReportProgressQuery(
                report_id=getattr(request, 'report_id'),
            )
            data = self.query_handler.handle_get_report_progress(query)
            return self._resp(
                data is not None,
                'ok' if data is not None else 'report not found',
                data,
            )
        except Exception as e:
            logger.exception("GetReportProgress failed")
            return self._resp(False, str(e), None)

    def ListReportsByTaskIds(self, request, context=None):
        """页级批量列出多个任务的报告摘要（INT-1462：任务列表 N+1 消解）。

        请求字段（proto ListReportsByTaskIdsRequest）：
            task_ids: repeated int32  页面任务 ID 集合
            per_task_limit: int32     每个任务最多返回条数（0 = 默认 100）

        响应 data：{'items_by_task': {'<task_id>': [{id,name,status,type,created_at}, ...]}}
        """
        try:
            query = ListReportBriefsByTaskIdsQuery(
                task_ids=[int(t) for t in getattr(request, 'task_ids', [])],
                per_task_limit=getattr(request, 'per_task_limit', 0) or 100,
            )
            if not query.task_ids:
                return self._resp(True, 'ok', {'items_by_task': {}})
            briefs = self.query_handler.handle_list_report_briefs_by_task_ids(query)
            return self._resp(True, 'ok', {
                'items_by_task': {str(tid): rows for tid, rows in briefs.items()},
            })
        except Exception as e:
            logger.exception("ListReportsByTaskIds failed")
            return self._resp(False, str(e), None)

    def ListReports(self, request, context=None):
        """分页列出报告。

        请求字段（proto ListReportsRequest）：
            report_type: str    可选类型过滤（多类型逗号分隔，INT-280）
            status: str         可选状态过滤
            task_id: int        可选任务过滤
            algorithm_type: str 可选算法类型过滤
            page: int           页码（从 1 开始）
            per_page: int       每页数量
            search: str         可选搜索关键字
            start_date: str     可选开始日期
            end_date: str       可选结束日期
            favorite: bool      INT-141 仅当前用户收藏（x-user-id metadata）
            deleted: bool       INT-141 仅回收站软删除项
        """
        try:
            from shared.infrastructure.user_context import user_id_from_context
            query = ListReportsQuery(
                status=getattr(request, 'status', None) or None,
                report_types=split_report_types(getattr(request, 'report_type', '') or ''),
                task_id=getattr(request, 'task_id', 0) or None,
                page=getattr(request, 'page', None) or 1,
                page_size=getattr(request, 'per_page', None) or 20,
                favorite=getattr(request, 'favorite', False),
                deleted=getattr(request, 'deleted', False),
                user_id=user_id_from_context(context),
            )
            aggregates: List[ReportAggregate] = self.query_handler.handle_list(query)
            # INT-141：当前用户收藏标记（user_id 已随 query 从 metadata 读取）
            fav_ids = set()
            if query.user_id:
                from report_service.application.favorite_trash_service import (
                    report_favorite_trash_service,
                )
                fav = report_favorite_trash_service.list_favorite_ids(query.user_id)
                if fav.get('success'):
                    fav_ids = {str(i) for i in (fav.get('data') or {}).get('ids', [])}
            items = []
            for aggregate in aggregates:
                item = _aggregate_to_dict(aggregate)
                if item is not None:
                    item['is_favorite'] = str(item.get('id')) in fav_ids
                    items.append(item)
            # INT-1776：整页一次批量补任务名（去重后单次 RPC；失败 / 超时降级为 ''）
            enrich_task_names(items)
            # INT-297：分页信封统一为 {items, page, pages, per_page, total}
            total = self.query_handler.handle_count_reports(query)
            return self._resp(True, 'ok', {
                'items': items,
                'page': query.page,
                'per_page': query.page_size,
                'total': total,
                'pages': (total + query.page_size - 1) // query.page_size if query.page_size else 1,
            })
        except Exception as e:
            logger.exception("ListReports failed")
            return self._resp(False, str(e), {'items': []})

    def CountReports(self, request, context=None):
        """按 ListReports 同一套过滤条件计数（INT-280：HistoryReports Tab 计数服务端聚合）。

        复用 ListReportsRequest：仅 report_type（可逗号分隔多类型）/status/
        favorite/deleted 过滤生效，分页与搜索字段忽略。
        响应 data: {'total': N}
        """
        try:
            from shared.infrastructure.user_context import user_id_from_context
            query = ListReportsQuery(
                status=getattr(request, 'status', None) or None,
                report_types=split_report_types(getattr(request, 'report_type', '') or ''),
                favorite=getattr(request, 'favorite', False),
                deleted=getattr(request, 'deleted', False),
                user_id=user_id_from_context(context),
            )
            total = self.query_handler.handle_count_reports(query)
            return self._resp(True, 'ok', {'total': total})
        except Exception as e:
            logger.exception("CountReports failed")
            return self._resp(False, str(e), {'total': 0})

    def CountReportsByTabs(self, request, context=None):
        """四个视图 Tab 一次聚合计数（INT-1463：单条条件聚合 SQL）。

        Tab 口径由服务端持有（all/draft/published/comparison），可见性/软删过滤
        沿用当前用户上下文与活跃口径；响应 data: {all, draft, published, comparison}。
        """
        try:
            counts = self.query_handler.handle_count_reports_by_tabs()
            return self._resp(True, 'ok', counts)
        except Exception as e:
            logger.exception("CountReportsByTabs failed")
            return self._resp(False, str(e), {'all': 0, 'draft': 0,
                                              'published': 0, 'comparison': 0})

    # ---- 收藏 / 回收站（INT-141）----

    def FavoriteReport(self, request, context=None):
        """收藏报告（幂等；user_id 从 x-user-id metadata 取）。"""
        try:
            from shared.infrastructure.user_context import get_current_user_id
            result = self.command_handler.handle_favorite_report(
                getattr(request, 'report_id'), user_id=get_current_user_id())
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'))
        except Exception as e:
            logger.exception("FavoriteReport failed")
            return self._resp(False, str(e), {})

    def UnfavoriteReport(self, request, context=None):
        """取消收藏报告（幂等）。"""
        try:
            from shared.infrastructure.user_context import get_current_user_id
            result = self.command_handler.handle_unfavorite_report(
                getattr(request, 'report_id'), user_id=get_current_user_id())
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'))
        except Exception as e:
            logger.exception("UnfavoriteReport failed")
            return self._resp(False, str(e), {})

    def ListFavoriteReportIds(self, request, context=None):
        """当前用户收藏的报告 ID 列表。"""
        try:
            from shared.infrastructure.user_context import (
                get_current_user_id, normalize_user_id,
            )
            user_id = normalize_user_id(getattr(request, 'user_id', 0)) or get_current_user_id()
            result = self.query_handler.handle_list_favorite_report_ids(user_id)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'))
        except Exception as e:
            logger.exception("ListFavoriteReportIds failed")
            return self._resp(False, str(e), {})

    def ListDeletedReports(self, request, context=None):
        """回收站报告列表（含删除人/删除时间）。"""
        try:
            result = self.query_handler.handle_list_deleted_reports(
                page=getattr(request, 'page', 1) or 1,
                per_page=getattr(request, 'per_page', 20) or 20,
                search=getattr(request, 'search', None) or None,
            )
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'))
        except Exception as e:
            logger.exception("ListDeletedReports failed")
            return self._resp(False, str(e), {})

    def RestoreReports(self, request, context=None):
        """恢复报告（单个+批量统一入口）。"""
        try:
            result = self.command_handler.handle_restore_reports(
                list(getattr(request, 'report_ids', [])))
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'))
        except Exception as e:
            logger.exception("RestoreReports failed")
            return self._resp(False, str(e), {})

    def PurgeReports(self, request, context=None):
        """彻底删除报告（物理删除；权限收敛在网关 admin/owner）。"""
        try:
            result = self.command_handler.handle_purge_reports(
                list(getattr(request, 'report_ids', [])))
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'))
        except Exception as e:
            logger.exception("PurgeReports failed")
            return self._resp(False, str(e), {})

    # ---- 报告用例查询 / 搜索 / 导出 / 平均值 / 日志下载 ----

    def GetReportCases(self, request, context=None):
        """查询报告用例列表。

        请求字段（proto GetReportCasesRequest）：
            report_id: int   报告 ID
            data: str        JSON: 查询参数（keyword/category/tags/page/per_page 等）
        """
        try:
            report_id = getattr(request, 'report_id', 0)
            params_dict = _loads(getattr(request, 'data', ''), {}) or {}
            data = self.query_handler.handle_get_report_cases(report_id, params_dict)
            return self._resp(True, 'ok', data)
        except Exception as e:
            logger.exception("GetReportCases failed")
            return self._resp(False, str(e), {'items': []})

    def SearchReportCases(self, request, context=None):
        """搜索报告用例。

        请求字段（proto SearchReportCasesRequest）：
            report_id: int   报告 ID
            data: str        JSON: 搜索参数（keyword/category/tags/include_untagged 等）
        """
        try:
            report_id = getattr(request, 'report_id', 0)
            params_dict = _loads(getattr(request, 'data', ''), {}) or {}
            data = self.query_handler.handle_search_report_cases(report_id, params_dict)
            return self._resp(True, 'ok', data)
        except Exception as e:
            logger.exception("SearchReportCases failed")
            return self._resp(False, str(e), {'items': []})

    def ExportReports(self, request, context=None):
        """导出报告（Excel/PDF/CSV/HTML）。

        请求字段（proto ExportReportsRequest）：
            data: str  JSON: {ids: [int], format: str}

        INT-1555：无论成败都登记一条导出历史（report_export_records），
        供「导出历史」页签回查；登记失败不影响导出结果。
        """
        try:
            data_in = _loads(getattr(request, 'data', ''), {}) or {}
            report_ids = data_in.get('ids') or []
            format_type = data_in.get('format') or 'csv'
        except Exception as e:
            logger.exception("ExportReports failed")
            return self._resp(False, str(e), {})

        try:
            data = self.query_handler.handle_export_reports(report_ids, format_type)
            if not data.get('content_base64'):
                report_export_history_service.record(
                    report_ids, format_type,
                    {**data, 'success': False,
                     'message': data.get('message') or 'export failed'})
                return self._resp(False, data.get('message', 'export failed'), data)
            report_export_history_service.record(
                report_ids, format_type, {**data, 'success': True})
            return self._resp(True, 'ok', data)
        except Exception as e:
            logger.exception("ExportReports failed")
            report_export_history_service.record(
                report_ids, format_type, {'success': False, 'message': str(e)})
            return self._resp(False, str(e), {})

    def ListExportHistory(self, request, context=None):
        """查询报告导出历史（INT-1555，按导出时间倒序分页）。

        请求字段（proto ListExportHistoryRequest）：
            data: str  JSON: {page, per_page}
        返回：{items: [{id, scope, format, created_at, status, error, report_ids}],
              total, page, per_page}
        """
        try:
            params_dict = _loads(getattr(request, 'data', ''), {}) or {}
            data = report_export_history_service.list_history(params_dict)
            return self._resp(True, 'ok', data)
        except Exception as e:
            logger.exception("ListExportHistory failed")
            return self._resp(False, str(e), {'items': [], 'total': 0})

    def GetCaseAverages(self, request, context=None):
        """查询用例平均值（按分组和标签）。

        请求字段（proto GetCaseAveragesRequest）：
            data: str  JSON: {task_id, category, tags, categories, include_untagged}
        """
        try:
            params_dict = _loads(getattr(request, 'data', ''), {}) or {}
            with _budget_scope(context):
                data = self.query_handler.handle_get_case_averages(params_dict)
            if data.get('success') is False:
                return self._resp(False, data.get('message', 'failed'), data)
            return self._resp(True, 'ok', data)
        except Exception as e:
            logger.exception("GetCaseAverages failed")
            return self._resp(False, str(e), {})

    def GetStatistics(self, request, context=None):
        """报告统计分析（GET /reports/statistics，INT-791）。

        请求字段（proto GetStatisticsRequest）：
            data: str  JSON: {dimension, start_time, end_time, algorithm_type}
        """
        try:
            params_dict = _loads(getattr(request, 'data', ''), {}) or {}
            data = self.query_handler.handle_get_statistics(params_dict)
            if data.get('success') is False:
                return self._resp(False, data.get('message', 'failed'), data)
            return self._resp(True, 'ok', data)
        except Exception as e:
            logger.exception("GetStatistics failed")
            return self._resp(False, str(e), {})

    def GetStatisticsTrend(self, request, context=None):
        """趋势分析（GET /reports/statistics/trend，INT-791）。

        请求字段（proto GetStatisticsTrendRequest）：
            data: str  JSON: {trend_type, metric, start_time, end_time}
        """
        try:
            params_dict = _loads(getattr(request, 'data', ''), {}) or {}
            data = self.query_handler.handle_get_statistics_trend(params_dict)
            if data.get('success') is False:
                return self._resp(False, data.get('message', 'failed'), data)
            return self._resp(True, 'ok', data)
        except Exception as e:
            logger.exception("GetStatisticsTrend failed")
            return self._resp(False, str(e), {})

    def GenerateStatisticsReport(self, request, context=None):
        """统计分析报表生成（POST /reports/statistics/report，INT-791）。

        请求字段（proto GenerateStatisticsReportRequest）：
            data: str  JSON: {report_type, content, format, time_range}
        """
        try:
            params_dict = _loads(getattr(request, 'data', ''), {}) or {}
            data = self.query_handler.handle_generate_statistics_report(params_dict)
            if not data.get('content_base64'):
                return self._resp(False, data.get('message', 'generate failed'), data)
            return self._resp(True, 'ok', data)
        except Exception as e:
            logger.exception("GenerateStatisticsReport failed")
            return self._resp(False, str(e), {})

    def DownloadCaseLogs(self, request, context=None):
        """下载用例日志（ZIP）。

        请求字段（proto DownloadCaseLogsRequest）：
            report_id: int   报告 ID
            case_id: str     用例 ID
            files: repeated string  可选，逻辑文件名筛选（缺省 = 整包，INT-1062）

        INT-1116 响应语义：成功载荷为 {filename, download_url, size, mime_type,
        mode: 'presigned'}（OSS 预签名 URL，整包不过 gRPC）或 {filename,
        content_base64, size, mime_type, mode: 'fallback'}（本地降级字节流回退）。
        """
        try:
            report_id = getattr(request, 'report_id', 0)
            case_id = getattr(request, 'case_id', '')
            files = list(getattr(request, 'files', []) or [])
            data = self.query_handler.handle_download_case_logs(
                report_id, case_id, files or None)
            if not data.get('content_base64') and not data.get('download_url'):
                return self._resp(False, data.get('message', 'download failed'),
                                  data, code=data.get('code', 0))
            return self._resp(True, 'ok', data)
        except Exception as e:
            logger.exception("DownloadCaseLogs failed")
            return self._resp(False, str(e), {})

    def ListCaseLogs(self, request, context=None):
        """查询用例日志文件列表（INT-1062）。

        请求字段（proto ListCaseLogsRequest）：
            report_id: int   报告 ID
            case_id: str     用例 ID
        返回：{items: [{name, size, updated_at?}]}
        """
        try:
            report_id = getattr(request, 'report_id', 0)
            case_id = getattr(request, 'case_id', '')
            data = self.query_handler.handle_list_case_logs(report_id, case_id)
            if data.get('success') is False:
                return self._resp(False, data.get('message', '查询日志文件列表失败'),
                                  data, code=data.get('code', 0))
            return self._resp(True, 'ok', data)
        except Exception as e:
            logger.exception("ListCaseLogs failed")
            return self._resp(False, str(e), {})

    def BuildReferenceParams(self, request, context=None):
        """构建参考参数（供 api_gateway task_query_service 调用）。

        请求字段（proto BuildReferenceParamsRequest）：
            data: str  JSON: {case_info: dict, case_results: list, test_type: str}
        """
        try:
            params = _loads(request.data, {}) or {}
            case_info = params.get('case_info', {})
            case_results = params.get('case_results', [])
            test_type = params.get('test_type', 'api')
            ref_params = self.query_handler.handle_build_reference_params(
                case_info, case_results, test_type
            )
            return self._resp(True, 'ok', ref_params)
        except Exception as e:
            logger.exception("BuildReferenceParams failed")
            return self._resp(False, str(e), {})

    # ==================== 任务数据导入导出（INT-25） ====================
    # 注：追加在类定义尾部，与上方方法同属 ReportServicer

    def ExportReportsForTasks(self, request, context=None):
        """按 task_id 列表导出报告 7 表只读行（数据导入导出用）。"""
        try:
            task_ids = _loads(request.task_ids, [])
            from report_service.application.report_transfer_service import (
                report_transfer_service,
            )
            result = report_transfer_service.export_reports_for_tasks(task_ids)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'))
        except Exception as e:
            logger.exception("ExportReportsForTasks failed")
            return self._resp(False, str(e), {})

    def ImportReports(self, request, context=None):
        """导入报告 7 表（单事务 + 主键冲突剥离 + 外键重映射）。"""
        try:
            data = _loads(request.data, {}) or {}
            from report_service.application.report_transfer_service import (
                report_transfer_service,
            )
            result = report_transfer_service.import_reports(
                data.get('tables') or {},
                data.get('task_id_mapping') or {},
                data.get('batch_id') or '')
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'))
        except Exception as e:
            logger.exception("ImportReports failed")
            return self._resp(False, str(e), {})

    def RollbackReportImport(self, request, context=None):
        """回滚报告导入批次（按批次登记主键删除）。"""
        try:
            from report_service.application.report_transfer_service import (
                report_transfer_service,
            )
            result = report_transfer_service.rollback_report_import(request.batch_id)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'))
        except Exception as e:
            logger.exception("RollbackReportImport failed")
            return self._resp(False, str(e), {})

    # ==================== 报告分享（INT-971） ====================

    def CreateReportShare(self, request, context=None):
        """创建报告分享链接。

        请求字段（proto CreateReportShareRequest）：
            data: str  JSON：{report_id, access, expiry, expires_at?, password?,
                             recipients（网关已解析的 [{user_id, label}] 列表）}
        """
        try:
            data = _loads(getattr(request, 'data', ''), {}) or {}
            result = report_share_service.create_share(data)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), code=result.get('code', 0))
        except Exception as e:
            logger.exception("CreateReportShare failed")
            return self._resp(False, str(e), {}, 500)

    def ListReportShares(self, request, context=None):
        """报告分享列表（分享管理与统计展示，按 created_at 倒序）。

        请求字段（proto ListReportSharesRequest）：
            data: str  JSON：{report_id}
        """
        try:
            data = _loads(getattr(request, 'data', ''), {}) or {}
            result = report_share_service.list_shares(data.get('report_id'))
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), code=result.get('code', 0))
        except Exception as e:
            logger.exception("ListReportShares failed")
            return self._resp(False, str(e), {}, 500)

    def RevokeReportShare(self, request, context=None):
        """撤销报告分享（软撤销，幂等：已撤销再次撤销仍 200）。

        请求字段（proto RevokeReportShareRequest）：
            data: str  JSON：{report_id, token}
        """
        try:
            data = _loads(getattr(request, 'data', ''), {}) or {}
            result = report_share_service.revoke_share(
                data.get('report_id'), data.get('token'))
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), code=result.get('code', 0))
        except Exception as e:
            logger.exception("RevokeReportShare failed")
            return self._resp(False, str(e), {}, 500)

    def GetSharedReport(self, request, context=None):
        """公开读取分享（token 自校验 + 密码 + 访问口径；200 时递增 visits）。

        请求字段（proto GetSharedReportRequest）：
            data: str  JSON：{token, password?, user_id}
            错误经 code 透出 404/410/401/403（网关映射 HTTP 状态码）。
        """
        try:
            data = _loads(getattr(request, 'data', ''), {}) or {}
            result = report_share_service.get_shared_report(
                data.get('token'),
                data.get('password'),
                data.get('user_id'),
            )
            if not result.get('success'):
                return self._resp(False, result.get('message', '读取分享失败'),
                                  result.get('data'), code=result.get('code', 404))
            report_id = (result.get('data') or {}).get('report_id')
            # INT-1043 F1：token 校验通过即 owner 显式授权，跳过行级可见性过滤
            # 直取未删报告（授权不因 visibility 收回；私有报告经分享链接匿名可读）
            aggregate = self.query_handler.handle_get_shared(report_id)
            if aggregate is None:
                return self._resp(False, '报告不存在或已删除', {'code': 404}, code=404)
            return self._resp(True, 'ok', _aggregate_to_dict(aggregate))
        except Exception as e:
            logger.exception("GetSharedReport failed")
            return self._resp(False, str(e), None, 500)


class BenchmarkServicer:
    """Benchmark 排行 gRPC Servicer（D1 双轨排行）。

    每个方法委托 application 层 BenchmarkCommandHandler / BenchmarkQueryHandler
    （严格 CQRS：写侧命令刷新 ReadModel，读侧只读）。
    """

    def __init__(self):
        from report_service.application.handlers.benchmark_handlers import (
            BenchmarkCommandHandler,
            BenchmarkQueryHandler,
        )
        self.command_handler = BenchmarkCommandHandler()
        self.query_handler = BenchmarkQueryHandler()

    @staticmethod
    def _resp(success: bool, message: str = '', data: Any = None, code: int = 0) -> report_pb.BenchmarkResponse:
        return report_pb.BenchmarkResponse(
            success=success,
            message=message,
            data=_dumps(data) if data is not None else '',
            code=code,
        )

    # ==================== 写侧 ====================

    def ComputeBenchmarkRanking(self, request, context=None):
        """触发排行计算（合并双轨 → 映射 → 6 算法 → ReadModel 刷新 + 审计）。"""
        try:
            params = _loads(request.data, {}) or {}
            command = ComputeBenchmarkRankingCommand(
                suite=(params.get('suite') or '').strip() or None,
                category=(params.get('category') or '').strip() or None,
                source=(params.get('source') or '').strip() or None,
                operator=params.get('operator') or '',
            )
            result = self.command_handler.handle_compute_ranking(command)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("ComputeBenchmarkRanking failed")
            return self._resp(False, str(e), {}, 500)

    def CreateBenchmarkSource(self, request, context=None):
        """创建外部基线数据源。"""
        try:
            params = _loads(request.data, {}) or {}
            command = CreateBenchmarkSourceCommand(
                name=params.get('name') or '',
                provider=params.get('provider') or '',
                source_type=params.get('source_type') or params.get('sourceType') or 'manual',
                url=params.get('url') or '',
                version=params.get('version') or '',
                description=params.get('description') or '',
                created_by=params.get('created_by') or params.get('createdBy') or '',
            )
            result = self.command_handler.handle_create_source(command)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("CreateBenchmarkSource failed")
            return self._resp(False, str(e), {}, 500)

    def ImportBenchmarkBaselines(self, request, context=None):
        """批量导入外部基线（导入即不可变快照新版本，重复内容幂等）。"""
        try:
            params = _loads(request.data, {}) or {}
            entries_data = params.get('entries') or []
            entries = [
                BaselineDraftEntry(
                    model_name=e.get('model_name') or e.get('modelName') or '',
                    metric_code=e.get('metric_code') or e.get('metricCode') or '',
                    value=e.get('value'),
                    vendor=e.get('vendor') or '',
                    metric_name=e.get('metric_name') or e.get('metricName') or '',
                    unit=e.get('unit') or '',
                    direction=e.get('direction') or '',
                    scenario_tags=e.get('scenario_tags') or e.get('scenarioTags') or [],
                    sample_size=e.get('sample_size', e.get('sampleSize')),
                    metric_date=e.get('metric_date') or e.get('metricDate') or '',
                )
                for e in entries_data if isinstance(e, dict)
            ]
            command = ImportBenchmarkBaselinesCommand(
                source_id=params.get('source_id') or params.get('sourceId'),
                category=params.get('category') or '',
                entries=entries,
                published_by=params.get('published_by') or params.get('publishedBy') or '',
            )
            result = self.command_handler.handle_import_baselines(command)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("ImportBenchmarkBaselines failed")
            return self._resp(False, str(e), {}, 500)

    def CreateBenchmarkMetricMapping(self, request, context=None):
        """创建指标映射（写侧 + 审计；dimension_name 唯一）。"""
        try:
            params = _loads(request.data, {}) or {}
            command = CreateBenchmarkMetricMappingCommand(
                dimension_name=params.get('dimension_name') or params.get('dimensionName') or '',
                metric_code=params.get('metric_code') or params.get('metricCode') or '',
                metric_name=params.get('metric_name', params.get('metricName')) or '',
                unit=params.get('unit') or '',
                direction=params.get('direction') or '',
                scenario_tags=params.get('scenario_tags', params.get('scenarioTags')) or [],
                active=bool(params.get('active', True)),
            )
            result = self.command_handler.handle_create_metric_mapping(command)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("CreateBenchmarkMetricMapping failed")
            return self._resp(False, str(e), {}, 500)

    def UpdateBenchmarkMetricMapping(self, request, context=None):
        """更新指标映射（写侧 + 审计）。"""
        try:
            params = _loads(request.data, {}) or {}
            command = UpdateBenchmarkMetricMappingCommand(
                mapping_id=params.get('mapping_id') or params.get('mappingId'),
                metric_name=params.get('metric_name', params.get('metricName')),
                unit=params.get('unit'),
                direction=params.get('direction'),
                scenario_tags=params.get('scenario_tags', params.get('scenarioTags')),
                active=params.get('active'),
            )
            result = self.command_handler.handle_update_metric_mapping(command)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("UpdateBenchmarkMetricMapping failed")
            return self._resp(False, str(e), {}, 500)

    # ==================== 读侧 ====================

    def GetBenchmarkRanking(self, request, context=None):
        """查询排行（只读 ReadModel，无写副作用）。"""
        try:
            params = _loads(request.data, {}) or {}
            query = GetBenchmarkRankingQuery(
                suite=(params.get('suite') or '').strip() or None,
                category=(params.get('category') or '').strip() or None,
                metric_code=(params.get('metric_code') or params.get('metricCode') or '').strip() or None,
                source=(params.get('source') or '').strip() or None,
                published_task_id=params.get('published_task_id', params.get('publishedTaskId')),
                subject_name=(params.get('subject_name') or params.get('subjectName') or '').strip() or None,
            )
            result = self.query_handler.handle_get_ranking(query)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("GetBenchmarkRanking failed")
            return self._resp(False, str(e), {}, 500)

    def GetBenchmarkRankingSubjects(self, request, context=None):
        """查询参与排行的被测主体列表。"""
        try:
            params = _loads(request.data, {}) or {}
            query = GetBenchmarkRankingSubjectsQuery(
                suite=(params.get('suite') or '').strip() or None)
            result = self.query_handler.handle_get_ranking_subjects(query)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("GetBenchmarkRankingSubjects failed")
            return self._resp(False, str(e), {}, 500)

    def ListBenchmarkSources(self, request, context=None):
        """外部基线数据源列表。"""
        try:
            params = _loads(request.data, {}) or {}
            query = ListBenchmarkSourcesQuery(
                page=params.get('page', 1),
                per_page=params.get('per_page', params.get('perPage', 10)),
                source_type=(params.get('source_type') or params.get('sourceType') or '').strip() or None,
            )
            result = self.query_handler.handle_list_sources(query)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("ListBenchmarkSources failed")
            return self._resp(False, str(e), {}, 500)

    def ListBenchmarkBaselines(self, request, context=None):
        """外部基线条目列表（当前生效版本）。"""
        try:
            params = _loads(request.data, {}) or {}
            query = ListBenchmarkBaselinesQuery(
                category=(params.get('category') or '').strip() or None,
                metric_code=(params.get('metric_code') or params.get('metricCode') or '').strip() or None,
                source_id=params.get('source_id', params.get('sourceId')),
                page=params.get('page', 1),
                per_page=params.get('per_page', params.get('perPage', 20)),
            )
            result = self.query_handler.handle_list_baselines(query)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("ListBenchmarkBaselines failed")
            return self._resp(False, str(e), {}, 500)

    def ListBenchmarkMetricMappings(self, request, context=None):
        """指标映射列表（读侧）。"""
        try:
            params = _loads(request.data, {}) or {}
            query = ListBenchmarkMetricMappingsQuery(
                active_only=bool(params.get('active_only', params.get('activeOnly', False))))
            result = self.query_handler.handle_list_metric_mappings(query)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("ListBenchmarkMetricMappings failed")
            return self._resp(False, str(e), {}, 500)

    # ==================== Benchmark 报告发布（INT-481） ====================

    def CreateBenchmarkReport(self, request, context=None):
        """发布 Benchmark 报告（聚合排行快照 → 复用报告 7 表结构 → benchmark_reports 落库）。"""
        try:
            params = _loads(request.data, {}) or {}
            command = CreateBenchmarkReportCommand(
                task_id=params.get('task_id', params.get('taskId')),
                suite=params.get('suite') or '',
                category=params.get('category') or '',
                source=params.get('source') or '',
                algorithm_set=params.get('algorithm_set', params.get('algorithmSet')) or '',
                name=params.get('name') or '',
                description=params.get('description') or '',
                published_by=params.get('published_by', params.get('publishedBy')) or '',
            )
            result = self.command_handler.handle_create_report(command)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("CreateBenchmarkReport failed")
            return self._resp(False, str(e), {}, 500)

    def ListBenchmarkReports(self, request, context=None):
        """Benchmark 报告发布记录列表（读侧）。"""
        try:
            params = _loads(request.data, {}) or {}
            query = ListBenchmarkReportsQuery(
                suite=(params.get('suite') or '').strip() or None,
                category=(params.get('category') or '').strip() or None,
                source=(params.get('source') or '').strip() or None,
                task_id=params.get('task_id', params.get('taskId')),
                page=params.get('page', 1),
                per_page=params.get('per_page', params.get('perPage', 20)),
            )
            result = self.query_handler.handle_list_reports(query)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("ListBenchmarkReports failed")
            return self._resp(False, str(e), {}, 500)

    def GetBenchmarkReport(self, request, context=None):
        """Benchmark 报告发布记录详情（读侧，含排行快照）。"""
        try:
            params = _loads(request.data, {}) or {}
            query = GetBenchmarkReportQuery(
                report_id=params.get('report_id', params.get('reportId')))
            result = self.query_handler.handle_get_report(query)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("GetBenchmarkReport failed")
            return self._resp(False, str(e), {}, 500)


class StudioServicer(report_grpc.ReportStudioServiceServicer):
    """Report Studio 业务资产 gRPC Servicer（INT-673）。

    每个方法委托 application 层 ReportStudioCommandHandler /
    ReportStudioQueryHandler（严格 CQRS：写侧只写并自动落版本快照，
    读侧只读 ReadModel/事实表）。
    """

    def __init__(self):
        from report_service.application.handlers.report_studio_handlers import (
            ReportStudioCommandHandler,
            ReportStudioQueryHandler,
        )
        self.command_handler = ReportStudioCommandHandler()
        self.query_handler = ReportStudioQueryHandler()

    @staticmethod
    def _resp(success: bool, message: str = '', data: Any = None, code: int = 0) -> report_pb.StudioResponse:
        return report_pb.StudioResponse(
            success=success,
            message=message,
            data=_dumps(data) if data is not None else '',
            code=code,
        )

    # ---- 写侧 ----

    def CreateStudioDocument(self, request, context=None):
        """用现有 reportId 创建草稿（可绑定 agentSessionId）。"""
        try:
            data = _loads(request.data, {}) or {}
            result = self.command_handler.handle_create_document(data)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("CreateStudioDocument failed")
            return self._resp(False, str(e), {}, 500)

    def UpdateStudioDocument(self, request, context=None):
        """人工编辑（expected_version 乐观锁，冲突 409 + 差异）。"""
        try:
            data = _loads(request.data, {}) or {}
            result = self.command_handler.handle_update_document(data)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("UpdateStudioDocument failed")
            return self._resp(False, str(e), {}, 500)

    def RestoreStudioDocumentVersion(self, request, context=None):
        """选定历史版本恢复为新版本（不覆盖）。"""
        try:
            data = _loads(request.data, {}) or {}
            result = self.command_handler.handle_restore_version(data)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("RestoreStudioDocumentVersion failed")
            return self._resp(False, str(e), {}, 500)

    def CreateStudioExportJob(self, request, context=None):
        """固定文档版本 + 格式 + 主题，创建导出异步作业。"""
        try:
            data = _loads(request.data, {}) or {}
            result = self.command_handler.handle_create_export_job(data)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("CreateStudioExportJob failed")
            return self._resp(False, str(e), {}, 500)

    # ---- 读侧 ----

    def GetStudioDocument(self, request, context=None):
        """当前版本、Markdown、图表引用、ETag。"""
        try:
            data = _loads(request.data, {}) or {}
            result = self.query_handler.handle_get_document(data)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("GetStudioDocument failed")
            return self._resp(False, str(e), {}, 500)

    def ListStudioDocumentVersions(self, request, context=None):
        """不可变版本列表。"""
        try:
            data = _loads(request.data, {}) or {}
            result = self.query_handler.handle_list_versions(data)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("ListStudioDocumentVersions failed")
            return self._resp(False, str(e), {}, 500)

    def GetStudioChartData(self, request, context=None):
        """按当前报告数据 + ChartSpec 返回图表数据。"""
        try:
            data = _loads(request.data, {}) or {}
            result = self.query_handler.handle_get_chart_data(data)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("GetStudioChartData failed")
            return self._resp(False, str(e), {}, 500)

    def GetStudioExportJob(self, request, context=None):
        """作业状态轮询 + 下载引用。"""
        try:
            data = _loads(request.data, {}) or {}
            result = self.query_handler.handle_get_export_job(data)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("GetStudioExportJob failed")
            return self._resp(False, str(e), {}, 500)

    def DownloadStudioExport(self, request, context=None):
        """已完成产物鉴权下载。"""
        try:
            data = _loads(request.data, {}) or {}
            result = self.query_handler.handle_download_export(data)
            return self._resp(result.get('success', False), result.get('message', ''),
                              result.get('data'), result.get('code', 0))
        except Exception as e:
            logger.exception("DownloadStudioExport failed")
            return self._resp(False, str(e), {}, 500)
