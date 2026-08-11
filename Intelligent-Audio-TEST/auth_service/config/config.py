# -*- coding: utf-8 -*-
"""auth_service 领域配置。"""
import os

from shared.infrastructure.config import BaseConfig


class Config(BaseConfig):
    """auth_service 配置。

    端口规划：
    - HTTP (FastAPI): 5009
    - gRPC: 50069
    """
    PORT = int(os.environ.get('PORT', 5009))
    GRPC_PORT = int(os.environ.get('GRPC_PORT', 50069))


# 兼容旧代码中的 AuthServiceConfig 引用
AuthServiceConfig = Config
