# -*- coding: utf-8 -*-
"""评估上下文值对象

包含评分规则、维度快照、轮次结果等值对象。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ScoringRule:
    """打分规则值对象
    - direct: 直接取值
    - linear: 线性映射
    - threshold: 阈值判断
    """
    rule_type: str = "direct"  # direct / linear / threshold
    formula: Optional[Dict[str, Any]] = None  # 线性映射参数 (y = ax + b)
    thresholds: Optional[List[Dict[str, Any]]] = None  # 阈值列表

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "ScoringRule":
        if not data:
            return cls()
        return cls(
            rule_type=data.get('rule_type', 'direct'),
            formula=data.get('formula'),
            thresholds=data.get('thresholds'),
        )


@dataclass
class DimensionSnapshot:
    """维度规则快照 — 评估时从 Dimension 实体生成快照"""
    dimension_id: int
    name: str
    rule: Optional[Dict[str, Any]] = None
    api_settings: Optional[Dict[str, Any]] = None
    params: Optional[Dict[str, Any]] = None
    score_range: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: dict) -> "DimensionSnapshot":
        return cls(
            dimension_id=data.get('dimension_id') or data.get('id', 0),
            name=data.get('name', ''),
            rule=data.get('rule'),
            api_settings=data.get('api_settings'),
            params=data.get('params'),
            score_range=data.get('score_range'),
        )


@dataclass
class RoundResult:
    """单轮原始结果引用"""
    round_number: int
    result_id: Optional[int] = None
    algorithm_result: Optional[Dict[str, Any]] = None
    reference_data: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: dict) -> "RoundResult":
        return cls(
            round_number=data.get('round_number', 0),
            result_id=data.get('result_id'),
            algorithm_result=data.get('algorithm_result'),
            reference_data=data.get('reference_data'),
        )


@dataclass
class ScoreRange:
    """评分范围值对象"""
    result_min: float = 0.0
    result_max: float = 100.0
    decimal_places: int = 2
    weight: float = 1.0

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "ScoreRange":
        if not data:
            return cls()
        return cls(
            result_min=data.get('result_min', 0.0),
            result_max=data.get('result_max', 100.0),
            decimal_places=data.get('decimal_places', 2),
            weight=data.get('weight', 1.0),
        )


@dataclass
class ApiSettings:
    """维度级 API 配置快照"""
    endpoint: str = ""
    method: str = "POST"
    headers: Dict[str, str] = field(default_factory=dict)
    timeout: int = 30
    retry_count: int = 0

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "ApiSettings":
        if not data:
            return cls()
        return cls(
            endpoint=data.get('endpoint', ''),
            method=data.get('method', 'POST'),
            headers=data.get('headers', {}),
            timeout=data.get('timeout', 30),
            retry_count=data.get('retry_count', 0),
        )
