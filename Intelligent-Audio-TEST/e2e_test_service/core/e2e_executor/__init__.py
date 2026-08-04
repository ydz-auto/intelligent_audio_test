"""e2e_executor 包 —— 由原 e2e_executor.py 拆分而来，保持向后兼容。

重导出：
- E2EExecutor：主执行器类（原有导入路径 `from e2e_test_service.core.e2e_executor import E2EExecutor` 仍可用）
- gRPC 辅助函数（模块级函数）
"""
from e2e_test_service.core.e2e_executor.executor import E2EExecutor
from e2e_test_service.core.e2e_executor.grpc_helpers import (
    _register_task_events_via_grpc,
    _register_task_devices_via_grpc,
    _play_voiceprint_via_grpc,
    _play_round_via_grpc,
)

__all__ = [
    'E2EExecutor',
    '_register_task_events_via_grpc',
    '_register_task_devices_via_grpc',
    '_play_voiceprint_via_grpc',
    '_play_round_via_grpc',
]
