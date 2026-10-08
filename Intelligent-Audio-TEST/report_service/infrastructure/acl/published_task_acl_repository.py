# -*- coding: utf-8 -*-
"""task_service.PublishedTaskConfigService 跨域 ACL 仓储 — gRPC 实现。

Benchmark 排行实测轨数据源：分页拉取 benchmark=true 且 status=published 的
已发布任务列表，按需取详情（含冻结报告快照）。失败降级为空结果并告警，
保证排行计算可重试。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from report_service.domain.repositories.acl.published_task_acl_repository import (
    PublishedTaskAclRepository,
)
from shared.utils.grpc_client_helper import call_rpc

logger = logging.getLogger(__name__)

# 单页拉取量：服务端无 per_page 上限，500 足够一期 Benchmark 规模
_ACL_PAGE_SIZE = 500


class PublishedTaskAclRepositoryImpl(PublishedTaskAclRepository):
    """task_service.PublishedTaskConfigService 跨域只读查询 gRPC 实现。"""

    def list_benchmark_published_tasks(self) -> List[Dict[str, Any]]:
        from shared.clients.grpc_clients import get_published_task_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        items: List[Dict[str, Any]] = []
        page = 1
        try:
            stub = get_published_task_config_service_stub()
            while True:
                data = call_rpc(
                    stub, 'ListPublishedTasks',
                    task_pb.ListPublishedTasksRequest(
                        page=page, per_page=_ACL_PAGE_SIZE,
                        status='published', benchmark='true',
                    ),
                    default={}, raise_on_failure=False,
                ) or {}
                page_items = data.get('items') or []
                items.extend(item for item in page_items if isinstance(item, dict))
                total = int(data.get('total') or 0)
                if not page_items or len(items) >= total:
                    break
                page += 1
            return items
        except Exception as e:
            logger.warning("list_benchmark_published_tasks gRPC failed: %s", e)
            return []

    def get_published_task_detail(self, published_task_id: int) -> Optional[Dict[str, Any]]:
        from shared.clients.grpc_clients import get_published_task_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        try:
            stub = get_published_task_config_service_stub()
            data = call_rpc(
                stub, 'GetPublishedTaskDetail',
                task_pb.GetPublishedTaskDetailRequest(
                    published_task_id=int(published_task_id)),
                default={}, raise_on_failure=False,
            ) or {}
            return data if isinstance(data, dict) and data.get('id') else None
        except Exception as e:
            logger.warning("get_published_task_detail gRPC failed: %s", e)
            return None
