# -*- coding: utf-8 -*-
"""auth_service OAuth 提供方 PO 定义（INT-51 登录体系改造）。

表：custom_oauth_providers
存储自定义 OAuth 提供方配置（授权码模式），华为云等预置提供方
以数据行形态存在（scripts/migrations/202610/seed_custom_oauth_providers.py）。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    func, Column, Integer, String, DateTime, Boolean,
)


class CustomOAuthProvider(Base):
    """自定义 OAuth 提供方模型 (Custom OAuth Provider Model)

    授权码模式三端点（authorize/token/userinfo）+ userinfo 字段映射配置。
    client_secret 明文存储（token 换取需回传原文，不做哈希），
    任何对外查询路径不得返回该字段。
    """
    __tablename__ = 'custom_oauth_providers'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='提供方唯一ID')
    name = Column(String(100), nullable=False, comment='显示名称 (如 华为云)')
    slug = Column(String(64), unique=True, nullable=False, index=True,
                  comment='URL 标识 (小写字母/数字/连字符，如 huawei)')
    icon = Column(String(128), nullable=False, default='',
                  comment='图标标识 (前端 icon class，空=默认图标)')
    enabled = Column(Boolean, nullable=False, default=False,
                     comment='是否启用 (登录页动态渲染仅取启用项)')
    client_id = Column(String(256), nullable=False, comment='OAuth 客户端 ID')
    client_secret = Column(String(512), nullable=False, comment='OAuth 客户端密钥 (不对外返回)')
    authorize_url = Column(String(512), nullable=False, comment='授权端点 URL')
    token_url = Column(String(512), nullable=False, comment='token 端点 URL')
    userinfo_url = Column(String(512), nullable=False, comment='用户信息端点 URL')
    scopes = Column(String(256), nullable=False, default='openid profile email',
                    comment='授权 scope (空格分隔，空串=不携带)')
    user_id_field = Column(String(128), nullable=False, default='sub',
                           comment='userinfo 用户唯一标识字段 (点路径)')
    username_field = Column(String(128), nullable=False, default='preferred_username',
                            comment='userinfo 用户名字段 (点路径)')
    display_name_field = Column(String(128), nullable=False, default='name',
                                comment='userinfo 显示名字段 (点路径)')
    email_field = Column(String(128), nullable=False, default='email',
                         comment='userinfo 邮箱字段 (点路径)')
    created_at = Column(DateTime, default=utc8now, server_default=func.now(),
                        nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, server_default=func.now(),
                        onupdate=utc8now, nullable=False, comment='更新时间')
