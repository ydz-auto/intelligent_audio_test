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


# 兼容旧代码中的 TaskServiceConfig 引用
TaskServiceConfig = Config
