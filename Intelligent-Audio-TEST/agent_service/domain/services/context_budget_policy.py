# -*- coding: utf-8 -*-
"""上下文预算策略（§8.3）：有效窗口 → 区段上限 / 软硬阈值。

唯一事实源是 ``ContextWindowResolver``（INT-2488）：本模块只负责把解析出的
窗口与输出预留映射成 ``ContextBudget``，不另算一套阈值。所有比例、乘数来自
配置；换模型 / 换供应商时调用方必须按新窗口重新调用 ``build``。
"""
from typing import Optional

from agent_service.domain.model.context_budget import (
    ContextBudget, ContextSection, SectionRatios,
)
from agent_service.domain.services.context_window_resolver import (
    ContextWindowResolver,
)

DEFAULT_SOFT_RATIO = 0.60
DEFAULT_HARD_RATIO = 0.80
DEFAULT_TOKEN_BUDGET_MULTIPLIER = 2


class ContextBudgetPolicy:
    """按有效上下文窗口派生一次模型调用的预算。"""

    def __init__(self, resolver: ContextWindowResolver, *,
                 ratios: Optional[SectionRatios] = None,
                 soft_ratio: float = DEFAULT_SOFT_RATIO,
                 hard_ratio: float = DEFAULT_HARD_RATIO,
                 token_budget_multiplier: int = DEFAULT_TOKEN_BUDGET_MULTIPLIER):
        self._resolver = resolver
        self._ratios = ratios or SectionRatios()
        self._ratios.validate()
        self._soft_ratio = float(soft_ratio)
        self._hard_ratio = float(hard_ratio)
        self._token_multiplier = int(token_budget_multiplier)
        if not 0 < self._soft_ratio < self._hard_ratio <= 1:
            raise ValueError('压缩软 / 硬阈值比例必须满足 0 < soft < hard <= 1')
        if self._token_multiplier <= 0:
            raise ValueError('token 预算乘数必须为正数')

    @property
    def ratios(self) -> SectionRatios:
        return self._ratios

    def build(self, window: int, output_reserve: int, *,
              window_source: Optional[str] = None,
              token_budget_multiplier: Optional[int] = None) -> ContextBudget:
        """按有效窗口构造预算；``output_reserve`` 为单轮输出预留。"""
        window = int(window)
        output_reserve = max(0, int(output_reserve))
        if window <= 0:
            raise ValueError('有效上下文窗口必须为正数')
        available = max(0, window - output_reserve)
        multiplier = (self._token_multiplier
                      if token_budget_multiplier is None
                      else int(token_budget_multiplier))
        total = ContextWindowResolver.token_budget(window, multiplier)
        soft, hard = ContextWindowResolver.compaction_thresholds(
            window, output_reserve,
            soft_ratio=self._soft_ratio, hard_ratio=self._hard_ratio)
        sections = {
            ContextSection.SYSTEM: int(window * self._ratios.system),
            ContextSection.SCRATCHPAD: int(window * self._ratios.scratchpad),
            ContextSection.DIALOGUE: int(window * self._ratios.dialogue),
            ContextSection.TOOL_RESULTS: int(window * self._ratios.tool_results),
            ContextSection.RESERVE: int(window * self._ratios.reserve),
        }
        return ContextBudget(
            window=window, output_reserve=output_reserve, available=available,
            total_token_budget=total, soft_threshold=soft, hard_threshold=hard,
            ratios=self._ratios, sections=sections, window_source=window_source,
        )


__all__ = ['ContextBudgetPolicy']
