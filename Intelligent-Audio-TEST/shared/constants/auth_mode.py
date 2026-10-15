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

# 认证模式响应提示头（INT-406）——API 响应携带当前 AUTH_MODE，调用方/前端
# 一眼可见 AUTH_MODE=off 的免认证风险态（对偶前端 INT-181 构建期显式注入守卫）
AUTH_MODE_HEADER = 'X-Auth-Mode'

# AUTH_MODE=off 启动显式守卫横幅（INT-406，对偶前端 INT-181 关机提示口径）
AUTH_MODE_OFF_BANNER = (
    '[SECURITY] AUTH_MODE=off：认证已关闭，所有 API 免认证放行。'
    '生产环境严禁使用；前端须同步注入 VITE_AUTH_MODE=off（INT-181 对偶守卫）。'
)


def log_auth_mode_banner(logger, auth_mode) -> None:
    """AUTH_MODE=off 时打启动显式横幅日志（非 off 不打，静默）。

    Args:
        logger: logging.Logger 实例（服务启动日志）
        auth_mode: 认证模式值（AuthMode 成员或 off|dev|prod 字符串）
    """
    if normalize_auth_mode(auth_mode) == AuthMode.OFF.value:
        logger.warning(AUTH_MODE_OFF_BANNER)


def normalize_auth_mode(value) -> str:
    """校验并归一 auth_mode 取值，非法值抛 ValueError（拒绝魔法字符串）。"""
    if isinstance(value, AuthMode):
        return value.value
    if value not in AUTH_MODE_VALUES:
        raise ValueError(
            f'AUTH_MODE="{value}" 不是合法取值，允许：{" | ".join(AUTH_MODE_VALUES)}')
    return value
