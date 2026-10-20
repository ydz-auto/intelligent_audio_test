# -*- coding: utf-8 -*-
"""report_service 报告分享 PO（INT-971 报告分享端点）

归属：report_service（报告上下文）。
表：report_shares —— 报告分享链接（生成/列表/撤销/公开读取）。

- token 服务端生成 secrets.token_urlsafe(24)，不落明文可猜序列；
- access: login / specific / public 三口径；access=specific 时 recipients
  存 [{user_id, label}]（label 用户名或邮箱，供弹窗回显）；
- 密码仅落 password_hash（bcrypt），响应只回 password_set；
- revoked 为软撤销标记；报告逻辑删除（deleted=true）或撤销后链接 404；
  报告物理删除 → hard_delete 子表级联清分享记录。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    func, Column, Integer, BigInteger, String, DateTime, Boolean, JSON,
    Index, UniqueConstraint,
)

# 自增主键：SQLite（测试库）仅 INTEGER PRIMARY KEY 自增，PG 用 BIGINT
_PK_BIGINT = BigInteger().with_variant(Integer, 'sqlite')


class ReportShare(Base):
    """报告分享链接记录（INT-971）"""
    __tablename__ = 'report_shares'
    __table_args__ = (
        UniqueConstraint('token', name='uq_report_share_token'),
        Index('idx_report_share_report_id', 'report_id'),
        Index('idx_report_share_token', 'token'),
    )
    id = Column(_PK_BIGINT, primary_key=True, autoincrement=True, comment='主键ID')
    report_id = Column(BigInteger, nullable=False, comment='外键 → test_reports.id')
    token = Column(String(64), nullable=False, comment='分享 token（secrets.token_urlsafe(24)）')
    access = Column(String(20), nullable=False, default='login', comment='访问口径 login/specific/public')
    expires_at = Column(DateTime, nullable=True, comment='过期时间；NULL=永久')
    password_hash = Column(String(255), nullable=True, comment='密码哈希（bcrypt）；NULL=无密码')
    recipients = Column(JSON, nullable=True, comment='access=specific 时 [{user_id, label}]')
    visits = Column(Integer, nullable=False, default=0, comment='访问计数（公开读取 200 时递增）')
    last_visited_at = Column(DateTime, nullable=True, comment='最近访问时间')
    revoked = Column(Boolean, nullable=False, default=False, comment='撤销标记（软撤销）')
    created_by_user_id = Column(BigInteger, nullable=True, comment='分享创建人（网关 x-user-id 透传）')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(), nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(), onupdate=utc8now, nullable=False, comment='更新时间')
