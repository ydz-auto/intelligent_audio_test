"""E2E Test Service 领域配置"""
import os
from shared.infrastructure.config import BaseConfig


class Config(BaseConfig):
    PORT = int(os.environ.get('PORT', 5002))
    GRPC_PORT = int(os.environ.get('GRPC_PORT', 50051))
    LAB_NAME = os.environ.get('LAB_NAME', 'lab-a')


# 兼容旧代码中的 E2ETestServiceConfig 引用
E2ETestServiceConfig = Config
