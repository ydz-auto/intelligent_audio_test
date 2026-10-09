# -*- coding: utf-8 -*-
"""transfer_agent PO 定义（传输流水表 + 已收分片表）。

表：transfer_records（审计层流水，幂等唯一键 transfer_id）
    transfer_chunks（已收片表，断点续传依据，(transfer_id, chunk_index) 唯一）

PkgType / TransferStatus 枚举不是 PO，定义在 shared/models/common_enums.py。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    func, BigInteger, Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint,
)


class TransferRecord(Base):
    """传输包流水（transfer_records）— 5 层安全基座的审计层落点。"""
    __tablename__ = 'transfer_records'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='自增主键')
    transfer_id = Column(String(64), unique=True, nullable=False, index=True,
                         comment='全局唯一传输ID，幂等去重键')
    pkg_type = Column(String(32), nullable=False,
                      comment='包类型 EVAL_REQUEST/EVAL_RESULT/REPORT_SYNC/DATA_SYNC/C_REPORT/C_RESULT')
    src_zone = Column(String(8), nullable=False, comment='源区 A/B/C')
    dst_zone = Column(String(8), nullable=False, comment='目的区 A/B/C')
    category = Column(String(32), nullable=False, comment='内容类别 case-result/audios/reports/transit')
    key = Column(Text, nullable=False, comment='对象键，如 task_1/case_2/dev_3/result.wav')
    file_hash = Column(String(128), nullable=False, comment='整体 sha256（sha256:<hex>）')
    file_size = Column(BigInteger, nullable=False, comment='文件字节数')
    chunk_size = Column(Integer, nullable=False, comment='分片大小（字节）')
    meta = Column(Text, nullable=True, comment='业务元数据 JSON（task_id/eval_params 等）')
    ttl_seconds = Column(Integer, nullable=False, comment='传输有效期（秒）')
    ephemeral = Column(Boolean, nullable=False, default=False,
                       comment='true=仅中转临时处理，不落目的区持久存储')
    timestamp = Column(String(48), nullable=False, comment='发起方 ISO8601 时间（参与签名）')
    signature = Column(String(128), nullable=False, comment='HMAC-SHA256 签名')
    status = Column(String(20), nullable=False, index=True,
                    comment='状态 CREATED/TRANSFERRING/COMPLETED/DELIVERED/FAILED/EXPIRED')
    final_path = Column(Text, nullable=True, comment='合并完成后的存储路径（带 scheme）')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(), onupdate=utc8now, nullable=False, comment='更新时间')


class TransferChunk(Base):
    """已收分片（transfer_chunks）— 断点续传/幂等去重的持久化依据。"""
    __tablename__ = 'transfer_chunks'
    __table_args__ = (
        UniqueConstraint('transfer_id', 'chunk_index', name='uq_transfer_chunk_index'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='自增主键')
    transfer_id = Column(String(64), nullable=False, index=True, comment='所属传输ID')
    chunk_index = Column(Integer, nullable=False, comment='分片序号，从 0 开始')
    checksum = Column(String(64), nullable=False, comment='分片 sha256 hex')
    size = Column(BigInteger, nullable=False, comment='分片字节数')
    received_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='接收时间')
