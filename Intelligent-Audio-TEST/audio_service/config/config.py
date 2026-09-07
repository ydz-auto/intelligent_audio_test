# -*- coding: utf-8 -*-
"""Audio Service 领域配置"""
import os
from shared.infrastructure.config import BaseConfig


class Config(BaseConfig):
    PORT = int(os.environ.get('PORT', 5005))
    GRPC_PORT = int(os.environ.get('GRPC_PORT', 50052))
