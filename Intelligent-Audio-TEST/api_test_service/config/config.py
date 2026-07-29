"""API Test Service 领域配置"""
import os
from shared.infrastructure.config import BaseConfig


class Config(BaseConfig):
    PORT = int(os.environ.get('PORT', 5003))
    GRPC_PORT = int(os.environ.get('GRPC_PORT', 50071))


# 兼容旧代码中的 APITestServiceConfig 引用
APITestServiceConfig = Config
