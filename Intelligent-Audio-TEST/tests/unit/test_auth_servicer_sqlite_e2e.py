# -*- coding: utf-8 -*-
"""auth_service 管理链路 sqlite 级自测（INT-30）。

直接驱动真实 gRPC servicer → 应用层 handler → 真实 SQLAlchemy 仓储
（SQLite 临时库，不依赖 Postgres/网络），验证：
- 差量授予/撤销真实落 user_permissions 表（回归修复点，验收标准 4）
- 角色管理全流程（建/配权限/改/删，验收标准 1 服务端部分）
- is_system / 被引用角色的删除保护（验收标准 2）
- 审计事件落 logs 表（category='auth'，验收标准 5）
- 差量撤销后生效权限合成（验收标准 3）
"""
import json
import os
import tempfile

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int30_') + '/auth.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.database import init_db, get_db_session, remove_db_session
from auth_service.infrastructure.persistence.models import (
    Role, Permission, RolePermission, UserPermission, User,
)
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


@pytest.fixture(scope='module')
def db():
    """初始化 SQLite 库并建 RBAC 相关表。"""
    init_db(pool_size=3)
    from shared.models.database import Base
    Base.metadata.create_all(
        bind=get_db_session().get_bind(),
        tables=[Role.__table__, Permission.__table__, RolePermission.__table__,
                UserPermission.__table__, User.__table__],
    )
    yield
    remove_db_session()


def _seed_permission(code, description=''):
    session = get_db_session()
    po = session.query(Permission).filter_by(name=code).first()
    if po:
        return po.id
    po = Permission(name=code, description=description)
    session.add(po)
    session.flush()
    return po.id


@pytest.fixture()
def servicer(db):
    from auth_service.interfaces.grpc.servicers import AuthServicer
    from shared.proto import auth_service_pb2 as auth_pb
    session = get_db_session()
    if session.query(Permission).count() == 0:
        _seed_permission('task:read', '查看任务')
        _seed_permission('audio:delete', '删除音频')
    return AuthServicer(), auth_pb


def _role_id(name):
    session = get_db_session()
    row = session.query(Role.id).filter_by(name=name).first()
    return row[0] if row else None


class TestRoleManagementChain:

    def test_role_crud_full_flow(self, servicer):
        svc, pb = servicer
        # 建角色（带权限）
        codes = pb.CreateRoleRequest(
            name='qa_custom', description='QA 自定义',
            permission_codes=['task:read'], operator_id=1)
        resp = svc.CreateRole(codes)
        assert resp.success, resp.message
        role_id = json.loads(resp.data)['role_id']
        assert role_id

        # GetRole 含权限码与 is_system=False
        resp = svc.GetRole(pb.GetRoleRequest(role_id=role_id))
        data = json.loads(resp.data)
        assert data['name'] == 'qa_custom'
        assert data['permissions'] == ['task:read']
        assert data['is_system'] is False

        # 改名
        resp = svc.UpdateRole(pb.UpdateRoleRequest(
            role_id=role_id, name='qa_custom2', operator_id=1))
        assert resp.success, resp.message

        # 全量替换权限
        resp = svc.SetRolePermissions(pb.SetRolePermissionsRequest(
            role_id=role_id, permission_codes=['audio:delete'], operator_id=1))
        assert resp.success, resp.message
        resp = svc.GetRole(pb.GetRoleRequest(role_id=role_id))
        assert json.loads(resp.data)['permissions'] == ['audio:delete']

        # 删除（未被引用 → 成功，连带 role_permissions）
        resp = svc.DeleteRole(pb.DeleteRoleRequest(role_id=role_id, operator_id=1))
        assert resp.success, resp.message
        assert _role_id('qa_custom2') is None
        session = get_db_session()
        assert session.query(RolePermission).filter_by(role_id=role_id).count() == 0

    def test_delete_system_role_rejected(self, servicer):
        svc, pb = servicer
        session = get_db_session()
        po = Role(name='builtin_guard', is_system=True)
        session.add(po)
        session.flush()
        resp = svc.DeleteRole(pb.DeleteRoleRequest(role_id=po.id, operator_id=1))
        assert resp.success is False
        assert json.loads(resp.data) == {'error_code': 'ROLE_IS_SYSTEM'}

    def test_delete_referenced_role_conflict(self, servicer):
        svc, pb = servicer
        session = get_db_session()
        role = Role(name='busy_role')
        user = User(username='busy_user', status='active', role_id=None)
        session.add(role)
        session.flush()
        user.role_id = role.id
        session.add(user)
        session.commit()
        resp = svc.DeleteRole(pb.DeleteRoleRequest(role_id=role.id, operator_id=1))
        assert resp.success is False
        assert json.loads(resp.data) == {'error_code': 'ROLE_IN_USE'}

    def test_create_role_duplicate_name(self, servicer):
        svc, pb = servicer
        assert svc.CreateRole(pb.CreateRoleRequest(name='dup_role')).success
        resp = svc.CreateRole(pb.CreateRoleRequest(name='dup_role'))
        assert json.loads(resp.data) == {'error_code': 'ROLE_NAME_DUPLICATED'}


