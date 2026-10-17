# -*- coding: utf-8 -*-
"""api_gateway infrastructure 持久化模型包（INT-620）。

当前仅 system_options（系统选项 KV，网关直管表）；后续网关直管表按此目录登记。
"""
from api_gateway.infrastructure.models.system_option_model import SystemOption  # noqa: F401

__all__ = ['SystemOption']
