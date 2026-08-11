# -*- coding: utf-8 -*-
"""task_service.TaskDataService ACL 仓储 — gRPC 实现。

从 report_service/infrastructure/clients/grpc_clients.py 迁出，
跨域只读查询返回 dataclass DTO（经 dict_to_dto / dict_list_to_dto 转换）。
DTO 的 result_data 保留原始 dict 负载，供 dto_to_dict 还原兼容历史调用方。
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from report_service.domain.dto import (
    TaskApiDTO, TaskCaseDTO, TaskDTO, TaskDeviceDTO, TestResultDTO,
)
from report_service.domain.repositories.acl.task_data_acl_repository import (
    TaskDataAclRepository,
)
from shared.utils.dto_utils import dict_to_dto, dict_list_to_dto
from shared.utils.grpc_client_helper import call_rpc

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

    def get_task_devices(self, task_id) -> List[TaskDeviceDTO]:
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        try:
            stub = get_task_data_service_stub()
            data = call_rpc(
                stub, 'GetTaskDevices',
                task_pb.GetTaskDevicesRequest(task_id=task_id),
                default=[], raise_on_failure=False,
            ) or []
            return [_attach(dict_to_dto(d, TaskDeviceDTO), d) for d in data if isinstance(d, dict)]
        except Exception as e:
            logger.warning("get_task_devices gRPC failed: %s", e)
            return []

    def get_task_apis(self, task_id) -> List[TaskApiDTO]:
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        try:
            stub = get_task_data_service_stub()
            data = call_rpc(
                stub, 'GetTaskApis',
                task_pb.GetTaskApisRequest(task_id=task_id),
                default=[], raise_on_failure=False,
            ) or []
            return [_attach(dict_to_dto(d, TaskApiDTO), d) for d in data if isinstance(d, dict)]
        except Exception as e:
            logger.warning("get_task_apis gRPC failed: %s", e)
            return []

    def get_tasks_by_ids(self, task_ids) -> List[TaskDTO]:
        if not task_ids:
            return []
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_task_data_service_stub()
            results: List[TaskDTO] = []
            for tid in task_ids:
                try:
                    resp = stub.GetTaskById(task_pb.GetTaskByIdRequest(task_id=tid))
                    if not resp.success:
                        continue
                    t = _loads(resp.data, {})
                    if t:
                        results.append(_attach(dict_to_dto(t, TaskDTO), t))
                except Exception as e:
                    logger.warning("get_tasks_by_ids item failed: %s", e)
                    continue
            return results
        except Exception as e:
            logger.warning("get_tasks_by_ids gRPC failed: %s", e)
            return []

    def get_test_results_by_task_ids(self, task_ids) -> List[TestResultDTO]:
        if not task_ids:
            return []
        if isinstance(task_ids, int):
            task_ids = [task_ids]
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_task_data_service_stub()
            all_results: List[TestResultDTO] = []
            for tid in task_ids:
                try:
                    resp = stub.GetTestResultsByTaskAndCase(
                        task_pb.GetTestResultsByTaskAndCaseRequest(task_id=tid))
                    if not resp.success:
                        continue
                    items = _loads(resp.data, []) or []
                    all_results.extend(
                        _attach(dict_to_dto(it, TestResultDTO), it)
                        for it in items if isinstance(it, dict))
                except Exception as e:
                    logger.warning("get_test_results_by_task_ids item failed: %s", e)
                    continue
            return all_results
        except Exception as e:
            logger.warning("get_test_results_by_task_ids gRPC failed: %s", e)
            return []

    def get_test_result_by_id(self, result_id) -> Optional[TestResultDTO]:
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_task_data_service_stub()
            resp = stub.GetTestResultById(task_pb.GetTestResultByIdRequest(result_id=result_id))
            if not resp.success:
                return None
            data = _loads(resp.data, {})
            return _attach(dict_to_dto(data, TestResultDTO), data)
        except Exception as e:
            logger.warning("get_test_result_by_id gRPC failed: %s", e)
            return None

    def get_task_case_ids(self, task_id) -> List[TaskCaseDTO]:
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_task_data_service_stub()
            resp = stub.GetTaskCaseByIds(task_pb.GetTaskCaseByIdsRequest(task_id=task_id))
            if not resp.success:
                return []
            items = _loads(resp.data, []) or []
            return [_attach(dict_to_dto(it, TaskCaseDTO), it) for it in items if isinstance(it, dict)]
        except Exception as e:
            logger.warning("get_task_case_ids gRPC failed: %s", e)
            return []

    def get_task_case_ids_batch(self, task_ids) -> List[TaskCaseDTO]:
        if not task_ids:
            return []
        all_items: List[TaskCaseDTO] = []
        for tid in task_ids:
            all_items.extend(self.get_task_case_ids(tid))
        return all_items

    def get_test_results_by_task_and_case(
        self, test_case_ids, task_ids=None,
    ) -> List[TestResultDTO]:
        if not test_case_ids:
            return []
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_task_data_service_stub()
            tc_id_set = {str(tc) for tc in test_case_ids}
            all_results: List[TestResultDTO] = []
            if task_ids:
                tid_list = task_ids if isinstance(task_ids, list) else [task_ids]
                for tid in tid_list:
                    try:
                        resp = stub.GetTestResultsByTaskAndCase(
                            task_pb.GetTestResultsByTaskAndCaseRequest(task_id=tid))
                        if not resp.success:
                            continue
                        items = _loads(resp.data, []) or []
                        for tr in items:
                            if not isinstance(tr, dict):
                                continue
                            tc_id = tr.get('test_case_id')
                            if tc_id is not None and str(tc_id) in tc_id_set:
                                all_results.append(_attach(dict_to_dto(tr, TestResultDTO), tr))
                    except Exception:
                        continue
            return all_results
        except Exception as e:
            logger.warning("get_test_results_by_task_and_case gRPC failed: %s", e)
            return []
