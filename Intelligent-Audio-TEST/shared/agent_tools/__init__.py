# -*- coding: utf-8 -*-
"""工具 Schema 单一事实源（INT-2453，落地方案 §6.2 / §12.1）。

- ``mcp_registry``：207 个外部 MCP 1:1 工具（INT-2453 谱 205 + INT-2461
  首页只读 2；api_gateway 与 agent_service 共用）；
- ``intent_tools``：31 个内部意图工具（M0 实现 3 个业务 + tool_search；
  M1 各域卡按域启用只读工具，当前含 ``audio_query`` / ``evaluation_query`` /
  ``algorithm_query`` / ``device_query``）；
- ``device_tools``：设备与 SPL 域只读动作表 / Agent 专用 SPL REST 目标；
- ``search``：tool_search 关键词 + 轻量语义索引；
- ``coverage``：MCP 工具 → 意图工具归属矩阵（生成 ``COVERAGE.md``）；
- ``contract``：platform_contract 平台口径事实源。

禁止在服务内复制第二份 Schema。
"""
from shared.agent_tools.intent_tools import (  # noqa: F401
    ENABLED_TOOLS,
    INTENT_TOOL_BY_NAME,
    INTENT_TOOLS,
    IntentTool,
    platform_contract,
    tool_search,
    validate_arguments,
)
from shared.agent_tools.mcp_registry import (  # noqa: F401
    TOOLS as MCP_TOOLS,
    build_body,
    build_path,
    get_tool,
    list_tools,
)

__all__ = [
    'ENABLED_TOOLS', 'INTENT_TOOL_BY_NAME', 'INTENT_TOOLS', 'IntentTool',
    'MCP_TOOLS', 'build_body', 'build_path', 'get_tool', 'list_tools',
    'platform_contract', 'tool_search', 'validate_arguments',
]
