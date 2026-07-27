"""Task Service 领域配置"""
import os
from shared.infrastructure.config import BaseConfig


class Config(BaseConfig):
    PORT = int(os.environ.get('PORT', 5001))
    GRPC_PORT = int(os.environ.get('GRPC_PORT', 50061))
    MAX_CONCURRENT = int(os.environ.get('MAX_CONCURRENT', 5))
    TASK_TIMEOUT = int(os.environ.get('TASK_TIMEOUT', 3600))


# 兼容旧代码中的 TaskServiceConfig 引用
TaskServiceConfig = Config
