# -*- coding: utf-8 -*-
"""端点配置工具函数（Domain 层）

纯函数操作 dict，不依赖 infrastructure 层。
"""


def get_endpoint_url(endpoint_item):
    """从端点配置项中提取URL，兼容 'url' 和 'endpoint' 两种字段名"""
    if not endpoint_item:
        return None
    return endpoint_item.get('url') or endpoint_item.get('endpoint')


def get_endpoint_field(endpoint_item, field_name, fallback_camel=None, default=None):
    """从端点配置项中提取字段值，兼容下划线和驼峰命名"""
    if not endpoint_item:
        return default
    val = endpoint_item.get(field_name)
    if val is None and fallback_camel:
        val = endpoint_item.get(fallback_camel)
    return val if val is not None else default


# 维度 api_settings.timeout 的单位是毫秒（前端「超时(ms)」表单，缺省 30000）。
# 出站请求（requests）按秒计，缺省沿用历史硬编码的 10 秒。
DEFAULT_API_TIMEOUT_SECONDS = 10
MIN_API_TIMEOUT_SECONDS = 0.1


def get_api_timeout_seconds(api_settings, default_seconds=DEFAULT_API_TIMEOUT_SECONDS):
    """把维度 api_settings.timeout（毫秒）换算成出站请求的超时秒数。

    INT-2287：此前 api_settings.timeout 从未被使用，评估请求一律硬编码 10s，
    维度上配置的超时（当前 30000ms）不生效。
    缺省 / 非数字 / 非正数回落 default_seconds。
    """
    raw = api_settings.get('timeout') if isinstance(api_settings, dict) else None
    try:
        timeout_ms = float(raw)
    except (TypeError, ValueError):
        return default_seconds
    if timeout_ms <= 0:
        return default_seconds
    return max(timeout_ms / 1000.0, MIN_API_TIMEOUT_SECONDS)
