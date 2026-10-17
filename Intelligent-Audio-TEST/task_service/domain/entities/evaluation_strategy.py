# -*- coding: utf-8 -*-
"""EvaluationStrategy 领域实体 — 评估策略（INT-590）

策略 = { 整体评估维度（主-子维度/权重/阈值/Judge/Prompt）、全局背景噪声 } 的
命名可复用包，属于 task_service 用例域。用例引用策略并可覆盖个别字段，
覆盖语义见 application/evaluation_strategy/strategy_merge_service.py（写时物化）。

维度定义（rule/api_settings/主-子层级/input_params）仍留 evaluation_service
dimensions 表；策略只打包「引用哪个维度 + 用例级参数（weight/threshold/
llmJudgeConfig）」，是 case 级数据模板，不复制定义。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EvaluationStrategyEntity:
    """评估策略实体（非聚合根）

    与 TestCase 同构的软删除语义；config 结构与用例 config.dimensions /
    config.background_noise 同构（复用现有协议字段，非宽松 Dict）。
    """
    id: str
    name: str
    config: Dict[str, Any]
    description: Optional[str] = None
    algorithm_type: Optional[str] = None
    enabled: bool = True
    created_by_user_id: Optional[int] = None
    updated_by_user_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    deleted: bool = False
    deleted_at: Optional[str] = None
    deleted_by_user_id: Optional[int] = None
    # 关联用例计数（列表/删除保护同源，查询侧填充，非持久化字段）
    referenced_case_count: int = 0

    @classmethod
    def from_orm(cls, po) -> "EvaluationStrategyEntity":
        """从 infrastructure PO 转换为领域实体（依赖倒置：领域不引用 PO 类型）。"""
        if po is None:
            return None
        return cls(
            id=po.id,
            name=po.name,
            description=po.description,
            algorithm_type=getattr(po, 'algorithm_type', None),
            enabled=bool(getattr(po, 'enabled', True)),
            config=po.config or {},
            created_by_user_id=getattr(po, 'created_by_user_id', None),
            updated_by_user_id=getattr(po, 'updated_by_user_id', None),
            created_at=po.created_at.isoformat() if getattr(po, 'created_at', None) else None,
            updated_at=po.updated_at.isoformat() if getattr(po, 'updated_at', None) else None,
            deleted=bool(getattr(po, 'deleted', False)),
            deleted_at=po.deleted_at.isoformat() if getattr(po, 'deleted_at', None) else None,
            deleted_by_user_id=getattr(po, 'deleted_by_user_id', None),
        )

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 API DTO（snake_case，网关 schema 层再转 camelCase）。"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'algorithm_type': self.algorithm_type,
            'enabled': self.enabled,
            'config': self.config,
            'created_by_user_id': self.created_by_user_id,
            'updated_by_user_id': self.updated_by_user_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'referenced_case_count': self.referenced_case_count,
        }


@dataclass
class StrategyDimension:
    """策略维度条目（与用例 config.dimensions 同构）

    weight/threshold/llmJudgeConfig 为用例级参数（覆盖语义按字段粒度）；
    round_scope 标注多轮整体评估口径（multi）或逐轮口径（single）。
    llmJudgeConfig 目前仅前端 UI 概念，后端评估实际取维度 input_params
    默认值（endpoint_worker.py:350）；本卡结构化该字段不影响执行，未消费。
    """
    id: int
    name: str = ''
    weight: Optional[float] = None
    threshold: Optional[float] = None
    round_scope: Optional[str] = None
    llmJudgeConfig: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "StrategyDimension":
        data = data or {}
        return cls(
            id=data.get('id'),
            name=data.get('name', ''),
            weight=data.get('weight'),
            threshold=data.get('threshold'),
            round_scope=data.get('round_scope'),
            llmJudgeConfig=data.get('llmJudgeConfig'),
        )

    def to_dict(self) -> Dict[str, Any]:
        result = {'id': self.id, 'name': self.name}
        if self.weight is not None:
            result['weight'] = self.weight
        if self.threshold is not None:
            result['threshold'] = self.threshold
        if self.round_scope is not None:
            result['round_scope'] = self.round_scope
        if self.llmJudgeConfig is not None:
            result['llmJudgeConfig'] = self.llmJudgeConfig
        return result


@dataclass
class StrategyConfig:
    """策略配置值对象 — {dimensions, background_noise}

    与用例 config.dimensions / config.background_noise **同构**（复用现有
    协议字段）。非宽松 Dict：维度条目经 StrategyDimension 结构化。
    """
    dimensions: List[StrategyDimension] = field(default_factory=list)
    background_noise: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "StrategyConfig":
        data = data or {}
        return cls(
            dimensions=[
                StrategyDimension.from_dict(d) for d in data.get('dimensions', [])
                if isinstance(d, dict)
            ],
            background_noise=data.get('background_noise'),
        )

    def to_dict(self) -> Dict[str, Any]:
        result = {}
        if self.dimensions:
            result['dimensions'] = [d.to_dict() for d in self.dimensions]
        if self.background_noise is not None:
            result['background_noise'] = self.background_noise
        return result
