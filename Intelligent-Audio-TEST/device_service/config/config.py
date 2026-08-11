# -*- coding: utf-8 -*-
"""device_service 领域配置。"""
import os

from shared.infrastructure.config import BaseConfig


class Config(BaseConfig):
    """device_service 配置。

    端口规划：
    - HTTP (FastAPI): 5005
    - gRPC: 50053
    """
    PORT = int(os.environ.get('PORT', 5005))
    GRPC_PORT = int(os.environ.get('GRPC_PORT', 50053))
    SERVICE_NAME = 'device_service'
