# -*- coding: utf-8 -*-
"""auth_service 领域配置。"""
import os

from shared.infrastructure.config import BaseConfig


class Config(BaseConfig):
    """auth_service 配置。

    端口规划：
    - HTTP (FastAPI): 5009
    - gRPC: 51069（INT-926 平移，避开 Windows Hyper-V 排除端口段）
    """
    PORT = int(os.environ.get('PORT', 5009))
    GRPC_PORT = int(os.environ.get('GRPC_PORT', 51069))

    # 认证模式（INT-180 /api/auth/mode 自检端点数据源）：off|dev|prod，
    # compose 与 api_gateway 注入同一 AUTH_MODE，保持两侧报告一致
    AUTH_MODE = os.environ.get('AUTH_MODE', 'off')

    # Access Token（INT-1140）：每用户 token 上限（0/负数=不限制，new-api 同值 20）
    ACCESS_TOKEN_MAX_PER_USER = int(os.environ.get('ACCESS_TOKEN_MAX_PER_USER', 20))
    # 默认有效期天数（未显式指定时生效，new-api 同值 30）
    ACCESS_TOKEN_DEFAULT_EXPIRY_DAYS = int(
        os.environ.get('ACCESS_TOKEN_DEFAULT_EXPIRY_DAYS', 30))


# 兼容旧代码中的 AuthServiceConfig 引用
AuthServiceConfig = Config
