# -*- coding: utf-8 -*-
"""评估配置密钥 PO（系统设置 → 评估服务）。

归属：api_gateway（系统选项上下文）
表：system_option_secrets

为什么单独一张表：``GET /api/option/`` 会把整表 KV 下发给 option:read，
密钥不能混在里面。这里只存 AES-256-GCM 密文与掩码；明文仅在网关内部
运行时配置端点按需解密，且只对内部 token 调用方返回。
"""
from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text, func

from shared.models.database import Base, utc8now


class SystemOptionSecret(Base):
    """系统选项密钥记录（key = eval.* 密钥键，一参一行）。"""

    __tablename__ = 'system_option_secrets'
    key = Column(String(128), primary_key=True, comment='选项键（域.分区.字段）')
    ciphertext = Column(Text, nullable=False,
                        comment='AES-256-GCM 密文（base64(nonce + blob)）')
    key_version = Column(Integer, nullable=False, default=1,
                         comment='主密钥版本（轮换用）')
    value_mask = Column(String(32), nullable=False, default='',
                        comment='脱敏回显串（如 sk-****abcd），列表不返回明文')
    updated_by = Column(BigInteger, nullable=True, comment='最后修改人 user_id')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(),
                        onupdate=utc8now, nullable=False, comment='更新时间')
