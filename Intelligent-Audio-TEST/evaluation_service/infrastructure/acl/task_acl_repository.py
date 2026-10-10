# -*- coding: utf-8 -*-
"""task_service 防腐层仓储（ACL Repository）

P1.4 新增。替代 evaluation_service 直接 `from shared.models.models import Task, TaskCase, TestResult` 的跨域 ORM 引用。

本文件属于 infrastructure 层的防腐层（ACL），封装 gRPC 调用将 task_service 的
数据模型转换为 evaluation_service 可用的 dataclass DTO，隔离上下游领域模型。
向上层（domain/services）返回 dataclass DTO（部分结构不固定的接口仍返回 dict），不返回 ORM 对象。
"""
import logging
import time
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
from shared.utils.id_normalizer import to_int_id

logger = logging.getLogger(__name__)

# INT-116：task_service 瞬时过载（连接池耗尽→超时/失败）时的内联重试参数。
# 重试仅覆盖传输级失败（异常/服务端 success=False），空结果是合法应答不重试。
_TRANSIENT_ATTEMPTS = 3
_TRANSIENT_BACKOFF_SECONDS = (0.5, 1.0)


def _norm_task_id(task_id) -> int:
    """task_service protobuf 的 task_id 为 int 字段，构造前统一归一。

    归一失败（空/非数字）在 try 块外抛 ValueError，由调用方 except 分支
    透出失败，避免被本仓储的兜底返回（[]/None/False）掩盖成“无数据”。
    """
    return to_int_id('task_id', task_id)


def _norm_result_id(result_id) -> int:
    return to_int_id('result_id', result_id)


def _with_transient_retry(desc, call):
    """带内联重试的 gRPC 调用（INT-116）。

    Args:
        desc: 日志标识
        call: 无参可调用，返回 (ok, value)；ok=False 表示可重试的失败

    Returns:
        value: 成功时为 call 的第二返回值；最终失败时为 None
    """
    for attempt in range(_TRANSIENT_ATTEMPTS):
        try:
            ok, value = call()
        except Exception as e:
            ok, value = False, None
            logger.warning('%s 第 %s 次调用异常: %s', desc, attempt + 1, e)
        if ok:
            return value
        if attempt < _TRANSIENT_ATTEMPTS - 1:
            time.sleep(_TRANSIENT_BACKOFF_SECONDS[min(attempt, len(_TRANSIENT_BACKOFF_SECONDS) - 1)])
    logger.error('%s 内联重试 %s 次仍失败', desc, _TRANSIENT_ATTEMPTS)
    return None


class TaskAclRepository(_TaskAclRepositoryABC):
    """task_service 防腐层仓储

    封装 gRPC 调用，提供领域层可用的 dataclass DTO 返回值。
    读方法返回 dataclass DTO（部分结构不固定的接口仍返回 dict），不返回 ORM 对象。
    """

    # ========== 读操作 ==========

    def get_test_result_by_id(self, result_id: int) -> Optional[TestResultDTO]:
        """按 ID 读取单个 TestResult。返回 TestResultDTO 或 None。"""
        result_id = _norm_result_id(result_id)
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
        """批量读取 TaskCase。case_ids 为空时返回该 task 下所有 TaskCase。

        INT-116: 传输级失败内联重试（评估后状态推进依赖本读取，瞬时失败
        曾导致整个状态推进被跳过、用例永久停留 evaluating）。
        """
        task_id = _norm_task_id(task_id)

        def _call():
            stub = get_task_data_service_stub()
            req = task_pb.GetTaskCaseByIdsRequest(task_id=task_id)
            if case_ids:
                req.case_ids.extend(list(case_ids))
            resp = stub.GetTaskCaseByIds(req)
            if not resp.success:
                return False, None
            return True, dict_list_to_dto(_loads(resp.data, []), TaskCaseDTO)

        dtos = _with_transient_retry(f'GetTaskCaseByIds task_id={task_id}', _call)
        return dtos if dtos is not None else []

    def get_task_by_id(self, task_id: int) -> Optional[TaskDTO]:
        """按 task_id 读取 Task 详情。"""
        task_id = _norm_task_id(task_id)
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
        task_id = _norm_task_id(task_id)
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
        task_id = _norm_task_id(task_id)
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
        dimension_id = to_int_id('dimension_id', dimension_id)
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
        task_id = _norm_task_id(task_id)
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
        """更新 TaskCase 状态。返回是否成功。

        INT-116: 传输级失败内联重试（终态/进度推进写库，瞬时失败曾导致
        task_case_relations 永久停留 evaluating）。持久失败由调用方决定
        是否转延迟重试队列。
        """
        task_id = _norm_task_id(task_id)

        def _call():
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
                return False, None
            return True, True

        return _with_transient_retry(
            f'UpdateTaskCaseStatus task_id={task_id} case_id={case_id}', _call) is True

    def update_test_result_algorithm_result(
        self, result_id: int, algorithm_result: Dict
    ) -> bool:
        """更新 TestResult.algorithm_result（多轮聚合后调用）。返回是否成功。"""
        result_id = _norm_result_id(result_id)
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
        result_id = _norm_result_id(result_id)
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
        task_id = _norm_task_id(task_id)
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
        result_id = _norm_result_id(result_id)
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
        """更新 Task.status。返回是否成功。

        INT-116: 传输级失败内联重试（任务终态写库失败是"任务永不收敛→
        执行引擎无限忙等"的直接原因）。
        """
        task_id = _norm_task_id(task_id)

        def _call():
            stub = get_task_data_service_stub()
            resp = stub.UpdateTaskStatus(task_pb.UpdateTaskStatusRequest(
                task_id=task_id,
                status=status,
            ))
            if not resp.success:
                return False, None
            return True, True

        return _with_transient_retry(
            f'UpdateTaskStatus task_id={task_id} status={status}', _call) is True

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
