# -*- coding: utf-8 -*-
"""E2E 测试 CQRS Handler。

统一导出命令/查询处理器，供 interfaces 层调用。
"""

from e2e_test_service.application.handlers.command_handlers import (
    StartE2ETestHandler,
    StopE2ETestHandler,
    RecordAudioHandler,
)
from e2e_test_service.application.handlers.query_handlers import (
    GetDeviceStatusHandler,
    GetTestProgressHandler,
)

__all__ = [
    'StartE2ETestHandler',
    'StopE2ETestHandler',
    'RecordAudioHandler',
    'GetDeviceStatusHandler',
    'GetTestProgressHandler',
]
