# -*- coding: utf-8 -*-
"""task_service 测试结果人工复核留痕 PO（INT-340）

归属：task_service（TestResult 所有权同域）
表：test_result_reviews

- 一条结果多次复核：每次复核的每个字段改判追加一行，历史不覆盖
- field_name 取 review 改判字段：execution_status / evaluation_status
- comment 为复核备注（负责人拍板 2026-10-15：必填）
- 冗余 task_id / test_case_id：按任务查复核计数（覆盖提醒）与按用例查历史免回表
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    func, Column, Integer, BigInteger, String, Text, DateTime, Index,
)

# 自增主键：SQLite（测试库）仅 INTEGER PRIMARY KEY 自增，PG 用 BIGINT
_PK_BIGINT = BigInteger().with_variant(Integer, 'sqlite')


class TestResultReview(Base):
    """测试结果人工复核留痕行（每条结果每次字段改判一条）"""
    __tablename__ = 'test_result_reviews'
    __table_args__ = (
        Index('idx_review_task', 'task_id'),
        Index('idx_review_result', 'result_id'),
    )
    id = Column(_PK_BIGINT, primary_key=True, autoincrement=True, comment='主键ID')
    result_id = Column(Integer, nullable=False, comment='关联测试结果ID（test_results.id）')
    task_id = Column(Integer, nullable=False, comment='冗余任务ID（按任务查复核计数）')
    test_case_id = Column(String(50), nullable=True, comment='冗余用例ID')
    field_name = Column(String(30), nullable=False, comment='改判字段 (execution_status/evaluation_status)')
    old_value = Column(String(20), nullable=True, comment='改判前原值')
    new_value = Column(String(20), nullable=False, comment='改判后新值')
    comment = Column(Text, nullable=False, comment='复核备注（必填）')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='复核操作人（JWT 透传，未认证 NULL）')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='复核时间')
