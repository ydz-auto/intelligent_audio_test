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

    # 用户管理入口（admin 建号 / admin 改资料带密码）密码长度兜底（INT-1590）：
    # gRPC 直连绕过网关时同样拒绝 <8 或 >128 位。与自助注册 / 自助改密的
    # 6 位下限是两个产品面，不共用。键名与网关 Config 保持一致，一次 .env 生效。
    USER_ADMIN_PASSWORD_MIN_LENGTH = int(os.environ.get(
        'AUTH_USER_ADMIN_PASSWORD_MIN_LENGTH', '8'))
    PASSWORD_MAX_LENGTH = int(os.environ.get(
        'AUTH_PASSWORD_MAX_LENGTH', '128'))


# 兼容旧代码中的 AuthServiceConfig 引用
AuthServiceConfig = Config
