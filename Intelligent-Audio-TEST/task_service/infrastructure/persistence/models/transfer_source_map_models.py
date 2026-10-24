# -*- coding: utf-8 -*-
"""task_service 离线搬运 source_map PO 定义（INT-1760）

归属：task_service
表：data_transfer_source_maps

设计依据：《任务数据离线搬运与增量回导功能设计文档》§5.3 + D0 裁定 A3/A4
（INT-1758 评论 01a16cbd）：

- 唯一键 `UNIQUE(source_server, entity_type, local_id)`：导出方向永远是从 B 的
  local id 反查 A 原始 id，local 侧天然唯一；同一 A 任务被 B 导入两次会产生
  多份本地副本（一个 source_id 对多个 local_id），唯一键若放在 source_id 上第
  二次整包导入就会炸。
- 普通索引 `(source_server, entity_type, source_id)`：按源 id 反查本地副本。
- 普通索引 `(source_server, source_task_id)`：增量回导按「源服务 + 源任务」一次
  取回四类映射。
- 无 TTL / 无 deleted 列：映射跨批次长期保留（D0 A4 第 4 条，清理只随任务硬删
  或人工维护）。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    BigInteger, Column, DateTime, Index, String, UniqueConstraint, func,
)


class DataTransferSourceMap(Base):
    """A 原始 id → B 本地 id 映射（整包导入发生主键重映射时登记）"""
    __tablename__ = 'data_transfer_source_maps'
    __table_args__ = (
        UniqueConstraint('source_server', 'entity_type', 'local_id',
                         name='uq_transfer_source_map_local'),
        Index('idx_transfer_source_map_task', 'source_server', 'source_task_id'),
        Index('idx_transfer_source_map_source',
              'source_server', 'entity_type', 'source_id'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='映射唯一ID')
    source_server = Column(String(128), nullable=False,
                           comment='源服务稳定标识（DATA_TRANSFER_SERVER_ID，非 hostname）')
    source_task_id = Column(BigInteger, nullable=False, comment='源服务（A）原始 task_id')
    entity_type = Column(String(32), nullable=False,
                         comment='实体类型 (tasks/test_results/test_result_dimensions/test_reports)')
    source_id = Column(BigInteger, nullable=False, comment='源服务（A）原始主键')
    local_id = Column(BigInteger, nullable=False, comment='本端（B）主键')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(),
                        nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(),
                        onupdate=utc8now, nullable=False, comment='更新时间')
