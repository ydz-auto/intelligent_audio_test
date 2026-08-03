# -*- coding: utf-8 -*-
"""命令处理器 — 委托给已有的 core/api_test_service.py，不重写执行逻辑。

原则：application 层只做编排与委托，真正的执行逻辑仍由 core 层持有。
"""
from api_test_service.application.commands.api_test_commands import (
    CreateAPITestCommand,
    StopAPITestCommand,
)
from api_test_service.core.api_test_service import api_test_service as _service


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


# 便于直接调用的模块级实例
create_api_test_handler = CreateAPITestCommandHandler()
stop_api_test_handler = StopAPITestCommandHandler()
