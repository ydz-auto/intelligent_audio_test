# -*- coding: utf-8 -*-
"""RealtimePacingService — Realtime 输出调输入节奏服务（INT-475）

驱动输入推送节奏的输出信号来自被测厂商 Realtime API 实时输出
（RealtimeWSClient 归一化事件实例内回流），执行器据此调整后续音频输入帧
的推送时机，而非固定间隔盲推（评审修订①：数据面实例内闭环，
evaluation_service 保持后置）。

纯逻辑无 IO：输入为 case_config / api_config.meta / 全局配置与事件，输出为
节奏上下文与决策；recv() 轮询由 executor 编排（评审修订③：内部事件队列 +
recv 轮询回流，排除 SSE 观测链路）。

节奏策略（RealtimePacingStrategy，common_enums.py + 前端 enums.ts 镜像）：
- FIXED            恒定节奏（默认 = 现状，回归基准）
- WAIT_TURN_END    模型输出 turn 进行中则暂停输入推流，turn 结束后续推
- ALLOW_BARGE_IN   输入推流中模型提前回话/打断 → 收敛输入推流
- TIMEOUT_FALLBACK 模型无输出/无 turn 结束时按配置超时兜底，不无限等待

配置优先级：case_config['pacing'] → api_config.meta['pacing'] →
realtime_session 全局配置 → 默认值。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, FrozenSet, Union

from shared.models.common_enums import RealtimePacingStrategy

logger = logging.getLogger(__name__)

# 配置键名（全局 realtime_session 段 / case_config.pacing / api_config.meta.pacing 共用）
KEY_STRATEGY = 'pacing_strategy'
KEY_TURN_END_WAIT = 'turn_end_wait_timeout_s'
KEY_FALLBACK_TIMEOUT = 'pacing_fallback_timeout_s'

# 单值 / 组合值均可接受：字符串（可逗号分隔）或字符串列表
StrategyValue = Union[str, list, tuple, set]


@dataclass(frozen=True)
class RealtimePacingContext:
    """解析后的节奏上下文（不可变值对象）。

    strategies 为 RealtimePacingStrategy 成员集合；仅含 FIXED 时 = 恒定节奏
    （执行器不消费事件，零回归基线）。
    """
    strategies: FrozenSet[RealtimePacingStrategy] = field(
        default_factory=lambda: frozenset({RealtimePacingStrategy.FIXED}))
    turn_end_wait_timeout_s: float = 60.0
    pacing_fallback_timeout_s: float = 30.0

    def has(self, strategy: RealtimePacingStrategy) -> bool:
        return strategy in self.strategies

    def is_fixed(self) -> bool:
        return self.strategies == {RealtimePacingStrategy.FIXED}

    def effective_turn_end_timeout(self) -> float:
        """WAIT_TURN_END 的 turn 结束等待上限。

        TIMEOUT_FALLBACK 组合时取兜底超时（更紧的安全网），否则取
        turn_end_wait_timeout_s —— 有兜底时不无限等待（INT-475 验收）。
        """
        if self.has(RealtimePacingStrategy.TIMEOUT_FALLBACK):
            return min(self.turn_end_wait_timeout_s, self.pacing_fallback_timeout_s)
        return self.turn_end_wait_timeout_s

    def effective_fallback_end_timeout(self, default: float) -> float:
        """TIMEOUT_FALLBACK 下 wait_ai_complete 的收口超时（模型无输出兜底）。"""
        if self.has(RealtimePacingStrategy.TIMEOUT_FALLBACK):
            return min(float(default), self.pacing_fallback_timeout_s)
        return default


class RealtimePacingService:
    """节奏策略解析服务（域服务，无 IO）"""

    DEFAULT_TURN_END_WAIT_S = 60.0
    DEFAULT_FALLBACK_S = 30.0

    def resolve(self, api_config, case_config,
                cfg_getter: Callable[..., object]) -> RealtimePacingContext:
        """解析节奏上下文：case_config['pacing'] → meta['pacing'] → 全局 → 默认。

        cfg_getter(key, default) 为全局配置读取（realtime_session 段，由执行器
        _cfg 注入），保持配置单源。
        """
        case_pacing = {}
        if isinstance(case_config, dict):
            case_pacing = case_config.get('pacing') or {}
        meta = getattr(api_config, 'meta', None) or {}
        meta_pacing = meta.get('pacing') or {}

        strategy_raw = (
            case_pacing.get(KEY_STRATEGY)
            or meta_pacing.get(KEY_STRATEGY)
            or cfg_getter(KEY_STRATEGY, RealtimePacingStrategy.FIXED.value)
        )
        turn_end = self._first_set(case_pacing, meta_pacing, cfg_getter,
                                   KEY_TURN_END_WAIT, self.DEFAULT_TURN_END_WAIT_S)
        fallback = self._first_set(case_pacing, meta_pacing, cfg_getter,
                                   KEY_FALLBACK_TIMEOUT, self.DEFAULT_FALLBACK_S)
        return RealtimePacingContext(
            strategies=self._normalize_strategies(strategy_raw),
            turn_end_wait_timeout_s=float(turn_end),
            pacing_fallback_timeout_s=float(fallback),
        )

    # ── 内部 ──
    @staticmethod
    def _first_set(case_pacing, meta_pacing, cfg_getter, key, default):
        value = case_pacing.get(key)
        if value is None:
            value = meta_pacing.get(key)
        if value is None:
            value = cfg_getter(key, default)
        return default if value is None else value

    @classmethod
    def _normalize_strategies(cls, raw: StrategyValue) -> FrozenSet[RealtimePacingStrategy]:
        """配置值 → 策略集合：字符串（可逗号分隔）/ 列表 / 集合。

        FIXED 与动态策略互斥：含任一动态策略时 FIXED 被丢弃；未知值告警忽略。
        """
        items: list = []
        if isinstance(raw, str):
            items = [s.strip() for s in raw.split(',') if s.strip()]
        elif isinstance(raw, (list, tuple, set)):
            items = [str(s).strip() for s in raw if str(s).strip()]
        members = set()
        for item in items:
            try:
                members.add(RealtimePacingStrategy(item))
            except ValueError:
                logger.warning('未知 RealtimePacingStrategy: %s，已忽略', item)
        members.discard(RealtimePacingStrategy.FIXED)
        return frozenset(members) if members else frozenset({RealtimePacingStrategy.FIXED})
