# -*- coding: utf-8 -*-
"""task_service 防腐层仓储（ACL Repository）

P1.4 新增。替代 evaluation_service 直接 `from shared.models.models import Task, TaskCase, TestResult` 的跨域 ORM 引用。

本文件属于 infrastructure 层的防腐层（ACL），封装 gRPC 调用将 task_service 的
数据模型转换为 evaluation_service 可用的 dataclass DTO，隔离上下游领域模型。
向上层（domain/services）返回 dataclass DTO（部分结构不固定的接口仍返回 dict），不返回 ORM 对象。
"""
import logging
from typing import Any, Dict, List, Optional

from evaluation_service.domain.dto import (
    TaskDTO,
    TaskCaseDTO,
    TestCaseDetailDTO,
    DimensionParamDTO,
    TestResultDTO,
    TaskDeviceDTO,
    TaskApiDTO,
)
from evaluation_service.domain.repositories.task_acl_repository import TaskAclRepository as _TaskAclRepositoryABC
from shared.clients.grpc_clients import get_task_data_service_stub
from shared.proto import task_service_pb2 as task_pb
from shared.utils.dto_utils import dict_to_dto, dict_list_to_dto
from shared.utils.grpc_json import loads as _loads, dumps as _dumps

logger = logging.getLogger(__name__)


