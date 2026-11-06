# -*- coding: utf-8 -*-
"""TaskDataService ACL 仓储 — gRPC 实现"""
from __future__ import annotations

import logging
from typing import List, Optional

from e2e_test_service.domain.dto import (
    TestResultDTO, TaskCaseDTO, DimensionResultDTO, TaskDeviceDTO,
)
from e2e_test_service.domain.repositories.acl_errors import AclQueryError
from e2e_test_service.domain.repositories.task_data_acl_repository import (
    TaskDataAclRepository,
)
from shared.utils.dto_utils import dict_to_dto, dict_list_to_dto

logger = logging.getLogger(__name__)


def _coerce_tc_rel_id(value):
    """将 tc_rel_id 归一为 int；空/非数字 → None（INT-604，防御转换）。"""
    if value in (None, '', 0):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class TaskDataAclRepositoryImpl(TaskDataAclRepository):
    """TaskDataService ACL 仓储实现"""

    def has_running_e2e_tasks(self) -> bool:
        """检查是否有运行中的 E2E（物理设备形态）任务

        差异#2 收尾：task.type 已废弃删除，GetTaskStats 的 group_by='type'
        不再支持；改经 TaskConfigService.ListTasks 以 device_type 过滤
        （proto ListTasksRequest.type 字段承载 device_type='physical'），
        覆盖 queued/pending/running 三种中间态。
        """
        from shared.clients.grpc_clients import get_task_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        for status in ('queued', 'pending', 'running'):
            try:
                stub = get_task_config_service_stub()
                resp = stub.ListTasks(task_pb.ListTasksRequest(
                    page=1,
                    per_page=1,
                    status=status,
                    type='physical',
                ))
                if not resp.success:
                    continue
                data = _loads(resp.data, {}) or {}
                if isinstance(data, dict):
                    total = data.get('total')
                    if total is not None and int(total) > 0:
                        return True
                    items = data.get('items') or data.get('list') or []
                    if len(items) > 0:
                        return True
                elif isinstance(data, list) and len(data) > 0:
                    return True
            except Exception as e:
                logger.error("has_running_e2e_tasks 查询 status=%s 失败: %s", status, e)
                continue
        return False

    def get_task_devices(self, task_id: str) -> List[TaskDeviceDTO]:
        """查询任务关联的 TaskDevice 关联记录

        INT-2255：gRPC 异常 / 服务端 success=False 上抛 AclQueryError，与
        「任务确实没有关联设备」的空列表严格区分；不得吞成 []，否则设备
        准备阶段会把查询故障误报成「没有可用的测试设备」。
        """
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_task_data_service_stub()
            resp = stub.GetTaskDevices(task_pb.GetTaskDevicesRequest(task_id=int(task_id)))
        except Exception as e:
            logger.error("get_task_devices 异常: %s", e)
            raise AclQueryError(f"GetTaskDevices 调用失败: {e}") from e
        if not resp.success:
            logger.error("get_task_devices 失败: %s", resp.message)
            raise AclQueryError(
                f"GetTaskDevices 返回失败: {resp.message or '未提供失败原因'}")
        try:
            data = _loads(resp.data, []) or []
        except (ValueError, TypeError) as e:
            logger.error("get_task_devices 数据解析失败: %s", e)
            raise AclQueryError(f"GetTaskDevices 数据解析失败: {e}") from e
        return dict_list_to_dto(data, TaskDeviceDTO)

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

    def update_test_result_outcome(self, result_id: int,
                                   algorithm_result: Optional[str] = None,
                                   execution_status: Optional[str] = None,
                                   response_time: Optional[int] = None,
                                   error_message: Optional[str] = None,
                                   result_data_path: Optional[str] = None) -> bool:
        """一次性更新 TestResult 终态字段（等价单条 UPDATE）"""
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        try:
            stub = get_task_data_service_stub()
            resp = stub.UpdateTestResultOutcome(
                task_pb.UpdateTestResultOutcomeRequest(
                    result_id=int(result_id),
                    algorithm_result=algorithm_result or '',
                    execution_status=execution_status or '',
                    response_time=int(response_time) if response_time is not None else 0,
                    error_message=error_message or '',
                    result_data_path=result_data_path or '',
                )
            )
            if not resp.success:
                logger.error("update_test_result_outcome 失败: %s", resp.message)
            return resp.success
        except Exception as e:
            logger.error("update_test_result_outcome 异常: %s", e)
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
                                status: str = '', execution_status: str = '',
                                evaluation_status: str = '',
                                error_message: str = '',
                                started_at=None, completed_at=None,
                                tc_rel_id: Optional[int] = None) -> bool:
        """更新 TaskCase 状态（status 为空由 task_service 推导复合状态，对齐服务端契约）

        INT-604：tc_rel_id 可选——多路由下按路由行精确命中，避免兄弟路由互相覆盖。
        """
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
                started_at=self._to_iso8601(started_at),
                completed_at=self._to_iso8601(completed_at),
                tc_rel_id=_coerce_tc_rel_id(tc_rel_id) or 0,
            ))
            if not resp.success:
                logger.error("update_task_case_status 失败: %s", resp.message)
            return resp.success
        except Exception as e:
            logger.error("update_task_case_status 异常: %s", e)
            return False

    @staticmethod
    def _to_iso8601(value):
        """datetime / ISO8601 字符串 → ISO8601 字符串；None/空 → ''。"""
        if value is None or value == '':
            return ''
        if isinstance(value, str):
            return value
        return value.isoformat()

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

    def _get_stub(self):
        """获取 task_data_service gRPC stub"""
        from shared.clients.grpc_clients import get_task_data_service_stub
        return get_task_data_service_stub()

    def _get_testcase_stub(self):
        """获取 testcase_config_service gRPC stub"""
        from shared.clients.grpc_clients import get_testcase_config_service_stub
        return get_testcase_config_service_stub()

    def notify_task_progress(self, task_id: str, force: bool = False):
        """通知任务进度"""
        from shared.clients.grpc_clients import notify_task_progress as _notify
        return _notify(task_id, force=force)

    def submit_result(self, task_id: str, result_payload: dict):
        """提交测试结果"""
        from shared.clients.grpc_clients import submit_result as _submit
        return _submit(task_id, result_payload)

    def submit_evaluate_case(self, task_id, result_id, test_case_id, algorithm_result, **eval_params):
        """提交评估（通过 gRPC 调用 evaluation_service.EvaluateCase）"""
        from shared.clients.grpc_clients import submit_evaluate_case
        device_type = eval_params.pop('device_type', None)
        return submit_evaluate_case(
            task_id=task_id, result_id=result_id, test_case_id=test_case_id,
            algorithm_result=algorithm_result, eval_params=eval_params,
            device_type=device_type,
        )
