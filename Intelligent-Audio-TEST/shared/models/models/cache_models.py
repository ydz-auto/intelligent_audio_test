"""
统计缓存管理模型 (Stats Cache Management)

存储预计算的统计数据，用于首页快速展示。
"""
from ._base import (
    db, Column, BigInteger, String, DateTime, JSON,
    utc8now,
)


# 13. 统计缓存管理 (Stats Cache Management)

class StatsCache(db.Model):
    """
    统计缓存模型 (Stats Cache Model)
    存储预计算的统计数据，用于首页快速展示。
    数据变化时自动更新缓存。
    """
    __tablename__ = 'stats_cache'
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='缓存唯一ID')
    cache_key = Column(String(100), nullable=False, unique=True, comment='缓存键值')
    cache_value = Column(JSON, nullable=False, comment='缓存数据 (JSON格式)')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='最后更新时间')
    created_by_user_id = Column(BigInteger, nullable=True, index=True, comment='创建者用户ID')
    updated_by_user_id = Column(BigInteger, nullable=True, comment='最后更新者用户ID')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