class TaskAclRepository(_TaskAclRepositoryABC):
    """task_service 防腐层仓储

    封装 gRPC 调用，提供领域层可用的 dataclass DTO 返回值。
    读方法返回 dataclass DTO（部分结构不固定的接口仍返回 dict），不返回 ORM 对象。
    """

    # ========== 读操作 ==========

    def get_test_result_by_id(self, result_id: int) -> Optional[TestResultDTO]:
        """按 ID 读取单个 TestResult。返回 TestResultDTO 或 None。"""
        try:
            stub = get_task_data_service_stub()
            resp = stub.GetTestResultById(task_pb.GetTestResultByIdRequest(result_id=result_id))
            if not resp.success:
                logger.warning('GetTestResultById %s failed: %s', result_id, resp.message)
                return None
            return dict_to_dto(_loads(resp.data, {}), TestResultDTO)
        except Exception as e:
            logger.exception('get_test_result_by_id failed: %s', e)
            return None

    def get_task_case_by_ids(
        self, task_id: int, case_ids: Optional[List[str]] = None
    ) -> List[TaskCaseDTO]:
        """批量读取 TaskCase。case_ids 为空时返回该 task 下所有 TaskCase。"""
        try:
            stub = get_task_data_service_stub()
            req = task_pb.GetTaskCaseByIdsRequest(task_id=task_id)
            if case_ids:
                req.case_ids.extend(list(case_ids))
            resp = stub.GetTaskCaseByIds(req)
            if not resp.success:
                logger.warning('GetTaskCaseByIds failed: %s', resp.message)
                return []
            return dict_list_to_dto(_loads(resp.data, []), TaskCaseDTO)
        except Exception as e:
            logger.exception('get_task_case_by_ids failed: %s', e)
            return []

    def get_task_by_id(self, task_id: int) -> Optional[TaskDTO]:
        """按 task_id 读取 Task 详情。"""
        try:
            stub = get_task_data_service_stub()
            resp = stub.GetTaskById(task_pb.GetTaskByIdRequest(task_id=task_id))
            if not resp.success:
                logger.warning('GetTaskById %s failed: %s', task_id, resp.message)
                return None
            return dict_to_dto(_loads(resp.data, {}), TaskDTO)
        except Exception as e:
            logger.exception('get_task_by_id failed: %s', e)
            return None

    def get_task_devices(self, task_id: int) -> List[TaskDeviceDTO]:
        """按 task_id 读取关联设备。"""
        try:
            stub = get_task_data_service_stub()
            resp = stub.GetTaskDevices(task_pb.GetTaskDevicesRequest(task_id=task_id))
            if not resp.success:
                logger.warning('GetTaskDevices failed: %s', resp.message)
                return []
            return dict_list_to_dto(_loads(resp.data, []), TaskDeviceDTO)
        except Exception as e:
            logger.exception('get_task_devices failed: %s', e)
            return []

    def get_task_apis(self, task_id: int) -> List[TaskApiDTO]:
        """按 task_id 读取关联 API。"""
        try:
            stub = get_task_data_service_stub()
            resp = stub.GetTaskApis(task_pb.GetTaskApisRequest(task_id=task_id))
            if not resp.success:
                logger.warning('GetTaskApis failed: %s', resp.message)
                return []
            return dict_list_to_dto(_loads(resp.data, []), TaskApiDTO)
        except Exception as e:
            logger.exception('get_task_apis failed: %s', e)
            return []

    def get_test_case_detail(self, tc_id: str) -> Optional[TestCaseDetailDTO]:
        """按 tc_id 读取测试用例详情（调 TestCaseConfigService.GetTestCaseDetail）。
        返回 TestCaseDetailDTO 或 None。"""
        try:
            from shared.clients.grpc_clients import get_testcase_config_service_stub
            stub = get_testcase_config_service_stub()
            resp = stub.GetTestCaseDetail(task_pb.GetTestCaseDetailRequest(tc_id=tc_id))
            if not resp.success:
                logger.warning('GetTestCaseDetail %s failed: %s', tc_id, resp.message)
                return None
            return dict_to_dto(_loads(resp.data, {}), TestCaseDetailDTO)
        except Exception as e:
            logger.exception('get_test_case_detail failed: %s', e)
            return None

    def get_dimension_params(self, dimension_id: int) -> List[DimensionParamDTO]:
        """获取评估维度的参数列表（含 output/input 完整字段）。
        调 task_service.AlgorithmConfigService.GetDimensionParams。"""
        try:
            from shared.clients.grpc_clients import get_algorithm_config_service_stub
            stub = get_algorithm_config_service_stub()
            resp = stub.GetDimensionParams(task_pb.GetDimensionParamsRequest(dimension_id=dimension_id))
            if not resp.success:
                logger.warning('GetDimensionParams %s failed: %s', dimension_id, resp.message)
                return []
            data = _loads(resp.data, {})
            return dict_list_to_dto(data, DimensionParamDTO, list_key='params')
        except Exception as e:
            logger.exception('get_dimension_params failed: %s', e)
            return []

    # ========== 写操作 ==========

    def submit_result(self, task_id: int, result_data: Dict) -> Optional[int]:
        """写入测试结果。返回新 result_id 或 None。"""
        try:
            stub = get_task_data_service_stub()
            resp = stub.SubmitResult(task_pb.SubmitResultRequest(
                task_id=task_id,
                result_data=_dumps(result_data),
            ))
            if not resp.success:
                logger.warning('SubmitResult failed: %s', resp.message)
                return None
            data = _loads(resp.data, {})
            return data.get('result_id')
        except Exception as e:
            logger.exception('submit_result failed: %s', e)
            return None

    def update_task_case_status(
        self,
        task_id: int,
        case_id: str,
        status: str = '',
        execution_status: str = '',
        evaluation_status: str = '',
        error_message: str = '',
    ) -> bool:
        """更新 TaskCase 状态。返回是否成功。"""
        try:
            stub = get_task_data_service_stub()
            resp = stub.UpdateTaskCaseStatus(task_pb.UpdateTaskCaseStatusRequest(
                task_id=task_id,
                case_id=case_id,
                status=status,
                execution_status=execution_status,
                evaluation_status=evaluation_status,
                error_message=error_message,
            ))
            if not resp.success:
                logger.warning('UpdateTaskCaseStatus failed: %s', resp.message)
                return False
            return True
        except Exception as e:
            logger.exception('update_task_case_status failed: %s', e)
            return False

    def update_test_result_algorithm_result(
        self, result_id: int, algorithm_result: Dict
    ) -> bool:
        """更新 TestResult.algorithm_result（多轮聚合后调用）。返回是否成功。"""
        try:
            stub = get_task_data_service_stub()
            resp = stub.UpdateTestResultAlgorithmResult(task_pb.UpdateTestResultAlgorithmResultRequest(
                result_id=result_id,
                algorithm_result=_dumps(algorithm_result),
            ))
            if not resp.success:
                logger.warning('UpdateTestResultAlgorithmResult failed: %s', resp.message)
                return False
            return True
        except Exception as e:
            logger.exception('update_test_result_algorithm_result failed: %s', e)
            return False

    def update_test_result_data(
        self, result_id: int, result_data: Any, result_data_path: str = None
    ) -> bool:
        """更新 TestResult.result_data 和 result_data_path（预提取 algorithm_results 快照后写回）。"""
        try:
            stub = get_task_data_service_stub()
            resp = stub.UpdateTestResultData(task_pb.UpdateTestResultDataRequest(
                result_id=result_id,
                result_data=_dumps(result_data),
                result_data_path=result_data_path or '',
            ))
            if not resp.success:
                logger.warning('UpdateTestResultData failed: %s', resp.message)
                return False
            return True
        except Exception as e:
            logger.exception('update_test_result_data failed: %s', e)
            return False

    def get_test_results_by_task_and_case(
        self, task_id: int, test_case_id: Optional[str] = None
    ) -> List[TestResultDTO]:
        """按 task_id + test_case_id 批量读取 TestResult。"""
        try:
            stub = get_task_data_service_stub()
            req = task_pb.GetTestResultsByTaskAndCaseRequest(task_id=task_id)
            if test_case_id:
                req.test_case_id = str(test_case_id)
            resp = stub.GetTestResultsByTaskAndCase(req)
            if not resp.success:
                logger.warning('GetTestResultsByTaskAndCase failed: %s', resp.message)
                return []
            return dict_list_to_dto(_loads(resp.data, []), TestResultDTO)
        except Exception as e:
            logger.exception('get_test_results_by_task_and_case failed: %s', e)
            return []

    def update_test_result_status(
        self, result_id: int, execution_status: str
    ) -> bool:
        """更新 TestResult.execution_status。返回是否成功。"""
        try:
            stub = get_task_data_service_stub()
            resp = stub.UpdateTestResultStatus(task_pb.UpdateTestResultStatusRequest(
                result_id=result_id,
                execution_status=execution_status,
            ))
            if not resp.success:
                logger.warning('UpdateTestResultStatus failed: %s', resp.message)
                return False
            return True
        except Exception as e:
            logger.exception('update_test_result_status failed: %s', e)
            return False

    def update_task_status(self, task_id: int, status: str) -> bool:
        """更新 Task.status。返回是否成功。"""
        try:
            stub = get_task_data_service_stub()
            resp = stub.UpdateTaskStatus(task_pb.UpdateTaskStatusRequest(
                task_id=task_id,
                status=status,
            ))
            if not resp.success:
                logger.warning('UpdateTaskStatus failed: %s', resp.message)
                return False
            return True
        except Exception as e:
            logger.exception('update_task_status failed: %s', e)
            return False

    def notify_task_progress(self, task_id: int, force: bool = False) -> None:
        """通知 task_service 发送进度更新。"""
        try:
            from shared.clients.grpc_clients import notify_task_progress as _notify
            _notify(task_id, force=force)
        except Exception as e:
            logger.exception('notify_task_progress failed: %s', e)

    def notify_case_completed(self, task_id: int) -> None:
        """通知 task_service 唤醒等待线程（某用例评估完成）。"""
        try:
            from shared.clients.grpc_clients import notify_case_completed as _notify
            _notify(task_id)
        except Exception as e:
            logger.exception('notify_case_completed failed: %s', e)


# 模块级单例
task_acl_repository = TaskAclRepository()
