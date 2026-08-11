# -*- coding: utf-8 -*-
"""auth_service 用户与权限 PO 定义

归属：auth_service（用户与权限上下文）
表：roles / permissions / role_permissions / user_permissions
     / users / oauth_clients / oauth_refresh_tokens

P5 改造：从 shared/models/models/user_models.py 真正下沉到本服务。

注意：ReportStatus / TaskStatus / ReportType 三个枚举不在此处定义（不是 PO），
保留在 shared/models/common_enums.py 作为跨服务共享枚举。
"""
from shared.models.database import Base, utc8now
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, Boolean, JSON,
    ForeignKey,
)
from sqlalchemy.orm import relationship


class Role(Base):
    """角色模型 (Role Model) - RBAC
    定义系统角色，通过 role_permissions 关联表与权限多对多映射。
    """
    __tablename__ = 'roles'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='角色唯一ID')
    name = Column(String(50), unique=True, nullable=False, comment='角色名称 (admin/editor/viewer)')
    description = Column(Text, comment='角色描述')
    is_system = Column(Boolean, nullable=False, default=False, comment='是否系统内置角色 (内置不可删除)')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')

    permissions = relationship('Permission', secondary='role_permissions',
        primaryjoin='Role.id == RolePermission.role_id',
        secondaryjoin='Permission.id == RolePermission.permission_id',
        backref='roles', lazy=True)


class Permission(Base):
    """权限模型 (Permission Model)
    定义系统支持的具体操作权限项 (如 test_case:create, audio:delete)。
    """
    __tablename__ = 'permissions'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='权限唯一ID')
    name = Column(String(100), unique=True, nullable=False, comment='权限名称 (资源:操作)')
    description = Column(Text, comment='权限详细描述')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')


class RolePermission(Base):
    """角色-权限关联模型 (Role-Permission Relation) - RBAC
    维护角色与权限之间的多对多映射关系。
    """
    __tablename__ = 'role_permissions'
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    role_id = Column(Integer, nullable=False, index=True, comment='关联角色ID')
    permission_id = Column(Integer, nullable=False, index=True, comment='关联权限ID')


class UserPermission(Base):
    """用户额外权限关联模型 (User-Permission Relation)
    在 RBAC 角色权限基础上，给个别用户附加或撤销权限。
    """
    __tablename__ = 'user_permissions'
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    user_id = Column(BigInteger, nullable=False, index=True, comment='关联用户ID')
    permission_id = Column(Integer, nullable=False, index=True, comment='关联权限ID')
    granted = Column(Boolean, nullable=False, default=True, comment='True=授予, False=撤销')


class User(Base):
    """用户模型 (User Model)
    存储系统登录用户信息，支持本地密码登录和第三方 OAuth 登录（华为云等）。
    通过 role_id 关联 Role 实现 RBAC。
    """
    __tablename__ = 'users'
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='用户唯一ID')
    username = Column(String(50), nullable=False, index=True, comment='用户名 (本地登录用户名)')
    password_hash = Column(String(255), nullable=True, comment='密码哈希值 (OAuth 用户可为空)')
    email = Column(String(100), nullable=True, index=True, comment='电子邮箱')
    role_id = Column(Integer, ForeignKey('roles.id'), nullable=True, index=True, comment='关联角色ID (RBAC)')
    status = Column(String(20), nullable=False, default='active', comment='账户状态 (active/inactive/banned)')
    # OAuth 登录字段（支持华为云等第三方 OAuth 登录）
    oauth_provider = Column(String(50), nullable=True, comment='OAuth 提供商 (huawei/github/google/...)')
    oauth_id = Column(String(255), nullable=True, index=True, comment='OAuth 提供商返回的用户唯一ID')
    oauth_unionid = Column(String(255), nullable=True, comment='OAuth 提供商返回的 unionid (如有)')
    oauth_nickname = Column(String(100), nullable=True, comment='OAuth 提供商返回的昵称')
    oauth_avatar_url = Column(String(500), nullable=True, comment='OAuth 提供商返回的头像URL')
    last_login_at = Column(DateTime, nullable=True, comment='最后登录时间')
    last_login_ip = Column(String(50), nullable=True, comment='最后登录IP')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')

    role = relationship('Role', foreign_keys='User.role_id', backref='users')

    def has_permission(self, perm_name):
        """检查用户是否拥有指定权限 (角色权限 + 用户附加权限)。"""
        # 角色权限
        if self.role and self.role.permissions:
            for p in self.role.permissions:
                if p.name == perm_name or p.name == '*':
                    return True
        # 用户附加权限
        for up in getattr(self, 'extra_permissions', []):
            if up.granted and up.permission and (up.permission.name == perm_name or up.permission.name == '*'):
                return True
        return False


class OAuthClient(Base):
    """OAuth 客户端模型 (OAuth Client Model) - 自建 OAuth2 Server
    注册接入本系统的第三方应用，支持授权码模式 (authorization_code)。
    """
    __tablename__ = 'oauth_clients'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='客户端唯一ID')
    client_id = Column(String(64), unique=True, nullable=False, comment='客户端标识符 (公开)')
    client_secret = Column(String(255), nullable=False, comment='客户端密钥 (哈希存储)')
    name = Column(String(100), nullable=False, comment='客户端应用名称')
    description = Column(Text, comment='客户端应用描述')
    redirect_uris = Column(JSON, nullable=False, default=list, comment='允许的回调地址列表')
    grant_types = Column(JSON, nullable=False, default=list, comment='支持的授权类型 (如 authorization_code)')
    scopes = Column(JSON, nullable=False, default=list, comment='允许的 scope 列表')
    is_confidential = Column(Boolean, nullable=False, default=True, comment='是否机密客户端 (需要 client_secret)')
    status = Column(String(20), nullable=False, default='active', comment='状态 (active/disabled)')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=utc8now, onupdate=utc8now, nullable=False, comment='更新时间')


class OAuthRefreshToken(Base):
    """OAuth 刷新令牌模型 (OAuth Refresh Token) - 自建 OAuth2 Server
    存储 refresh_token，用于换取新的 access_token。
    """
    __tablename__ = 'oauth_refresh_tokens'
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='主键ID')
    token = Column(String(512), unique=True, nullable=False, index=True, comment='刷新令牌值 (哈希存储)')
    client_id = Column(String(64), nullable=False, index=True, comment='关联客户端 client_id')
    user_id = Column(BigInteger, nullable=True, index=True, comment='关联用户ID (客户端模式可为空)')
    scope = Column(Text, nullable=True, comment='令牌的 scope (空格分隔)')
    expires_at = Column(DateTime, nullable=False, comment='过期时间')
    revoked = Column(Boolean, nullable=False, default=False, comment='是否已撤销')
    created_at = Column(DateTime, default=utc8now, nullable=False, comment='创建时间')
