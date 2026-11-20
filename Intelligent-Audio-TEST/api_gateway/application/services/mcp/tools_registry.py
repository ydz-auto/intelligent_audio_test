# -*- coding: utf-8 -*-
"""兼容入口：MCP 工具注册表已迁至 ``shared/agent_tools``（INT-2453）。

单一事实源：``shared/agent_tools/mcp_registry.py``。本模块只做 re-export，
不再保存任何 Schema；外部 ``POST /api/v1/mcp`` 的 tools/list / tools/call
行为与迁移前逐字节一致。
"""
from shared.agent_tools.mcp_registry import (  # noqa: F401
    TOOLS,
    _tool,
    build_body,
    build_path,
    get_tool,
    list_tools,
)

__all__ = [
    'TOOLS', '_tool', 'build_body', 'build_path', 'get_tool', 'list_tools',
]
