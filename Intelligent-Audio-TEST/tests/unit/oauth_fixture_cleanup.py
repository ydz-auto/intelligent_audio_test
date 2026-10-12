# -*- coding: utf-8 -*-
"""OAuth/用户验收夹具清理（INT-179）。

G3 / INT-147 验收测试以模块级 ``os.environ.setdefault`` 期望独享临时
SQLite；但当运行环境已显式设置 DATABASE_URL 时 setdefault 不生效，
测试会打到共享库且从不清理——登录页公开提供方列表被验收残留污染
（INT-179 缺陷三根因）。各测试模块在 teardown 按 run tag 调用本函数，
保证任何库目标下都不落测试残留。
"""
from sqlalchemy import or_

from auth_service.infrastructure.persistence.models import (
    CustomOAuthProvider, User, UserOAuthBinding, UserPermission,
)
from shared.models.database import get_db_session, remove_db_session


def purge_oauth_test_fixtures(tag: str) -> dict:
    """按 run tag 清除本模块创建的提供方/绑定/用户夹具，返回各类删除计数。

    tag 须具备运行级唯一性（uuid hex8 / pid）。删除顺序先关联表后主体，
    兼容有无外键约束两种库形态。tag 未命中任何行时为无操作（幂等）。
    """
    session = get_db_session()
    deleted = {}
    try:
        provider_ids = [
            row[0] for row in session.query(CustomOAuthProvider.id)
            .filter(CustomOAuthProvider.slug.like(f'%{tag}')).all()]
        user_ids = [
            row[0] for row in session.query(User.id)
            .filter(or_(User.username.like(f'%{tag}'),
                        User.oauth_provider.like(f'%{tag}'))).all()]
        if user_ids:
            deleted['user_permissions'] = session.query(UserPermission).filter(
                UserPermission.user_id.in_(user_ids)).delete(
                synchronize_session=False)
            deleted['bindings_by_user'] = session.query(
                UserOAuthBinding).filter(
                UserOAuthBinding.user_id.in_(user_ids)).delete(
                synchronize_session=False)
        if provider_ids:
            deleted['bindings_by_provider'] = session.query(
                UserOAuthBinding).filter(
                UserOAuthBinding.provider_id.in_(provider_ids)).delete(
                synchronize_session=False)
            deleted['providers'] = session.query(CustomOAuthProvider).filter(
                CustomOAuthProvider.id.in_(provider_ids)).delete(
                synchronize_session=False)
        if user_ids:
            deleted['users'] = session.query(User).filter(
                User.id.in_(user_ids)).delete(synchronize_session=False)
        session.commit()
        return deleted
    except Exception:
        session.rollback()
        raise
    finally:
        remove_db_session()
