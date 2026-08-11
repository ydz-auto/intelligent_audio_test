# -*- coding: utf-8 -*-
"""algorithm_service 领域配置。"""
import os

from shared.infrastructure.config import BaseConfig


class Config(BaseConfig):
    """algorithm_service 配置。

    端口规划：
    - HTTP (FastAPI): 5007
    - gRPC: 50067
    """
    PORT = int(os.environ.get('PORT', 5007))
    GRPC_PORT = int(os.environ.get('GRPC_PORT', 50067))
    SERVICE_NAME = 'algorithm_service'