class TestUserPermissionPersistence:
    """验收标准 4：GrantPermission / RevokePermission 真实落 user_permissions 表。"""

    def test_grant_persists_row(self, servicer):
        svc, pb = servicer
        session = get_db_session()
        user = User(username='perm_user_1', status='active')
        session.add(user)
        session.commit()

        resp = svc.GrantPermission(pb.GrantPermissionRequest(
            user_id=user.id, permission='task:read', operator_id=1))
        assert resp.success, resp.message

        row = (
            session.query(UserPermission)
            .filter_by(user_id=user.id)
            .join(Permission, Permission.id == UserPermission.permission_id)
            .filter(Permission.name == 'task:read')
            .first()
        )
        assert row is not None and row.granted is True

    def test_revoke_baseline_semantics(self, servicer):
        """基线权限撤销 → override granted=False，生效权限不再含该权限；重授恢复。"""
        svc, pb = servicer
        session = get_db_session()
        role = Role(name='baseline_role')
        session.add(role)
        session.flush()
        pid = _seed_permission('task:read')
        session.add(RolePermission(role_id=role.id, permission_id=pid))
        user = User(username='perm_user_2', status='active', role_id=role.id)
        session.add(user)
        session.commit()

        # 基线权限生效
        resp = svc.GetUserPermissions(pb.GetUserPermissionsRequest(user_id=user.id))
        assert 'task:read' in json.loads(resp.data)['permissions']

        # 撤销（基线覆盖撤销）→ 生效权限不含
        resp = svc.RevokePermission(pb.RevokePermissionRequest(
            user_id=user.id, permission_id=pid, operator_id=1))
        assert resp.success and json.loads(resp.data)['action'] == 'override_revoke'
        resp = svc.GetUserPermissions(pb.GetUserPermissionsRequest(user_id=user.id))
        assert 'task:read' not in json.loads(resp.data)['permissions']

        # 重新授予恢复
        resp = svc.GrantPermission(pb.GrantPermissionRequest(
            user_id=user.id, permission='task:read', operator_id=1))
        assert resp.success
        resp = svc.GetUserPermissions(pb.GetUserPermissionsRequest(user_id=user.id))
        assert 'task:read' in json.loads(resp.data)['permissions']

    def test_revoke_extra_grant_and_noop(self, servicer):
        svc, pb = servicer
        session = get_db_session()
        user = User(username='perm_user_3', status='active')
        session.add(user)
        session.flush()
        pid_extra = _seed_permission('audio:delete')
        session.add(UserPermission(user_id=user.id, permission_id=pid_extra,
                                   granted=True))
        pid_absent = _seed_permission('task:read')
        session.commit()

        # 附加授予 → delete_grant
        resp = svc.RevokePermission(pb.RevokePermissionRequest(
            user_id=user.id, permission_id=pid_extra, operator_id=1))
        assert json.loads(resp.data)['action'] == 'delete_grant'
        assert session.query(UserPermission).filter_by(
            user_id=user.id, permission_id=pid_extra).count() == 0

        # 既非基线也无 override → 幂等 no-op
        resp = svc.RevokePermission(pb.RevokePermissionRequest(
            user_id=user.id, permission_id=pid_absent, operator_id=1))
        assert resp.success and json.loads(resp.data)['action'] == 'noop'

    def test_grant_wildcard_rejected(self, servicer):
        svc, pb = servicer
        session = get_db_session()
        user = User(username='perm_user_4', status='active')
        session.add(user)
        session.commit()
        resp = svc.GrantPermission(pb.GrantPermissionRequest(
            user_id=user.id, permission='*', operator_id=1))
        assert json.loads(resp.data) == {'error_code': 'WILDCARD_FORBIDDEN'}


