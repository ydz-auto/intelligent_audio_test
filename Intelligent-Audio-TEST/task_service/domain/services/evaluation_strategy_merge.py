# -*- coding: utf-8 -*-
"""评估策略覆盖合并领域服务（INT-590 写时物化）。

保存用例时合并策略 config 与用例级 strategy_overrides，并**落库解析结果**
（对齐验收#2「覆盖字段与策略字段合并后正确落库」）：
- dimensions：策略维度为底，按 dimension id 逐字段覆盖
  （weight/threshold/llmJudgeConfig 只覆盖传入字段）；overrides 新 id 追加
- background_noise：overrides 非空则整块替换，空则继承策略
- 解析结果写回 config.dimensions / config.background_noise，strategy_id +
  overrides 另列落库 → 下游（e2e/评估/报告）零改动，任务创建快照天然含
  解析后配置

规格拍板点（已固化）：
- P1 策略编辑不回灌已引用用例（用例/任务均快照语义）；「批量同步策略变更」
  另开增强卡
- P2 overrides V1 不支持显式移除策略维度（覆盖+追加即可，移除走整体维度编辑）
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional


class EvaluationStrategyMergeService:
    """策略 config 与用例 overrides 的合并领域服务（纯函数，无副作用）。"""

    # overrides 可逐字段覆盖的维度字段（P2：不支持显式移除策略维度）
    _DIMENSION_OVERRIDE_FIELDS = ('weight', 'threshold', 'llmJudgeConfig')

    @classmethod
    def resolve(cls, strategy_config: Optional[dict],
                overrides: Optional[dict]) -> dict:
        """合并策略配置与用例级覆盖，返回解析后的策略配置。

        Args:
            strategy_config: 策略的 config JSON
                {dimensions: [{id,name,weight,threshold,round_scope?,llmJudgeConfig?}],
                 background_noise: {...}}
            overrides: 用例级覆盖 JSON
                {dimensions: [{id, weight?, threshold?, llmJudgeConfig?}],
                 background_noise: {...} | {}}

        Returns:
            解析后的配置 {dimensions: [...], background_noise: {...}}。
            策略为空时返回空 dict（调用方不应引用不存在的策略）。
        """
        if not strategy_config:
            return {}
        if not overrides:
            return copy.deepcopy(strategy_config)

        result = copy.deepcopy(strategy_config)
        strategy_dims = result.get('dimensions') or []

        # ---- dimensions：策略为底，按 dimension id 逐字段覆盖；新 id 追加 ----
        override_dims = overrides.get('dimensions')
        if override_dims:
            dim_map = {d.get('id'): d for d in strategy_dims if isinstance(d, dict)}
            for od in override_dims:
                if not isinstance(od, dict):
                    continue
                oid = od.get('id')
                if oid is None:
                    continue
                if oid in dim_map:
                    base = dim_map[oid]
                    for field in cls._DIMENSION_OVERRIDE_FIELDS:
                        if field in od:
                            base[field] = od[field]
                else:
                    # overrides 新 id 追加（P2：不支持显式移除，仅覆盖+追加）
                    strategy_dims.append(dict(od))

        # ---- background_noise：overrides 非空则整块替换，空则继承策略 ----
        bn_override = overrides.get('background_noise')
        if bn_override is not None and len(bn_override) > 0:
            result['background_noise'] = bn_override

        return result

    @classmethod
    def validate_overrides(cls, overrides: Optional[dict]) -> Optional[str]:
        """校验 strategy_overrides 结构合法性，返回错误消息或 None。

        合法结构：{dimensions: [{id, weight?, threshold?, llmJudgeConfig?}],
                    background_noise: {...}}
        overrides 仅声明用例级覆盖字段；维度条目必须带 id。
        """
        if overrides is None:
            return None
        if not isinstance(overrides, dict):
            return 'strategy_overrides 必须是对象'
        override_dims = overrides.get('dimensions')
        if override_dims is not None:
            if not isinstance(override_dims, list):
                return 'strategy_overrides.dimensions 必须是数组'
            for i, od in enumerate(override_dims):
                if not isinstance(od, dict) or od.get('id') is None:
                    return f"strategy_overrides.dimensions 第 {i + 1} 项缺少 id"
        bn = overrides.get('background_noise')
        if bn is not None and not isinstance(bn, dict):
            return 'strategy_overrides.background_noise 必须是对象'
        return None


# 模块级单例
evaluation_strategy_merge_service = EvaluationStrategyMergeService()
