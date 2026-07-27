"""API Gateway 领域配置"""
import os
from shared.infrastructure.config import BaseConfig


class Config(BaseConfig):
    PORT = int(os.environ.get('PORT', 5000))


# 兼容旧代码中的 GatewayConfig 引用
GatewayConfig = Config
