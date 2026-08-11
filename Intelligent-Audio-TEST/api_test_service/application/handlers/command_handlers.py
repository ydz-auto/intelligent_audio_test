# -*- coding: utf-8 -*-
"""命令处理器 — 委托给已有的 core/api_test_service.py，不重写执行逻辑。

原则：application 层只做编排与委托，真正的执行逻辑仍由 core 层持有。

API 配置 CRUD 命令处理器（CreateAPI/UpdateAPI/DeleteAPI）则直接通过
api_test_repository 操作聚合根，不直接 import PO，保持领域隔离。
"""
from api_test_service.application.commands.api_test_commands import (
    CreateAPITestCommand,
    StopAPITestCommand,
    CreateAPICommand,
    UpdateAPICommand,
    DeleteAPICommand,
)
from api_test_service.core.api_test_service import api_test_service as _service
from api_test_service.infrastructure.persistence.api_test_repository import api_test_repository


class CreateAPITestCommandHandler:
    """处理 CreateAPITestCommand — 启动一个 API 测试任务

    委托给 APITestService.start_task(task_id, case_ids, api_ids)。
    """

    def handle(self, command: CreateAPITestCommand) -> dict:
        return _service.start_task(
            task_id=command.task_id,
            case_ids=command.case_ids,
            api_ids=command.api_ids,
        )


class StopAPITestCommandHandler:
    """处理 StopAPITestCommand — 停止一个正在运行的 API 测试任务

    委托给 APITestService.stop_task(task_id)。
    """

    def handle(self, command: StopAPITestCommand) -> dict:
        return _service.stop_task(task_id=command.task_id)


# ========== API 配置 CRUD 命令处理器（通过 repository 操作聚合根）==========


def _aggregate_to_dict(aggregate) -> dict:
    """将 APIAggregate 聚合根序列化为 dict。

    聚合根仅承载核心字段，故仅输出聚合根持有的信息，
    不涉及 PO 独有的 vendor/meta/api_endpoints 等字段，避免领域泄漏。
    """
    return {
        'id': aggregate.id,
        'name': aggregate.name,
        'url': aggregate.url,
        'status': aggregate.status,
        'timeout_seconds': aggregate.timeout_seconds,
        'deleted': aggregate.deleted,
    }


class CreateAPICommandHandler:
    """处理 CreateAPICommand — 创建 API 配置

    通过 api_test_repository.create_api 创建聚合根并持久化。
    """

    def handle(self, command: CreateAPICommand) -> dict:
        try:
            aggregate = api_test_repository.create_api(command.data)
            return {
                'success': True,
                'message': 'API配置创建成功',
                'data': {'id': aggregate.id, **_aggregate_to_dict(aggregate)},
                'code': 201,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}


class UpdateAPICommandHandler:
    """处理 UpdateAPICommand — 更新 API 配置

    通过 api_test_repository.update_api 更新聚合根并返回最新状态。
    """

    def handle(self, command: UpdateAPICommand) -> dict:
        try:
            aggregate = api_test_repository.update_api(command.api_id, command.data)
            if aggregate is None:
                return {'success': False, 'message': '未找到API配置', 'data': None, 'code': 404}
            return {
                'success': True,
                'message': 'API配置更新成功',
                'data': _aggregate_to_dict(aggregate),
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}


class DeleteAPICommandHandler:
    """处理 DeleteAPICommand — 软删除 API 配置

    通过 api_test_repository.delete_api 软删除聚合根。
    """

    def handle(self, command: DeleteAPICommand) -> dict:
        try:
            success = api_test_repository.delete_api(command.api_id)
            if not success:
                return {'success': False, 'message': '未找到API配置', 'data': None, 'code': 404}
            return {
                'success': True,
                'message': 'API配置已删除',
                'data': None,
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}


# 便于直接调用的模块级实例
create_api_test_handler = CreateAPITestCommandHandler()
stop_api_test_handler = StopAPITestCommandHandler()
create_api_handler = CreateAPICommandHandler()
update_api_handler = UpdateAPICommandHandler()
delete_api_handler = DeleteAPICommandHandler()
