# -*- coding: utf-8 -*-
"""增量回导合并的旧值快照 PO（INT-1762 D4，D0-A8 裁定）

归属：evaluation_service；表：evaluation_merge_snapshots

A8 要求「快照落各服务自有库的新表 data_transfer_merge_snapshots（evaluation /
report 各一张，同构），绝不跨服务写对方的表」。本工作区所有服务共用同一个
Postgres 库（见 docker/docker-compose.yml 各服务的 DATABASE_URL），同名表无法
各建一份，故按服务前缀区分表名：evaluation → evaluation_merge_snapshots，
report → report_merge_snapshots。列结构与 A8 一致。

行语义：
- old_row 非空：被覆盖 / 被删除的旧行（entity_pk = 旧行主键），回滚时原样插回；
- old_row 为空：本批次新插入 / 新建的行（entity_pk = 新行主键），回滚时删除。
"""
from sqlalchemy import (
    BigInteger, Column, DateTime, Index, String, func, JSON,
)

from shared.models.database import Base, utc8now


class EvaluationMergeSnapshot(Base):
    """维度合并批次快照（旧值 + 本批新行登记），与合并同事务写入"""
    __tablename__ = 'evaluation_merge_snapshots'
    __table_args__ = (
        Index('idx_eval_merge_snapshot_batch', 'batch_id'),
        Index('idx_eval_merge_snapshot_created_at', 'created_at'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='快照行ID')
    batch_id = Column(String(64), nullable=False, comment='编排方批次ID')
    entity_table = Column(String(64), nullable=False, comment='被改写的表名')
    entity_pk = Column(BigInteger, nullable=True, comment='行主键（旧行 id，或本批新行 id）')
    old_row = Column(JSON, nullable=True, comment='旧行全字段 JSON；NULL=本批新插入的行')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(),
                        nullable=False, comment='快照写入时间')