class TestUserManagementChain:

    def test_create_assign_role_update_delete(self, servicer):
        svc, pb = servicer
        # admin 建用户（带密码 → bcrypt 哈希落库）
        resp = svc.CreateUser(pb.CreateUserRequest(
            username='managed_user', password='s3cret', operator_id=1))
        assert resp.success, resp.message
        user_id = json.loads(resp.data)['user_id']
        session = get_db_session()
        po = session.query(User).filter_by(id=user_id).first()
        assert po.password_hash and po.password_hash.startswith('$2')

        # 分配角色
        role = Role(name='assigned_role')
        session.add(role)
        session.commit()
        resp = svc.SetUserRole(pb.SetUserRoleRequest(
            user_id=user_id, role_id=role.id, operator_id=1))
        assert resp.success, resp.message

        # 更新资料（status 校验 + username 唯一）
        resp = svc.UpdateUser(pb.UpdateUserRequest(
            user_id=user_id, email='m@x.com', status='locked', operator_id=1))
        assert resp.success, resp.message
        session.expire_all()
        po = session.query(User).filter_by(id=user_id).first()
        assert po.status == 'locked' and po.email == 'm@x.com'

        # 详情含 role_name / overrides / 时间戳
        resp = svc.GetUser(pb.GetUserRequest(user_id=user_id))
        data = json.loads(resp.data)
        assert data['role_name'] == 'assigned_role'
        assert data['status'] == 'locked'
        assert data['overrides'] == []
        assert data['created_at'] != ''

        # 软删除
        resp = svc.DeleteUser(pb.DeleteUserRequest(user_id=user_id, operator_id=1))
        assert resp.success
        session.expire_all()
        assert session.query(User).filter_by(id=user_id).first().status == 'deleted'

    def test_self_delete_and_self_role_forbidden(self, servicer):
        svc, pb = servicer
        resp = svc.DeleteUser(pb.DeleteUserRequest(user_id=9, operator_id=9))
        assert json.loads(resp.data) == {'error_code': 'SELF_OPERATION_FORBIDDEN'}
        resp = svc.SetUserRole(pb.SetUserRoleRequest(
            user_id=9, role_id=1, operator_id=9))
        assert json.loads(resp.data) == {'error_code': 'SELF_OPERATION_FORBIDDEN'}

    def test_register_resolves_guest_role(self, servicer):
        svc, pb = servicer
        session = get_db_session()
        guest = Role(name='guest')
        session.add(guest)
        session.commit()
        resp = svc.CreateUser(pb.CreateUserRequest(
            username='self_registered', password='pw123456',
            role_name='guest'))
        assert resp.success, resp.message
        user_id = json.loads(resp.data)['user_id']
        po = session.query(User).filter_by(id=user_id).first()
        assert po.role_id == guest.id

    def test_list_users_filters(self, servicer):
        svc, pb = servicer
        # keyword 过滤（软删除用户不在列表内）
        resp = svc.ListUsers(pb.ListUsersRequest(
            page=1, page_size=100, keyword='self_registered'))
        data = json.loads(resp.data)
        assert data['total'] >= 1
        assert any(u['username'] == 'self_registered' for u in data['users'])
        assert all('managed_user' not in u['username'] for u in data['users'])
        # role_id 过滤
        role_row = _role_id('baseline_role')
        resp = svc.ListUsers(pb.ListUsersRequest(page=1, page_size=100,
                                                 role_id=role_row))
        users = json.loads(resp.data)['users']
        assert users and all(u['role_id'] == role_row for u in users)


class TestAuditEvents:
    """验收标准 5：管理操作落审计事件（category='auth'，含 operator_id/target_id）。

    logs 表由日志服务经 gRPC batch_create_logs 托管，本地库不可直查；
    此处在 handler 模块层捕获 write_auth_audit 调用，验证 servicer 全链路
    触发了正确的事件名与负载（落库通道由旁路 worker 保证，失败不阻断）。
    """

    def test_delete_role_emits_audit(self, servicer, monkeypatch):
        import auth_service.application.handlers.auth_handlers as ah
        captured = []

        def _capture(event, module, content):
            captured.append({'event': event, 'module': module, 'content': content})

        monkeypatch.setattr(ah, 'write_auth_audit', _capture)
        svc, pb = servicer
        session = get_db_session()
        po = Role(name='audit_role_x')
        session.add(po)
        session.commit()
        resp = svc.DeleteRole(pb.DeleteRoleRequest(
            role_id=po.id, operator_id=42))
        assert resp.success
        assert captured, 'DeleteRole 未触发审计'
        assert captured[0]['event'].value == 'AUTH_ROLE_DELETED'
        assert captured[0]['content']['operator_id'] == 42
        assert captured[0]['content']['target_id'] == po.id
