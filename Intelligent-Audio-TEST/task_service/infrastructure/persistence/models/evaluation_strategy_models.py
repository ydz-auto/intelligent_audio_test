# -*- coding: utf-8 -*-
"""task_service 评估策略 PO 定义（INT-590）

归属：task_service（用例域，评估配置跟随用例生命周期）
表：evaluation_strategies

背景：用例编辑抽屉「整体评估维度 + 全局背景噪声」抽为可复用「评估策略」实体；
策略 = { 整体评估维度（主-子维度/权重/阈值/Judge/Prompt）、全局背景噪声 } 的
命名可复用包，用例引用策略并可覆盖个别字段（写时物化）。维度定义仍留
evaluation_service.dimensions 表，策略只打包「引用哪个维度 + 用例级参数
（weight/threshold/llmJudgeConfig）」，是 case 级数据模板，不复制定义。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    func, Column, String, Text, Boolean, DateTime, JSON, BigInteger,
)


class EvaluationStrategy(Base):
    """评估策略模型 (Evaluation Strategy Model)

    策略 config 与用例 config.dimensions / config.background_noise **同构**
    （复用现有协议字段，非宽松 Dict）：
    config = {
        "dimensions": [{"id", "name", "weight", "threshold", "round_scope"?, "llmJudgeConfig"?}],
        "background_noise": {...}
    }
    软删除同 TestCase（deleted / deleted_at / deleted_by_user_id）。
    """
    __tablename__ = 'evaluation_strategies'
    id = Column(String(50), primary_key=True, comment='策略唯一ID')
    name = Column(String(150), nullable=False, comment='策略名称')
    description = Column(Text, comment='策略描述')
    algorithm_type = Column(String(50), nullable=True, comment='策略适用算法类型（前端策略列表过滤）')
    enabled = Column(Boolean, nullable=False, default=True, comment='启用/禁用')
    config = Column(JSON, nullable=False, comment='评估配置 JSON（dimensions/background_noise，与用例 config 同构）')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(), onupdate=utc8now, nullable=False, comment='更新时间')
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')
    deleted_at = Column(DateTime, nullable=True, comment='逻辑删除时间（60天后硬删除）')
    deleted_by_user_id = Column(BigInteger, nullable=True, comment='执行删除操作的用户ID（JWT，INT-590）')
