# -*- coding: utf-8 -*-
"""重启恢复时判断「写操作是否可安全重放」（§9.2 第 3 条）。

M0 只读：READ 工具可安全重放（无副作用）；WRITE / DESTRUCTIVE 一律不重放，
由 M2 接入业务真实副作用查询后实现。接口在此预留，禁止静默重放写操作。
"""
from abc import ABC, abstractmethod

from agent_service.domain.enums import ToolRisk
from agent_service.domain.model.entities import AgentToolCall


class SideEffectChecker(ABC):
    """判断一次中断的 tool call 能否重放。"""

    @abstractmethod
    def can_replay(self, tool_call: AgentToolCall) -> bool:
        """True 表示可安全重放；False 表示必须先人工确认（M0 写操作恒 False）。"""


class ReadOnlySideEffectChecker(SideEffectChecker):
    """M0 口径：只有 READ 工具允许自动重放。"""

    def can_replay(self, tool_call: AgentToolCall) -> bool:
        return tool_call.risk is ToolRisk.READ
