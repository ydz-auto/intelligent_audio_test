# -*- coding: utf-8 -*-
"""认证模式枚举（INT-180）——AUTH_MODE / VITE_AUTH_MODE 单一取值来源。

后端 api_gateway 按此枚举校验 AUTH_MODE（启动即自曝非法取值），
auth_service /api/auth/mode 与网关 /api/v1/auth/mode 按此枚举回值；
前端构建期 VITE_AUTH_MODE 对应同一取值集合（frontend/src/domain/enums.ts AuthMode）。
"""
from enum import Enum


class AuthMode(str, Enum):
    """认证模式（值 = 后端 Config.AUTH_MODE 原值，禁止改动值）"""

    OFF = 'off'
    DEV = 'dev'
    PROD = 'prod'


AUTH_MODE_VALUES = tuple(mode.value for mode in AuthMode)


def normalize_auth_mode(value) -> str:
    """校验并归一 auth_mode 取值，非法值抛 ValueError（拒绝魔法字符串）。"""
    if isinstance(value, AuthMode):
        return value.value
    if value not in AUTH_MODE_VALUES:
        raise ValueError(
            f'AUTH_MODE="{value}" 不是合法取值，允许：{" | ".join(AUTH_MODE_VALUES)}')
    return value
