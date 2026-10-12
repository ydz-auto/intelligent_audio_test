# -*- coding: utf-8 -*-
"""report_service 收藏 PO（INT-141 收藏功能）

归属：report_service（收藏按服务分治：本服务管 report）。
表名 report_favorites 而非 favorites：单库部署下 Base.metadata
表名全局唯一，task_service 已占用 favorites（task|testcase）。

- user_id 来自 JWT（x-user-id metadata），AUTH_MODE=off 时为 NULL
- entity_type 固定 report（取 shared.models.common_enums.EntityType），
  保留列以维持收藏表统一形态
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    Column, Integer, BigInteger, String, DateTime, UniqueConstraint, Index,
)

# 自增主键：SQLite（测试库）仅 INTEGER PRIMARY KEY 自增，PG 用 BIGINT
_PK_BIGINT = BigInteger().with_variant(Integer, 'sqlite')


class ReportFavorite(Base):
    """用户收藏的报告（per-user）"""
    __tablename__ = 'report_favorites'
    __table_args__ = (
        UniqueConstraint('user_id', 'entity_type', 'entity_id',
                         name='uq_report_favorite_user_entity'),
        Index('idx_report_favorite_user', 'user_id', 'entity_type'),
    )
    id = Column(_PK_BIGINT, primary_key=True, autoincrement=True, comment='主键ID')
    user_id = Column(BigInteger, nullable=False, index=True, comment='收藏者用户ID（JWT，未认证 NULL 禁止写入）')
    entity_type = Column(String(20), nullable=False, comment='实体类型 (report，见 EntityType 枚举)')
    entity_id = Column(String(64), nullable=False, comment='报告ID（字符串化存储）')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='收藏时间')
