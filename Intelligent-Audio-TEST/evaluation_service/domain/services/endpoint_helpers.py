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
