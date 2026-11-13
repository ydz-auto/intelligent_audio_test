# -*- coding: utf-8 -*-
"""重启恢复时判断「写操作是否可安全重放」（§9.2 第 3 条）。

READ 工具无副作用，可安全重放；WRITE / DESTRUCTIVE 一律不自动重放
（INT-2466 起写操作走审批链，但「执行到一半被杀」的写仍禁止自动重试：
先由业务真实副作用查询判定，当前实现保守判定为「需人工确认」，run 以
RESTART_WRITE_UNVERIFIED 收口）。接口在此固定，域写卡接入真实副作用
查询后不允许放宽成无条件重放。
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
