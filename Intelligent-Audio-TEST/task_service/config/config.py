"""Task Service 领域配置"""
import os
from shared.infrastructure.config import BaseConfig


class Config(BaseConfig):
    PORT = int(os.environ.get('PORT', 5001))
    GRPC_PORT = int(os.environ.get('TASK_SERVICE_GRPC_PORT', os.environ.get('GRPC_PORT', 50061)))
    MAX_CONCURRENT = int(os.environ.get('MAX_CONCURRENT', 5))
    TASK_TIMEOUT = int(os.environ.get('TASK_TIMEOUT', 3600))

    # --- 用例批量操作幂等（INT-75）---
    # 客户端幂等键回放窗口：同键重复提交在窗口内直接回放上次响应
    IDEMPOTENCY_CLIENT_KEY_TTL_SECONDS = int(os.environ.get('IDEMPOTENCY_CLIENT_KEY_TTL_SECONDS', 86400))
    # 无客户端键时按请求内容指纹去重的窗口（双击/重试防护，不拦截有意的事后重复操作）
    IDEMPOTENCY_FINGERPRINT_TTL_SECONDS = int(os.environ.get('IDEMPOTENCY_FINGERPRINT_TTL_SECONDS', 60))
    # 占位态 TTL 上限：执行崩溃后占位到期自愈，不永久卡死重试
    IDEMPOTENCY_RESERVE_TTL_SECONDS = int(os.environ.get('IDEMPOTENCY_RESERVE_TTL_SECONDS', 300))

    # --- 用例参考参数批量刷新（INT-76）---
    # 同步处理上限：超过该条数的批量刷新转异步任务，避免请求超时（默认 50 保持行为兼容）
    REFERENCE_REFRESH_ASYNC_THRESHOLD = int(os.environ.get('REFERENCE_REFRESH_ASYNC_THRESHOLD', 50))
    # 异步刷新任务状态记录的 Redis TTL（秒）：过期后前端查询返回 not_found
    REFERENCE_REFRESH_TASK_TTL_SECONDS = int(os.environ.get('REFERENCE_REFRESH_TASK_TTL_SECONDS', 86400))


# 兼容旧代码中的 TaskServiceConfig 引用
TaskServiceConfig = Config
