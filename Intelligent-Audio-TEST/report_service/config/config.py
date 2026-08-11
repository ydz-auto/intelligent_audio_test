# -*- coding: utf-8 -*-
"""report_service 领域配置。"""
import os

from shared.infrastructure.config import BaseConfig


class Config(BaseConfig):
    """report_service 配置。

    端口规划：
    - HTTP (FastAPI): 5006（避免与 api_adapter_service 的 5008 冲突）
    - gRPC: 50068
    """
    PORT = int(os.environ.get('PORT', 5006))
    GRPC_PORT = int(os.environ.get('GRPC_PORT', 50068))
    SERVICE_NAME = 'report_service'
