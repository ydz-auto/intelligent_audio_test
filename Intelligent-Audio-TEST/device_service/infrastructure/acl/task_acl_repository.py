# -*- coding: utf-8 -*-
"""task_service 防腐层仓储（ACL Repository）

封装对 task_service.TaskConfigService 的 gRPC 调用，
替代 device_service 中对 shared.utils.task_utils.has_running_e2e_tasks 的直接 import。

- 读操作通过 gRPC 完成，返回 bool / dict / list，不返回 ORM 对象。
- 与 device_service/infrastructure/acl/algorithm_query_acl_repository.py 风格一致，
  采用具体类 + 模块级单例（device_service ACL 层无统一 ABC）。
"""
import logging

from shared.utils.status_constants import TaskStatus

logger = logging.getLogger(__name__)


class TaskACLRepository:
    """task_service 防腐层仓储

    封装 gRPC 调用，提供 application 层可用的返回值。
    所有方法返回纯 dict / list / bool，不返回 ORM 对象。
    """

    def has_running_e2e_tasks(self) -> bool:
        """查询 task_service 是否有运行中的 e2e 任务

        通过 gRPC 调用 task_service.TaskConfigService.ListTasks（status=running, type=e2e）
        替代原 shared.utils.task_utils.has_running_e2e_tasks 直连。
        gRPC 不可用时回退到无运行任务。
        """
        try:
            from shared.clients.grpc_clients import get_task_config_service_stub
            from shared.proto import task_service_pb2 as task_pb
            from shared.utils.grpc_json import loads as _loads

            stub = get_task_config_service_stub()
            resp = stub.ListTasks(task_pb.ListTasksRequest(
                page=1,
                per_page=1,
                status=TaskStatus.RUNNING,
                type='e2e',
            ))
            if not resp.success:
                return False
            data = _loads(resp.data, {}) or {}
            # 兼容分页结构：{'items': [...]} 或 {'total': N}
            if isinstance(data, dict):
                total = data.get('total')
                if total is not None:
                    return int(total) > 0
                items = data.get('items') or data.get('list') or []
                return len(items) > 0
            if isinstance(data, list):
                return len(data) > 0
            return False
        except Exception:
            return False

    def check_device_in_tasks(self, device_id: int) -> bool:
        """检查设备是否被任务引用

        通过 gRPC 调用 task_service.TaskConfigService.ListTasks 全量分页扫描，
        检查是否有任务的 devices 列表引用了此设备。
        gRPC 不可用时回退到无引用。
        """
        try:
            from shared.clients.grpc_clients import get_task_config_service_stub
            from shared.proto import task_service_pb2 as task_pb
            from shared.utils.grpc_json import loads as _loads

            stub = get_task_config_service_stub()
            page = 1
            per_page = 100
            while True:
                resp = stub.ListTasks(task_pb.ListTasksRequest(
                    page=page,
                    per_page=per_page,
                ))
                if not resp.success:
                    return False
                data = _loads(resp.data, {})
                if not isinstance(data, dict):
                    return False
                items = data.get('items', []) or []
                for task_item in items:
                    for dev in task_item.get('devices', []) or []:
                        if dev.get('id') == device_id:
                            return True
                total_pages = data.get('pages', 1)
                if page >= total_pages or not items:
                    return False
                page += 1
        except Exception:
            return False


# 模块级单例
task_acl_repository = TaskACLRepository()
