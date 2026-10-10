# -*- coding: utf-8 -*-
"""users_email_key 空邮箱撞唯一约束回归测试（INT-84）。

历史库 users.email 带唯一约束（users_email_key），email='' 空串占位后第二个
空邮箱用户 INSERT 必失败（真实故障：e2e 建号 e2e_guest/e2e_admin 全部失败）。

修复语义：注册/建号 email 为空（含纯空白）一律落 NULL（PG 唯一索引对 NULL
不生效）。本测试走真实 gRPC servicer + 真实 SQLAlchemy（文件型 sqlite），
验证连续创建多个空邮箱用户全部成功且落库 email 为 NULL。

不依赖外部服务（本地 sqlite，与 test_g3_auth_http_e2e 同款模式）。
"""
import os
import tempfile
import uuid

os.environ.setdefault(
    'DATABASE_URL',
    'sqlite:///' + tempfile.mkdtemp(prefix='int84_email_') + '/auth.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles

from shared.models.database import init_db, get_db_session, get_engine, remove_db_session


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


_RUN = uuid.uuid4().hex[:8]


@pytest.fixture(scope='module')
def svc():
    """真实 AuthServicer + 真实文件型 sqlite（auth 用户/角色相关表）。"""
    init_db(pool_size=3)
    remove_db_session()
    from shared.models.database import Base
    from auth_service.infrastructure.persistence.models import (
        Role, Permission, RolePermission, UserPermission, User,
    )
    engine = get_engine()
    Base.metadata.create_all(
        bind=engine,
        tables=[Role.__table__, Permission.__table__,
                RolePermission.__table__, UserPermission.__table__,
                User.__table__],
    )
    from auth_service.interfaces.grpc.servicers import AuthServicer
    servicer = AuthServicer()
    yield servicer
    remove_db_session()


def _create_user(svc, username, email=''):
    """经 gRPC servicer 建号（proto3 未传 email 默认空串，真实故障入口）。"""
    from shared.proto import auth_service_pb2 as auth_pb
    return svc.CreateUser(auth_pb.CreateUserRequest(
        username=username, email=email, password='pass-123456',
        operator_id=1))


class TestEmptyEmailUsers:
    """验收标准：e2e 连续创建多个空邮箱用户全部成功。"""

    def test_consecutive_empty_email_users_all_succeed(self, svc):
        """连续建两个空邮箱用户：全部成功且落库 email 为 NULL。"""
        resp1 = _create_user(svc, f'no_email_a_{_RUN}', email='')
        resp2 = _create_user(svc, f'no_email_b_{_RUN}', email='')
        assert resp1.success, resp1.message
        assert resp2.success, resp2.message

        from auth_service.infrastructure.persistence.models import User
        session = get_db_session()
        row_a = session.query(User).filter_by(
            username=f'no_email_a_{_RUN}').one()
        row_b = session.query(User).filter_by(
            username=f'no_email_b_{_RUN}').one()
        assert row_a.email is None, '空邮箱应落 NULL 而非空串'
        assert row_b.email is None, '空邮箱应落 NULL 而非空串'

    def test_whitespace_email_normalized_to_null(self, svc):
        """纯空白 email 同样归一化为 NULL。"""
        resp = _create_user(svc, f'ws_email_{_RUN}', email='   ')
        assert resp.success, resp.message
        from auth_service.infrastructure.persistence.models import User
        session = get_db_session()
        row = session.query(User).filter_by(
            username=f'ws_email_{_RUN}').one()
        assert row.email is None

    def test_explicit_email_stored_as_is(self, svc):
        """非空 email 照常落库（归一化不影响正常路径）。"""
        resp = _create_user(svc, f'has_email_{_RUN}', email='dev@example.com')
        assert resp.success, resp.message
        from auth_service.infrastructure.persistence.models import User
        session = get_db_session()
        row = session.query(User).filter_by(
            username=f'has_email_{_RUN}').one()
        assert row.email == 'dev@example.com'
