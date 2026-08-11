# -*- coding: utf-8 -*-
"""task_service.TaskDataService ACL 仓储 — gRPC 实现。

将 api_test_service/core 与 infrastructure/persistence 中分散的
task_service gRPC 调用集中到 ACL 仓储，返回 dataclass DTO（经
dict_to_dto / dict_list_to_dto 转换）。
"""
from __future__ import annotations

import logging
from typing import List, Optional

from api_test_service.domain.dto import TaskApiDTO, TaskCaseDTO, TaskDTO
from api_test_service.domain.repositories.acl.task_data_acl_repository import (
    TaskDataAclRepository,
)
from shared.utils.dto_utils import dict_to_dto, dict_list_to_dto

logger = logging.getLogger(__name__)


def _attach(dto, payload):
    """将原始 dict 负载挂到 DTO.result_data，供 dto_to_dict 还原。"""
    if dto is not None and payload is not None:
        try:
            dto.result_data = payload
        except Exception:
            pass
    return dto


class TaskDataAclRepositoryImpl(TaskDataAclRepository):
    """task_service.TaskDataService 跨域只读查询 gRPC 实现。"""

    def get_task_case_by_ids(self, task_id, case_ids=None) -> List[TaskCaseDTO]:
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_task_data_service_stub()
            req = task_pb.GetTaskCaseByIdsRequest(task_id=int(task_id))
            if case_ids:
                req = task_pb.GetTaskCaseByIdsRequest(
                    task_id=int(task_id),
                    case_ids=[str(c) for c in case_ids],
                )
            resp = stub.GetTaskCaseByIds(req)
            if not resp.success:
                logger.warning("get_task_case_by_ids failed: %s", resp.message)
                return []
            items = _loads(resp.data, []) or []
            return [_attach(dict_to_dto(it, TaskCaseDTO), it)
                    for it in items if isinstance(it, dict)]
        except Exception as e:
            logger.warning("get_task_case_by_ids gRPC failed: %s", e)
            return []

    def get_task_by_id(self, task_id) -> Optional[TaskDTO]:
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_task_data_service_stub()
            resp = stub.GetTaskById(task_pb.GetTaskByIdRequest(task_id=int(task_id)))
            if not resp.success:
                logger.warning("get_task_by_id %s failed: %s", task_id, resp.message)
                return None
            data = _loads(resp.data, {}) or None
            return _attach(dict_to_dto(data, TaskDTO), data)
        except Exception as e:
            logger.warning("get_task_by_id gRPC failed: %s", e)
            return None

    def get_task_apis(self, task_id) -> List[TaskApiDTO]:
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_task_data_service_stub()
            resp = stub.GetTaskApis(task_pb.GetTaskApisRequest(task_id=int(task_id)))
            if not resp.success:
                logger.warning("get_task_apis failed: %s", resp.message)
                return []
            items = _loads(resp.data, []) or []
            return [_attach(dict_to_dto(it, TaskApiDTO), it)
                    for it in items if isinstance(it, dict)]
        except Exception as e:
            logger.warning("get_task_apis gRPC failed: %s", e)
            return []

    def update_task_case_status(self, task_id, case_id, status=None,
                                execution_status=None, evaluation_status=None,
                                error_message=None) -> bool:
        from shared.clients.grpc_clients import update_task_case_status as _update
        return bool(_update(
            task_id=task_id,
            case_id=str(case_id),
            status=status,
            execution_status=execution_status,
            evaluation_status=evaluation_status,
            error_message=error_message,
        ))

    def submit_result(self, task_id, result_data) -> Optional[int]:
        from shared.clients.grpc_clients import submit_result as _submit
        return _submit(task_id, result_data)
