"""e2e_executor 包 —— 由原 e2e_executor.py 拆分而来，保持向后兼容。

重导出：
- E2EExecutor：主执行器类（原有导入路径 `from e2e_test_service.core.e2e_executor import E2EExecutor` 仍可用）

gRPC 封装函数已迁移到 infrastructure/acl/ 下的 ACL repository 类，
不再从 grpc_helpers 重导出。
"""
from e2e_test_service.application.services.e2e_executor.executor import E2EExecutor

__all__ = [
    'E2EExecutor',
]
