# -*- coding: utf-8 -*-
"""任务合并关系 ACL 仓储 — gRPC 实现。"""
from __future__ import annotations

import logging
from typing import List

from report_service.domain.dto import TaskMergeRelationDTO
from report_service.domain.repositories.acl.task_merge_relation_acl_repository import (
    TaskMergeRelationAclRepository,
)
from shared.utils.dto_utils import dict_to_dto

logger = logging.getLogger(__name__)


def _attach(dto, payload):
    if dto is not None and payload is not None:
        try:
            dto.result_data = payload
        except Exception:
            pass
    return dto


class TaskMergeRelationAclRepositoryImpl(TaskMergeRelationAclRepository):
    """task_service.TaskMergeRelation 跨域只读查询 gRPC 实现。"""

    def get_task_merge_relations(self, merged_task_id) -> List[TaskMergeRelationDTO]:
        from shared.clients.grpc_clients import get_task_merge_relations
        try:
            data = get_task_merge_relations(merged_task_id)
            items = [it for it in (data.get('items') or [])
                     if isinstance(it, dict) and it.get('merged_task_id') == merged_task_id]
            return [_attach(dict_to_dto(it, TaskMergeRelationDTO), it) for it in items]
        except Exception as e:
            logger.warning("get_task_merge_relations gRPC failed: %s", e)
            return []

    def get_task_merge_relations_by_source(self, source_task_id) -> List[TaskMergeRelationDTO]:
        from shared.clients.grpc_clients import get_task_merge_relations
        try:
            data = get_task_merge_relations(source_task_id)
            items = [it for it in (data.get('items') or [])
                     if isinstance(it, dict) and it.get('source_task_id') == source_task_id]
            return [_attach(dict_to_dto(it, TaskMergeRelationDTO), it) for it in items]
        except Exception as e:
            logger.warning("get_task_merge_relations_by_source gRPC failed: %s", e)
            return []
