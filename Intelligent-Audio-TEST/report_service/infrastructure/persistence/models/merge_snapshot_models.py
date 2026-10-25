# -*- coding: utf-8 -*-
"""增量回导报告替换的旧值快照 PO（INT-1762 D4，D0-A8 裁定）

归属：report_service；表：report_merge_snapshots

A8 要求快照落各服务自有库（evaluation / report 各一张、同构）。本工作区两服务
共用同一个 Postgres 库，同名表无法各建一份，故按服务前缀区分表名（列结构一致）。

行语义：
- old_row 非空：被替换掉的旧报告 7 表行（entity_pk = 旧行主键），回滚时原样插回；
- old_row 为空：本批次新写入的行（entity_pk = 新行主键），回滚时删除。
  A5 要求原地替换保留 A 报告 id：父行 id 不变，父行旧值同样以 entity_pk = 该 id
  记录，回滚时先删当前父行再插回旧值。
"""
from sqlalchemy import (
    BigInteger, Column, DateTime, Index, String, func, JSON,
)

from shared.models.database import Base, utc8now


class ReportMergeSnapshot(Base):
    """报告替换批次快照（旧报告 7 表旧行 + 本批新行登记），与替换同事务写入"""
    __tablename__ = 'report_merge_snapshots'
    __table_args__ = (
        Index('idx_report_merge_snapshot_batch', 'batch_id'),
        Index('idx_report_merge_snapshot_created_at', 'created_at'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='快照行ID')
    batch_id = Column(String(64), nullable=False, comment='编排方批次ID')
    entity_table = Column(String(64), nullable=False, comment='被改写的表名')
    entity_pk = Column(BigInteger, nullable=True, comment='行主键（旧行 id，或本批新行 id）')
    old_row = Column(JSON, nullable=True, comment='旧行全字段 JSON；NULL=本批新写入的行')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(),
                        nullable=False, comment='快照写入时间')
