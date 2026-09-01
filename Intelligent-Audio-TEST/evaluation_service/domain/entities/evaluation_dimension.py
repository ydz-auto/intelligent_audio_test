# -*- coding: utf-8 -*-
"""evaluation_service 领域实体（纯领域对象，不依赖 SQLAlchemy / db.Model）

DDD 分层原则：
- domain 层只含纯领域逻辑，不依赖基础设施（DB/HTTP/线程池）
- 领域实体 ≠ PO：PO 是持久化层概念（继承 db.Model），领域实体是领域层概念（纯业务对象）
- Repository 负责在 PO ↔ Entity 之间做转换

本服务核心聚合：
- EvaluationDimension（评估维度定义）— 聚合根
- DimensionScore（维度评分结果）— 实体，属于 EvaluationDimension 聚合
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ===== 领域状态/类型常量（evaluation_service 自有，非任务/用例状态枚举） =====

# DimensionScore.evaluation_status: 维度评估过程状态
SCORE_EVAL_STATUS_PENDING = 'pending'
SCORE_EVAL_STATUS_RUNNING = 'running'
SCORE_EVAL_STATUS_COMPLETED = 'completed'

# DimensionScore.status: 维度评估结论
SCORE_PASSED = 'passed'
SCORE_FAILED = 'failed'

# DimensionSnapshot.api_status: 维度评估 API 在线状态
API_STATUS_ONLINE = 'online'


@dataclass
class ScoringRule:
    """评分规则（值对象）

    对应 PO Dimension.rule 字段的 JSON 结构。
    评分规则类型：
    - direct: 直接取值
    - linear: 线性插值（min/max → score_min/score_max）
    - threshold: 阈值匹配（命中即取对应分数）
    """
    type: str = 'direct'  # direct / linear / threshold
    min: float = 0
    max: float = 1
    score_min: float = 0
    score_max: float = 100
    thresholds: List[Dict[str, float]] = field(default_factory=list)
    # 旧格式兼容：rule JSON 中可能含 rules 列表（condition/value/score）
    rules: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'ScoringRule':
        if not data:
            return cls()
        return cls(
            type=data.get('type', 'direct'),
            min=data.get('min', 0),
            max=data.get('max', 1),
            score_min=data.get('score_min', 0),
            score_max=data.get('score_max', 100),
            thresholds=data.get('thresholds', []) or [],
            rules=data.get('rules', []) or [],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': self.type,
            'min': self.min,
            'max': self.max,
            'score_min': self.score_min,
            'score_max': self.score_max,
            'thresholds': self.thresholds,
            'rules': self.rules,
        }

    # ===== 业务规则（从 Application 层下沉） =====

    _VALID_RULE_CONDITIONS = ['>', '>=', '<', '<=', '==', '!=']

    def validate(self) -> tuple:
        """验证评分规则结构。返回 (is_valid: bool, message: str)。"""
        if not self.rules:
            return True, '验证通过'
        for idx, r in enumerate(self.rules):
            if not isinstance(r, dict):
                return False, f'第 {idx + 1} 条规则必须是一个对象'
            if 'condition' not in r or 'value' not in r or 'score' not in r:
                return False, f'第 {idx + 1} 条规则缺少必要字段 (condition, value, score)'
            if r['condition'] not in self._VALID_RULE_CONDITIONS:
                return False, f"第 {idx + 1} 条规则的条件无效: {r['condition']}"
            if not isinstance(r['value'], (int, float)):
                return False, f'第 {idx + 1} 条规则的阈值必须是数字'
            if not isinstance(r['score'], (int, float)):
                return False, f'第 {idx + 1} 条规则的得分必须是数字'
        return True, '验证通过'

    def calculate(self, test_value) -> float:
        """根据评分规则计算分值。返回匹配的分数，无匹配返回 0。"""
        if not self.rules:
            return 0.0
        if isinstance(test_value, str):
            try:
                test_value = float(test_value)
                if test_value.is_integer():
                    test_value = int(test_value)
            except (ValueError, TypeError):
                pass
        for r in self.rules:
            cond = r.get('condition')
            val = r.get('value')
            s = r.get('score', 0)
            match = False
            if cond == '>':
                match = test_value > val
            elif cond == '>=':
                match = test_value >= val
            elif cond == '<':
                match = test_value < val
            elif cond == '<=':
                match = test_value <= val
            elif cond == '==':
                match = test_value == val
            elif cond == '!=':
                match = test_value != val
            if match:
                return float(s)
        return 0.0


@dataclass
class DimensionSnapshot:
    """维度快照（值对象）

    评估时从 Dimension PO 提取的不可变快照，包含评估所需的最小字段集。
    使用快照而非 PO 引用，避免领域层依赖 ORM。
    """
    id: int
    name: str
    algorithm_type: str
    task_type_code: Optional[str] = None
    dimension_type: str = 'main'  # main / sub
    parent_dimension_id: Optional[int] = None
    category_id: Optional[int] = None
    result_type: int = 1  # 1:数值, 2:布尔, 3:文本
    result_min: Optional[float] = None
    result_max: Optional[float] = None
    decimal_places: Optional[int] = None
    weight: int = 1
    score_unit: str = ''
    statistic_method: str = 'average'  # average / weighted_wer
    rule: ScoringRule = field(default_factory=ScoringRule)
    api_endpoints: List[Dict[str, Any]] = field(default_factory=list)
    api_settings: Optional[Dict[str, Any]] = None
    api_url: Optional[str] = None
    api_status: str = 'online'


@dataclass
class RoundResult:
    """单轮结果引用（值对象）

    评估执行时单轮的原始结果引用，包含从评测 API 拿到的原始响应。
    round_number=None 表示整体评估，0-indexed 表示多轮中的某轮。
    """
    round_number: Optional[int]
    dimension_value: Optional[float] = None  # 维度原始值（如 BLEU 分数）
    api_raw_response: Optional[Dict[str, Any]] = None
    api_request_body: Optional[Dict[str, Any]] = None


@dataclass
class DimensionScore:
    """维度评分结果（实体）

    归属 EvaluationDimension 聚合，表示某次评估中某个维度的得分。
    对应 PO TestResultDimension，但不含持久化字段（id/created_at 等）。
    """
    test_result_id: int
    dimension_id: int
    algorithm_type: str
    round_number: Optional[int] = None
    dimension_value: Optional[float] = None
    score: Optional[float] = None
    status: Optional[str] = None  # passed / failed
    evaluation_status: str = SCORE_EVAL_STATUS_PENDING  # pending / running / completed
    error_message: Optional[str] = None
    rounds: List[RoundResult] = field(default_factory=list)

    def is_completed(self) -> bool:
        return self.evaluation_status == SCORE_EVAL_STATUS_COMPLETED

    def is_multi_round(self) -> bool:
        return self.round_number is None and len(self.rounds) > 0

    def mark_running(self) -> None:
        self.evaluation_status = SCORE_EVAL_STATUS_RUNNING

    def mark_completed(self, score: float, status: str = SCORE_PASSED) -> None:
        self.score = score
        self.status = status
        self.evaluation_status = SCORE_EVAL_STATUS_COMPLETED

    def mark_failed(self, error: str) -> None:
        self.error_message = error
        self.evaluation_status = SCORE_EVAL_STATUS_COMPLETED
        self.status = SCORE_FAILED


@dataclass
class EvaluationDimension:
    """评估维度（聚合根）

    评估维度的核心定义，是 evaluation_service 的核心聚合根。
    包含维度元数据 + 评分规则 + 该维度在某次评估中的得分（DimensionScore）。

    注意：领域层不持有 PO 引用，通过 Repository 加载 PO 后转换为聚合根。
    """
    id: int
    name: str
    algorithm_type: str
    snapshot: DimensionSnapshot
    scores: List[DimensionScore] = field(default_factory=list)

    def add_score(self, score: DimensionScore) -> None:
        """添加一次评估得分"""
        self.scores.append(score)

    def is_active(self) -> bool:
        """维度是否可用（API 在线）"""
        return self.snapshot.api_status == API_STATUS_ONLINE
