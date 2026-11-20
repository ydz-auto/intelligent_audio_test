# -*- coding: utf-8 -*-
"""上下文预算值对象（落地方案 §8.3）。

区段占比（合计 100%）来自配置，不在代码里写死：

| 区段 | 默认上限 |
|---|---|
| system + Skill L1 + 激活正文 | 15% |
| 计划 / scratchpad | 10% |
| 对话历史 | 35% |
| 工具结果 | 30% |
| 安全余量 | 10% |

可用窗口 = 模型窗口 − 输出预留；软 / 硬压缩阈值由 ``ContextWindowResolver``
按可用窗口派生（60% / 80%），换模型时由调用方按新窗口重算，不沿用旧值。
"""
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Mapping, Optional


class ContextSection(str, Enum):
    """上下文预算区段（§8.3）。

    五个区段都参与占比校验，但**当前只有 SYSTEM / DIALOGUE / TOOL_RESULTS
    被实际计入预算**：``SCRATCHPAD``（计划 / scratchpad 块）与 ``RESERVE``
    （安全余量）是给 M1 计划注入与余量预留保留的口径，M2 之前不写入内容，
    只用于校验占比之和为 1.0。不要因为「这里有枚举」就认为计划块已被预算。
    """

    SYSTEM = 'system'
    SCRATCHPAD = 'scratchpad'  # 计划 / scratchpad 注入（M1 口径，当前只占位）
    DIALOGUE = 'dialogue'
    TOOL_RESULTS = 'tool_results'
    RESERVE = 'reserve'  # 安全余量（不写入内容）


@dataclass(frozen=True)
class SectionRatios:
    """区段上限占比（sum == 1.0，由配置构造）。"""

    system: float = 0.15
    scratchpad: float = 0.10
    dialogue: float = 0.35
    tool_results: float = 0.30
    reserve: float = 0.10

    @classmethod
    def from_dict(cls, data: Optional[Mapping]) -> 'SectionRatios':
        data = data or {}
        return cls(
            system=float(data.get('system', 0.15)),
            scratchpad=float(data.get('scratchpad', 0.10)),
            dialogue=float(data.get('dialogue', 0.35)),
            tool_results=float(data.get('tool_results', 0.30)),
            reserve=float(data.get('reserve', 0.10)),
        )

    def as_dict(self) -> Dict[str, float]:
        return {
            ContextSection.SYSTEM.value: self.system,
            ContextSection.SCRATCHPAD.value: self.scratchpad,
            ContextSection.DIALOGUE.value: self.dialogue,
            ContextSection.TOOL_RESULTS.value: self.tool_results,
            ContextSection.RESERVE.value: self.reserve,
        }

    def validate(self, tolerance: float = 1e-6) -> None:
        values = self.as_dict()
        if any(v < 0 for v in values.values()):
            raise ValueError('上下文区段占比不能为负数')
        if abs(sum(values.values()) - 1.0) > tolerance:
            raise ValueError(
                f'上下文区段占比之和必须为 1.0，当前 {sum(values.values()):.4f}')


@dataclass(frozen=True)
class ContextBudget:
    """一次模型调用的上下文预算快照（按有效窗口 W 派生）。"""

    window: int
    output_reserve: int
    available: int
    total_token_budget: int
    soft_threshold: int
    hard_threshold: int
    ratios: SectionRatios
    sections: Mapping[ContextSection, int]
    window_source: Optional[str] = None

    def section_limit(self, section: ContextSection) -> int:
        return int(self.sections.get(section, 0))

    def exceeds_soft(self, tokens: int) -> bool:
        return self.soft_threshold > 0 and tokens > self.soft_threshold

    def exceeds_hard(self, tokens: int) -> bool:
        return self.hard_threshold > 0 and tokens > self.hard_threshold

    def to_dict(self) -> Dict[str, int]:
        data: Dict[str, int] = {
            'context_window': self.window,
            'output_reserve': self.output_reserve,
            'available_tokens': self.available,
            'token_budget': self.total_token_budget,
            'compaction_soft_tokens': self.soft_threshold,
            'compaction_hard_tokens': self.hard_threshold,
        }
        for section, limit in self.sections.items():
            data[f'section_{section.value}'] = int(limit)
        return data


__all__ = [
    'ContextBudget', 'ContextSection', 'SectionRatios',
]
