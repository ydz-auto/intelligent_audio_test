# -*- coding: utf-8 -*-
"""Run 级预算值对象（§9.3）。

所有阈值来自配置，不在代码里硬编码；实体只负责记录与判定。
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional


BUDGET_ROUNDS = 'max_rounds'
BUDGET_TOOL_CALLS = 'max_tool_calls'
BUDGET_TOKENS = 'max_tokens'
BUDGET_DURATION = 'max_duration_seconds'
BUDGET_OUTPUT_BYTES = 'max_output_bytes'

_BUDGET_KEYS = (
    BUDGET_ROUNDS, BUDGET_TOOL_CALLS, BUDGET_TOKENS,
    BUDGET_DURATION, BUDGET_OUTPUT_BYTES,
)


@dataclass(frozen=True)
class RunBudget:
    """一次 Run 的预算上限；从配置解析后可随 run 落库（agent_run.budget）。"""

    max_rounds: int
    max_tool_calls: int
    max_tokens: int
    max_duration_seconds: int
    max_output_bytes: int

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'RunBudget':
        data = data or {}
        return cls(**{key: int(data.get(key, 0)) for key in _BUDGET_KEYS})

    def to_dict(self) -> Dict[str, int]:
        return {
            BUDGET_ROUNDS: self.max_rounds,
            BUDGET_TOOL_CALLS: self.max_tool_calls,
            BUDGET_TOKENS: self.max_tokens,
            BUDGET_DURATION: self.max_duration_seconds,
            BUDGET_OUTPUT_BYTES: self.max_output_bytes,
        }

    def with_max_tokens(self, max_tokens: int) -> 'RunBudget':
        """按有效上下文窗口重算总 token 上限（§8.3：默认 2×W / Auto 4×W）。"""
        return RunBudget(
            max_rounds=self.max_rounds,
            max_tool_calls=self.max_tool_calls,
            max_tokens=int(max_tokens),
            max_duration_seconds=self.max_duration_seconds,
            max_output_bytes=self.max_output_bytes,
        )

    def tightened(self, overrides: Optional[Dict[str, Any]]) -> 'RunBudget':
        """按请求侧给定的上限**收紧**预算（§9.4：请求不可放宽）。

        只接受已知预算键；``0`` / 负数 / 缺省视为「不覆盖」（不能让调用方把
        某一维度关掉），正数取 ``min(服务端默认, 请求值)``。未知键抛
        ``ValueError``，由接口层转 400（不静默忽略，避免调用方以为生效）。
        """
        if not overrides:
            return self
        data = self.to_dict()
        for key, raw in overrides.items():
            if key not in _BUDGET_KEYS:
                raise ValueError(f'未知预算项：{key}')
            if raw is None:
                continue
            try:
                value = int(raw)
            except (TypeError, ValueError):
                raise ValueError(f'预算项 {key} 必须为整数')
            if value <= 0:
                continue
            current = data[key]
            data[key] = value if current <= 0 else min(current, value)
        return RunBudget.from_dict(data)

    @staticmethod
    def _exceeded(value: int, limit: int) -> bool:
        # limit <= 0 表示该维度不启用（配置可关闭单个预算）
        return limit > 0 and value >= limit

    def check_rounds(self, rounds: int) -> Optional[str]:
        return BUDGET_ROUNDS if self._exceeded(rounds, self.max_rounds) else None

    def check_tool_calls(self, calls: int) -> Optional[str]:
        return BUDGET_TOOL_CALLS if self._exceeded(calls, self.max_tool_calls) else None

    def check_tokens(self, total_tokens: int) -> Optional[str]:
        return BUDGET_TOKENS if self._exceeded(total_tokens, self.max_tokens) else None

    def check_duration(self, elapsed_seconds: float) -> Optional[str]:
        return BUDGET_DURATION if self._exceeded(elapsed_seconds, self.max_duration_seconds) else None

    def check_output_bytes(self, output_bytes: int) -> Optional[str]:
        return BUDGET_OUTPUT_BYTES if self._exceeded(output_bytes, self.max_output_bytes) else None
