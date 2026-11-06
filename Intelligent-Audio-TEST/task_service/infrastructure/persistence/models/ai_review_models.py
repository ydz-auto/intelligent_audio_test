# -*- coding: utf-8 -*-
"""task_service AI 复核记录 PO（INT-821 / INT-800）

归属：task_service（TestResult 所有权同域，与 test_result_reviews 同域）
表：ai_reviews

- AI 结论是机器判定，无 old→new 改判语义，独立建表不与人工复核留痕
  （test_result_reviews）同表（方案一致性审计已裁定）
- 一条结果可发起多次 AI 复核（幂等复用最近一次结论），追加行不覆盖
- status: pending/running/completed/failed/canceled（AI 复核任务状态）
- verdict: passed/failed/uncertain（AI 判定；uncertain 对应置信度不足）
- confidence NUMERIC(3,2)：0.00~1.00
- adopted/rejected：人工采纳 / 驳回标记（采纳落人工复核语义在 #2 命令侧）
- 冗余 task_id / test_case_id：按任务查复核记录、按用例查历史免回表
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    func, Column, Integer, BigInteger, Numeric, String, Text, DateTime, Index,
)

# 自增主键：SQLite（测试库）仅 INTEGER PRIMARY KEY 自增，PG 用 BIGINT
_PK_BIGINT = BigInteger().with_variant(Integer, 'sqlite')


class AiReview(Base):
    """AI 复核记录行（每次发起一次 AI 复核一条）"""
    __tablename__ = 'ai_reviews'
    __table_args__ = (
        Index('idx_ai_review_task', 'task_id'),
        Index('idx_ai_review_result', 'result_id', 'dimension_id'),
    )
    id = Column(_PK_BIGINT, primary_key=True, autoincrement=True, comment='主键ID')
    result_id = Column(Integer, nullable=False, comment='关联测试结果ID（test_results.id）')
    task_id = Column(Integer, nullable=False, comment='冗余任务ID（按任务查 AI 复核记录）')
    test_case_id = Column(String(50), nullable=True, comment='冗余用例ID')
    dimension_id = Column(Integer, nullable=True, comment='评估维度ID（整体评估 NULL）')
    status = Column(String(20), nullable=False, default='pending',
                    server_default='pending',
                    comment='复核任务状态 pending/running/completed/failed/canceled')
    verdict = Column(String(20), nullable=True, comment='AI 判定 passed/failed/uncertain')
    confidence = Column(Numeric(3, 2), nullable=True, comment='置信度 0.00~1.00')
    reasoning = Column(Text, nullable=True, comment='AI 推理依据')
    adopted = Column(Integer, nullable=False, default=0, server_default='0',
                     comment='是否采纳 0/1')
    adopted_by_user_id = Column(BigInteger, nullable=True, comment='采纳操作人（JWT 透传）')
    adopted_at = Column(DateTime, nullable=True, comment='采纳时间')
    rejected = Column(Integer, nullable=False, default=0, server_default='0',
                      comment='是否驳回 0/1')
    rejected_by_user_id = Column(BigInteger, nullable=True, comment='驳回操作人（JWT 透传）')
    rejected_at = Column(DateTime, nullable=True, comment='驳回时间')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(),
                        nullable=False, comment='发起时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now,
                        nullable=True, comment='更新时间')
