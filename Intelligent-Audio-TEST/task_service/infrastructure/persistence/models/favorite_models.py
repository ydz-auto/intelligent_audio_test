# -*- coding: utf-8 -*-
"""task_service 收藏 PO（INT-141 收藏功能）

归属：task_service（收藏按服务分治：本服务管 task|testcase，
report_service 管 report 其表名为 report_favorites——单库部署下
Base.metadata 表名全局唯一，禁止同名复用）。

- user_id 来自 JWT（x-user-id metadata），AUTH_MODE=off 时为 NULL
- entity_type 取 shared.models.common_enums.EntityType（task/testcase）
- entity_id 统一 String(64)：Task 主键 Integer / TestCase 主键 String(50) 混型，
  存储层统一字符串化，查询侧按实体回转类型
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    Column, Integer, BigInteger, String, DateTime, UniqueConstraint, Index,
)

# 自增主键：SQLite（测试库）仅 INTEGER PRIMARY KEY 自增，PG 用 BIGINT
_PK_BIGINT = BigInteger().with_variant(Integer, 'sqlite')


class Favorite(Base):
    """用户收藏记录（per-user）"""
    __tablename__ = 'favorites'
    __table_args__ = (
        UniqueConstraint('user_id', 'entity_type', 'entity_id',
                         name='uq_favorite_user_entity'),
        Index('idx_favorite_user_type', 'user_id', 'entity_type'),
    )
    id = Column(_PK_BIGINT, primary_key=True, autoincrement=True, comment='主键ID')
    user_id = Column(BigInteger, nullable=False, index=True, comment='收藏者用户ID（JWT，未认证 NULL 禁止写入）')
    entity_type = Column(String(20), nullable=False, comment='实体类型 (task/testcase，见 EntityType 枚举)')
    entity_id = Column(String(64), nullable=False, comment='实体ID（统一字符串化存储）')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='收藏时间')
