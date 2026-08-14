# -*- coding: utf-8 -*-
"""task_service.TaskDataService 防腐层仓储（ACL Repository）

封装对 task_service.TaskDataService 的 gRPC 调用，
替代 device_service application 层中对 shared.clients.grpc_clients 的直接 import。

- 读/写操作均通过 gRPC 完成，返回 dict / list / bool / int，不返回 ORM 对象。
- 与 device_service/infrastructure/acl/task_acl_repository.py 风格一致，
  采用具体类 + 模块级单例（device_service ACL 层无统一 ABC）。
"""
import logging

logger = logging.getLogger(__name__)


class TaskDataACLRepository:
    """task_service.TaskDataService 防腐层仓储

    封装 gRPC 调用，提供 application 层可用的返回值。
    所有方法返回纯 dict / list / bool，不返回 ORM 对象。
    """

    def get_task_by_id(self, task_id):
        """查询任务详情

        通过 gRPC 调用 task_service.TaskDataService.GetTaskById。
        返回 {'success': bool, 'data': dict}；gRPC 不可用时 success=False。
        """
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_task_data_service_stub()
            resp = stub.GetTaskById(task_pb.GetTaskByIdRequest(task_id=int(task_id)))
            if not resp.success:
                return {'success': False, 'data': None}
            return {'success': True, 'data': _loads(resp.data, {}) or {}}
        except Exception as e:
            logger.warning(f"get_task_by_id gRPC 调用失败: {e}")
            return {'success': False, 'data': None}

    def get_task_devices(self, task_id):
        """查询任务设备关联记录

        通过 gRPC 调用 task_service.TaskDataService.GetTaskDevices。
        返回设备关联列表；gRPC 不可用时返回空列表。
        """
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_task_data_service_stub()
            resp = stub.GetTaskDevices(task_pb.GetTaskDevicesRequest(task_id=int(task_id)))
            if not resp.success:
                return []
            return _loads(resp.data, []) or []
        except Exception as e:
            logger.warning(f"get_task_devices gRPC 调用失败: {e}")
            return []

    def get_task_case_by_ids(self, task_id):
        """查询任务的用例关联记录

        通过 gRPC 调用 task_service.TaskDataService.GetTaskCaseByIds。
        返回用例关联列表；gRPC 不可用时返回空列表。
        """
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_task_data_service_stub()
            resp = stub.GetTaskCaseByIds(task_pb.GetTaskCaseByIdsRequest(task_id=int(task_id)))
            if not resp.success:
                return []
            return _loads(resp.data, []) or []
        except Exception as e:
            logger.warning(f"get_task_case_by_ids gRPC 调用失败: {e}")
            return []

    def get_test_results_by_task_and_case(self, task_id, test_case_id):
        """查询任务和用例下的测试结果

        通过 gRPC 调用 task_service.TaskDataService.GetTestResultsByTaskAndCase。
        返回测试结果列表；gRPC 不可用时返回空列表。
        """
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_task_data_service_stub()
            resp = stub.GetTestResultsByTaskAndCase(
                task_pb.GetTestResultsByTaskAndCaseRequest(
                    task_id=int(task_id),
                    test_case_id=str(test_case_id),
                )
            )
            if not resp.success:
                return []
            return _loads(resp.data, []) or []
        except Exception as e:
            logger.warning(f"get_test_results_by_task_and_case gRPC 调用失败: {e}")
            return []

    def update_test_result_status(self, result_id, execution_status):
        """更新测试结果状态

        通过 gRPC 调用 task_service.TaskDataService.UpdateTestResultStatus。
        返回是否成功；gRPC 异常时返回 False。
        """
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        try:
            stub = get_task_data_service_stub()
            stub.UpdateTestResultStatus(task_pb.UpdateTestResultStatusRequest(
                result_id=int(result_id),
                execution_status=execution_status,
            ))
            return True
        except Exception as e:
            logger.warning(f"update_test_result_status gRPC 调用失败: {e}")
            return False

    def update_task_case_status(self, task_id, case_id, evaluation_status=None,
                                execution_status=None, status=None, error_message=None):
        """更新任务用例状态

        通过 gRPC 调用 task_service.TaskDataService.UpdateTaskCaseStatus。
        返回是否成功；gRPC 异常时返回 False。
        """
        from shared.clients.grpc_clients import get_task_data_service_stub
        from shared.proto import task_service_pb2 as task_pb
        try:
            stub = get_task_data_service_stub()
            stub.UpdateTaskCaseStatus(task_pb.UpdateTaskCaseStatusRequest(
                task_id=int(task_id),
                case_id=str(case_id),
                status=status or '',
                execution_status=execution_status or '',
                evaluation_status=evaluation_status or '',
                error_message=error_message or '',
            ))
            return True
        except Exception as e:
            logger.warning(f"update_task_case_status gRPC 调用失败: {e}")
            return False

    def submit_result(self, task_id, result_data):
        """提交测试结果

        通过 gRPC 调用 task_service.TaskDataService.SubmitResult 写入 TestResult。
        返回新建 TestResult 的 result_id；gRPC 不可用时返回 None。
        """
        from shared.clients.grpc_clients import submit_result
        try:
            return submit_result(task_id, result_data)
        except Exception as e:
            logger.warning(f"submit_result gRPC 调用失败: {e}")
            return None


# 模块级单例
task_data_acl_repository = TaskDataACLRepository()
