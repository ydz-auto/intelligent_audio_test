# -*- coding: utf-8 -*-
"""auth_service Access Token PO 定义

归属：auth_service（用户与权限上下文）
表：access_tokens（INT-1140 Access Token + skill/MCP 鉴权令牌）

对齐 new-api user_access_tokens 口径（INT-1142 评审 §1）：
- 库中只存 SHA-256 哈希（token_hash）与末 4 位掩码（token_hint），
  明文 token 仅创建响应返回一次；
- scopes JSON 存 RBAC 权限码列表，空列表=继承用户全部权限；
- expires_at 可空（NULL=永不过期，对外契约 0=永不过期）；
- 软删（deleted_at）+ status（enabled|disabled），对齐本平台收藏/回收站语义；
  new-api 为硬删，本卡采用软删（取舍见 INT-1148 实现说明）。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    func, Column, BigInteger, String, DateTime, JSON, Index, UniqueConstraint,
)


class AccessToken(Base):
    """Access Token 模型 (Access Token Model)

    外部 agent / skill / MCP 调用本系统能力时的鉴权令牌。
    """
    __tablename__ = 'access_tokens'
    __table_args__ = (
        UniqueConstraint('token_hash', name='uq_access_tokens_token_hash'),
        Index('ix_access_tokens_user_id', 'user_id'),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True,
                comment='令牌唯一ID')
    user_id = Column(BigInteger, nullable=False, comment='归属用户ID（鉴权后路由到该用户）')
    name = Column(String(100), nullable=False, comment='令牌名称（个人配置页展示）')
    token_hash = Column(String(64), nullable=False, comment='明文令牌的 SHA-256 哈希（64 hex，库中只存哈希）')
    token_hint = Column(String(10), nullable=False, comment='明文令牌末 4 位（列表/详情掩码）')
    scopes = Column(JSON, nullable=False, default=list,
                    comment='RBAC 权限码列表（空列表=继承用户全部权限）')
    expires_at = Column(DateTime, nullable=True, comment='过期时间（NULL=永不过期）')
    status = Column(String(20), nullable=False, default='enabled',
                    comment='状态 (enabled/disabled)')
    last_used_at = Column(DateTime, nullable=True, comment='最后使用时间')
    last_used_ip = Column(String(50), nullable=True, comment='最后使用来源IP')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(),
                        nullable=False, comment='创建时间')
    deleted_at = Column(DateTime, nullable=True, comment='软删除时间（NULL=未删除）')
