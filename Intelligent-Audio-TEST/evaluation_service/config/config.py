"""Evaluation Service 领域配置"""
import os
from shared.infrastructure.config import BaseConfig


class Config(BaseConfig):
    PORT = int(os.environ.get('PORT', 5004))
    GRPC_PORT = int(os.environ.get('GRPC_PORT', 51091))
    SERVICE_NAME = 'evaluation_service'
