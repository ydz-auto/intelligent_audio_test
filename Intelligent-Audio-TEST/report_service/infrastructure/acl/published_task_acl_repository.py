# -*- coding: utf-8 -*-
"""task_service.PublishedTaskConfigService 跨域 ACL 仓储 — gRPC 实现。

Benchmark 排行实测轨数据源：分页拉取 benchmark=true 且 status=published 的
已发布任务列表，按需取详情（含冻结报告快照）。

失败语义（设计文档 §10：排行计算失败保留上次排行结果）：瞬时失败自动重试
一次，仍失败则上抛，由排行计算整体失败并保留旧榜。禁止降级为空结果——
那会把"拉取失败"伪装成"无实测数据"，在共享组刷新时静默删除该主体排行行。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from report_service.domain.repositories.acl.published_task_acl_repository import (
    PublishedTaskAclRepository,
)
from shared.utils.grpc_client_helper import call_rpc

logger = logging.getLogger(__name__)

# 单页拉取量：服务端无 per_page 上限，500 足够一期 Benchmark 规模
_ACL_PAGE_SIZE = 500

# 瞬时失败重试次数（首次 + 重试 1 次）
_MAX_ATTEMPTS = 2


def _call_with_retry(operation: Callable[[], Any], what: str) -> Any:
    """执行 gRPC 操作，瞬时失败重试一次，仍失败上抛。"""
    last_exc: Exception = RuntimeError(f'{what} failed')
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return operation()
        except Exception as e:
            last_exc = e
            logger.warning('%s gRPC failed (attempt %s/%s): %s',
                           what, attempt, _MAX_ATTEMPTS, e)
    raise last_exc


class PublishedTaskAclRepositoryImpl(PublishedTaskAclRepository):
    """task_service.PublishedTaskConfigService 跨域只读查询 gRPC 实现。"""

    def list_benchmark_published_tasks(self) -> List[Dict[str, Any]]:
        from shared.clients.grpc_clients import get_published_task_config_service_stub
        from shared.proto import task_service_pb2 as task_pb

        def _fetch_page(page: int) -> Dict[str, Any]:
            def _op():
                stub = get_published_task_config_service_stub()
                return call_rpc(
                    stub, 'ListPublishedTasks',
                    task_pb.ListPublishedTasksRequest(
                        page=page, per_page=_ACL_PAGE_SIZE,
                        status='published', benchmark='true',
                    ),
                    default={}, raise_on_failure=True,
                ) or {}
            return _call_with_retry(_op, 'list_benchmark_published_tasks')

        items: List[Dict[str, Any]] = []
        page = 1
        while True:
            data = _fetch_page(page)
            page_items = data.get('items') or []
            items.extend(item for item in page_items if isinstance(item, dict))
            total = int(data.get('total') or 0)
            if not page_items or len(items) >= total:
                break
            page += 1
        return items

    def get_published_task_detail(self, published_task_id: int) -> Optional[Dict[str, Any]]:
        from shared.clients.grpc_clients import get_published_task_config_service_stub
        from shared.proto import task_service_pb2 as task_pb

        def _op():
            stub = get_published_task_config_service_stub()
            return call_rpc(
                stub, 'GetPublishedTaskDetail',
                task_pb.GetPublishedTaskDetailRequest(
                    published_task_id=int(published_task_id)),
                default={}, raise_on_failure=True,
            ) or {}

        data = _call_with_retry(_op, 'get_published_task_detail')
        # 响应到达但无有效内容 = 服务端明确的无数据（no_report 合法形态），
        # 仅传输/调用失败才在上抛
        return data if isinstance(data, dict) and data.get('id') else None
