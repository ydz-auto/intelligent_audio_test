# -*- coding: utf-8 -*-
"""TaskDataService ACL 仓储 — gRPC 实现"""
from __future__ import annotations

import logging
from typing import List, Optional

from e2e_test_service.domain.dto import (
    TestResultDTO, TaskCaseDTO, DimensionResultDTO, TaskDeviceDTO,
)
from e2e_test_service.domain.repositories.task_data_acl_repository import (
    TaskDataAclRepository,
)
from shared.utils.dto_utils import dict_to_dto, dict_list_to_dto

logger = logging.getLogger(__name__)


class TaskDataAclRepositoryImpl(TaskDataAclRepository):
    """TaskDataService ACL 仓储实现"""

    def has_running_e2e_tasks(self) -> bool:
        """检查是否有运行中的 E2E 任务"""
        from shared.clients.grpc_clients import get_task_stats
        for status in ('queued', 'pending', 'running'):
            try:
                result = get_task_stats(status=status, group_by='type')
                items = result.get('items', []) if isinstance(result, dict) else []
                for item in items:
                    if item.get('key') == 'e2e' and item.get('count', 0) > 0:
                        return True
            except Exception as e:
                logger.error("has_running_e2e_tasks 查询 status=%s 失败: %s", status, e)
                continue
        return False

    def get_task_devices(self, task_id: str) -> List[TaskDeviceDTO]:
        """查询任务关联的 TaskDevice 关联记录"""
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_task_data_service_stub()
            resp = stub.GetTaskDevices(task_pb.GetTaskDevicesRequest(task_id=int(task_id)))
            if not resp.success:
                logger.error("get_task_devices 失败: %s", resp.message)
                return []
            data = _loads(resp.data, []) or []
            return dict_list_to_dto(data, TaskDeviceDTO)
        except Exception as e:
            logger.error("get_task_devices 异常: %s", e)
            return []

    def get_test_result_by_id(self, result_id: int) -> Optional[TestResultDTO]:
        """按 ID 查询 TestResult"""
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_task_data_service_stub()
            resp = stub.GetTestResultById(task_pb.GetTestResultByIdRequest(result_id=int(result_id)))
            if not resp.success:
                logger.error("get_test_result_by_id 失败: %s", resp.message)
                return None
            data = _loads(resp.data, {})
            return dict_to_dto(data, TestResultDTO)
        except Exception as e:
            logger.error("get_test_result_by_id 异常: %s", e)
            return None

    def update_test_result_algorithm_result(self, result_id: int,
                                             algorithm_result: str) -> bool:
        """更新 TestResult.algorithm_result"""
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        try:
            stub = get_task_data_service_stub()
            resp = stub.UpdateTestResultAlgorithmResult(
                task_pb.UpdateTestResultAlgorithmResultRequest(
                    result_id=int(result_id),
                    algorithm_result=algorithm_result,
                )
            )
            if not resp.success:
                logger.error("update_test_result_algorithm_result 失败: %s", resp.message)
            return resp.success
        except Exception as e:
            logger.error("update_test_result_algorithm_result 异常: %s", e)
            return False

    def update_test_result_status(self, result_id: int,
                                  execution_status: str) -> bool:
        """更新 TestResult.execution_status"""
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        try:
            stub = get_task_data_service_stub()
            resp = stub.UpdateTestResultStatus(
                task_pb.UpdateTestResultStatusRequest(
                    result_id=int(result_id),
                    execution_status=execution_status or '',
                )
            )
            if not resp.success:
                logger.error("update_test_result_status 失败: %s", resp.message)
            return resp.success
        except Exception as e:
            logger.error("update_test_result_status 异常: %s", e)
            return False

    def get_task_case_by_ids(self, task_id: str, case_ids: list) -> List[TaskCaseDTO]:
        """按 task_id 和 case_ids 查询 TaskCase"""
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_task_data_service_stub()
            resp = stub.GetTaskCaseByIds(task_pb.GetTaskCaseByIdsRequest(
                task_id=int(task_id),
                case_ids=[str(c) for c in case_ids],
            ))
            if not resp.success:
                logger.error("get_task_case_by_ids 失败: %s", resp.message)
                return []
            data = _loads(resp.data, [])
            return dict_list_to_dto(data, TaskCaseDTO)
        except Exception as e:
            logger.error("get_task_case_by_ids 异常: %s", e)
            return []

    def update_task_case_status(self, task_id: str, case_id: str,
                                status: str, execution_status: str = '',
                                evaluation_status: str = '',
                                error_message: str = '') -> bool:
        """更新 TaskCase 状态"""
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        try:
            stub = get_task_data_service_stub()
            resp = stub.UpdateTaskCaseStatus(task_pb.UpdateTaskCaseStatusRequest(
                task_id=int(task_id),
                case_id=str(case_id),
                status=status,
                execution_status=execution_status,
                evaluation_status=evaluation_status,
                error_message=error_message,
            ))
            if not resp.success:
                logger.error("update_task_case_status 失败: %s", resp.message)
            return resp.success
        except Exception as e:
            logger.error("update_task_case_status 异常: %s", e)
            return False

    def get_dimension_results_by_result_ids(self, result_ids: list) -> List[DimensionResultDTO]:
        """按 result_ids 查询维度评估结果"""
        from shared.clients.grpc_clients import get_evaluation_data_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb
        from shared.utils.grpc_json import loads as _loads, dumps as _dumps
        try:
            stub = get_evaluation_data_service_stub()
            resp = stub.GetDimensionResultsByResultIds(
                eval_pb.GetDimensionResultsByResultIdsRequest(
                    result_ids=_dumps([int(r) for r in result_ids])
                )
            )
            if not resp.success:
                logger.error("get_dimension_results_by_result_ids 失败: %s", resp.message)
                return []
            dim_data = _loads(resp.data, {})
            items = dim_data.get('items', []) if isinstance(dim_data, dict) else []
            return dict_list_to_dto(items, DimensionResultDTO)
        except Exception as e:
            logger.error("get_dimension_results_by_result_ids 异常: %s", e)
            return []
