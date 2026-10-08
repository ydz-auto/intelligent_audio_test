# -*- coding: utf-8 -*-
"""用户/角色/权限管理 API 单测（INT-30）。

覆盖（不依赖真库，仓储以 fake 注入）：
- 领域校验纯函数：validate_grant / validate_role_deletion /
  validate_role_permission_set / validate_status_transition
- _query_user_permissions 校验顺序固化（角色底表 → granted=true →
  granted=false → '*' 透传）
- 差量授予/撤销 handler 编排语义（真实落库路径：upsert_override /
  delete_override，回归修复点）
- 用户/角色管理命令校验（重名 / 系统角色 / 被引用 / 自操作 / 角色解析）
- servicer 失败响应携带 AuthErrorCode
- 网关 error_code → HTTP 状态码映射 + notice 注入
"""
import json
import os
import tempfile

import pytest

# 共享配置在导入期校验必填环境变量，且 BaseConfig.DATABASE_URL 为类属性、
# 在进程内首次导入时冻结 —— 本模块设置的默认值会决定后续收集模块
# （如 sqlite e2e）实际拿到的库。因此必须用文件型 sqlite（QueuePool 兼容），
# 不能用 :memory:（SingletonThreadPool 拒收 init_db 的 pool_size/max_overflow）。
# 本模块测试全程 fake 注入，不依赖真库。
os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int30_unit_') + '/unit.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.common_enums import AuditEvent, AuthErrorCode

from auth_service.domain.entities.user import UserAggregate
from auth_service.domain.entities.role import RoleEntity
from auth_service.domain.exceptions import AuthDomainError
from auth_service.domain.services.auth_service import (
    validate_grant,
    validate_revoke,
    validate_role_deletion,
    validate_role_permission_set,
    validate_status_transition,
)
import auth_service.application.handlers.auth_handlers as auth_handlers
import auth_service.infrastructure.persistence.user_repository as repo_mod
from auth_service.application.commands.auth_commands import (
    CreateUserCommand,
    DeleteUserCommand,
    DeleteRoleCommand,
    GrantPermissionCommand,
    RevokePermissionCommand,
    SetRolePermissionsCommand,
    SetUserRoleCommand,
    UpdateUserCommand,
    UpdateUserStatusCommand,
    UpdateRoleCommand,
    CreateRoleCommand,
)
from auth_service.application.queries.auth_queries import (
    GetUserQuery, ListPermissionsQuery, GetRoleQuery,
)


# ============================================================
# 领域校验纯函数
# ============================================================

class TestDomainValidations:

    def test_validate_grant_rejects_wildcard(self):
        with pytest.raises(AuthDomainError) as ei:
            validate_grant('*')
        assert ei.value.error_code == AuthErrorCode.WILDCARD_FORBIDDEN

    def test_validate_grant_rejects_empty(self):
        with pytest.raises(AuthDomainError) as ei:
            validate_grant('')
        assert ei.value.error_code == AuthErrorCode.PERMISSION_NOT_FOUND

    def test_validate_grant_accepts_normal_code(self):
        validate_grant('task:read')

    def test_validate_revoke_rejects_wildcard(self):
        """撤销 '*' 必须封禁：清空基线含 '*' 用户的生效权限后无 API 恢复路径。"""
        with pytest.raises(AuthDomainError) as ei:
            validate_revoke('*')
        assert ei.value.error_code == AuthErrorCode.WILDCARD_FORBIDDEN

    def test_validate_revoke_accepts_normal_code(self):
        validate_revoke('task:read')

    def test_validate_role_deletion_rejects_system_role(self):
        with pytest.raises(AuthDomainError) as ei:
            validate_role_deletion(is_system=True, user_ref_count=0)
        assert ei.value.error_code == AuthErrorCode.ROLE_IS_SYSTEM

    def test_validate_role_deletion_rejects_referenced_role(self):
        with pytest.raises(AuthDomainError) as ei:
            validate_role_deletion(is_system=False, user_ref_count=3)
        assert ei.value.error_code == AuthErrorCode.ROLE_IN_USE

    def test_validate_role_deletion_allows_free_custom_role(self):
        validate_role_deletion(is_system=False, user_ref_count=0)

    def test_validate_role_permission_set_rejects_admin_wildcard_removal(self):
        with pytest.raises(AuthDomainError) as ei:
            validate_role_permission_set('admin', ['task:read'])
        assert ei.value.error_code == AuthErrorCode.WILDCARD_FORBIDDEN

    def test_validate_role_permission_set_allows_admin_with_wildcard(self):
        validate_role_permission_set('admin', ['*', 'task:read'])

    def test_validate_role_permission_set_allows_custom_role_any_set(self):
        validate_role_permission_set('my_role', ['task:read'])

    def test_validate_status_transition_accepts_assignable(self):
        for status in ('active', 'inactive', 'locked'):
            validate_status_transition(status)

    def test_validate_status_transition_rejects_deleted_and_unknown(self):
        for status in ('deleted', 'banned', ''):
            with pytest.raises(AuthDomainError):
                validate_status_transition(status)


# ============================================================
# _query_user_permissions 校验顺序（fake session，不依赖真库）
# ============================================================

class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def join(self, *a, **k):
        return self

    def filter(self, *a, **k):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    """第一次 query（单列=角色基线），第二次 query（双列=override 行）。"""

    def __init__(self, role_rows, user_rows):
        self._role_rows = role_rows
        self._user_rows = user_rows

    def query(self, *cols):
        if len(cols) == 1:
            return _FakeQuery(self._role_rows)
        return _FakeQuery(self._user_rows)


class TestQueryUserPermissionsOrder:
    """固化生效权限合成顺序：角色底表 → granted=true 追加 → granted=false 移除。"""

    def _run(self, role_rows, user_rows, monkeypatch):
        monkeypatch.setattr(
            repo_mod, 'get_db_session',
            lambda: _FakeSession(role_rows, user_rows))
        return repo_mod._query_user_permissions(user_id=1, role_id=2)

    def test_role_baseline_plus_granted_minus_revoked(self, monkeypatch):
        # 角色基线 a/b；override：a 再授予（冗余）、b 撤销、c 附加授予
        result = self._run(
            role_rows=[('a',), ('b',)],
            user_rows=[('a', True), ('b', False), ('c', True)],
            monkeypatch=monkeypatch)
        assert set(result) == {'a', 'c'}

    def test_revoked_only_override_never_grants(self, monkeypatch):
        # 角色没有的权限被 granted=False 撤销 → 不生效（撤销不反向授予）
        result = self._run(
            role_rows=[('a',)],
            user_rows=[('x', False)],
            monkeypatch=monkeypatch)
        assert set(result) == {'a'}

    def test_wildcard_passthrough(self, monkeypatch):
        # '*' 不做通配展开，原样透传（放行判断由上层处理）
        result = self._run(
            role_rows=[('*',)],
            user_rows=[('a', False)],
            monkeypatch=monkeypatch)
        assert result == {'*'} or set(result) == {'*'}

    def test_override_granted_true_adds_outside_role(self, monkeypatch):
        result = self._run(
            role_rows=[('a',)],
            user_rows=[('extra', True)],
            monkeypatch=monkeypatch)
        assert set(result) == {'a', 'extra'}


# ============================================================
# Fake 仓储（handler 编排测试用）
# ============================================================

class FakeUserRepository:
    def __init__(self):
        self.users = {}       # id → UserAggregate
        self.by_name = {}
        self.overrides = {}   # (user_id, permission_id) → granted bool
        self.baselines = {}   # user_id → [code]
        self.next_id = 1

    def seed(self, user_id, username='u', role_id=None, baseline=()):
        agg = UserAggregate(id=user_id, username=username, role_id=role_id)
        self.users[user_id] = agg
        self.by_name[username] = agg
        self.baselines[user_id] = list(baseline)
        return agg

    def get_by_id(self, user_id):
        return self.users.get(user_id)

    def get_by_username(self, username):
        return self.by_name.get(username)

    def add(self, aggregate, password=None):
        aggregate.id = self.next_id
        self.next_id += 1
        self.users[aggregate.id] = aggregate
        self.by_name[aggregate.username] = aggregate
        return aggregate.id

    def save(self, aggregate):
        self.users[aggregate.id] = aggregate
        self.by_name[aggregate.username] = aggregate

    def update_status(self, user_id, status):
        self.users[user_id].status = status

    def update_user_fields(self, user_id, username=None, email=None,
                           status=None, password=None):
        agg = self.users[user_id]
        if username is not None:
            self.by_name.pop(agg.username, None)
            agg.username = username
            self.by_name[username] = agg
        if email is not None:
            agg.email = email
        if status is not None:
            agg.status = status
        return True

    def soft_delete(self, user_id):
        agg = self.users[user_id]
        agg.status = 'deleted'
        agg.deleted = True
        agg.role_id = None
        return True

    def upsert_override(self, user_id, permission_id, granted):
        self.overrides[(user_id, permission_id)] = granted

    def delete_override(self, user_id, permission_id):
        return 1 if self.overrides.pop((user_id, permission_id), None) else 0

    def list_overrides(self, user_id):
        return [
            {'permission_id': pid, 'code': f'p{pid}', 'granted': g}
            for (uid, pid), g in self.overrides.items() if uid == user_id
        ]

    def get_user_role_baseline(self, user_id):
        return list(self.baselines.get(user_id, []))


class FakeRoleRepository:
    def __init__(self):
        self.roles = {}          # id → RoleEntity
        self.by_name = {}
        self.permissions_by_code = {}
        self.permissions_by_id = {}
        self.role_perms = {}     # role_id → [pid]
        self.user_refs = {}      # role_id → count
        self.next_id = 1

    def seed_role(self, role_id, name, is_system=False, perms=()):
        entity = RoleEntity(id=role_id, name=name, permissions=list(perms),
                            is_system=is_system)
        self.roles[role_id] = entity
        self.by_name[name] = entity
        return entity

    def seed_permission(self, pid, code):
        from auth_service.domain.entities.role import PermissionEntity
        entity = PermissionEntity(id=pid, code=code)
        self.permissions_by_code[code] = entity
        self.permissions_by_id[pid] = entity

    def get_by_id(self, role_id):
        return self.roles.get(role_id)

    def get_by_name(self, name):
        return self.by_name.get(name)

    def add(self, name, description='', is_system=False):
        entity = RoleEntity(id=self.next_id, name=name,
                            description=description, is_system=is_system)
        self.next_id += 1
        self.roles[entity.id] = entity
        self.by_name[name] = entity
        return entity.id

    def save(self, entity):
        self.roles[entity.id] = entity
        self.by_name[entity.name] = entity
        return True

    def delete(self, role_id):
        return self.roles.pop(role_id, None) is not None

    def set_permissions(self, role_id, permission_ids):
        self.role_perms[role_id] = list(permission_ids)

    def count_users(self, role_id):
        return self.user_refs.get(role_id, 0)

    def get_permission_by_code(self, code):
        return self.permissions_by_code.get(code)

    def get_permission_by_id(self, permission_id):
        return self.permissions_by_id.get(permission_id)

    def list_permissions(self):
        return list(self.permissions_by_id.values())


@pytest.fixture()
def handler(monkeypatch):
    """构造注入 fake 仓储与 no-op 审计的 AuthCommandHandler。"""
    users, roles = FakeUserRepository(), FakeRoleRepository()
    audits = []

    def _audit(event, module, content):
        audits.append({'event': event, 'module': module, 'content': content})

    monkeypatch.setattr(auth_handlers, 'user_repository', users)
    monkeypatch.setattr(auth_handlers, 'role_repository', roles)
    monkeypatch.setattr(auth_handlers, 'write_auth_audit', _audit)
    return {'handler': auth_handlers.AuthCommandHandler(),
            'query': auth_handlers.AuthQueryHandler(),
            'users': users, 'roles': roles, 'audits': audits}


# ============================================================
# 用户授予/撤销差量语义（回归修复点：真实落 user_permissions）
# ============================================================

class TestGrantRevokeHandlers:

    def test_grant_upserts_override_true(self, handler):
        handler['users'].seed(1, baseline=['base:read'])
        handler['roles'].seed_permission(10, 'extra:run')
        handler['handler'].handle_grant_permission(
            GrantPermissionCommand(user_id=1, permission='extra:run'))
        assert handler['users'].overrides[(1, 10)] is True
        assert handler['audits'][0]['event'] == AuditEvent.AUTH_USER_PERMISSION_GRANTED

    def test_grant_is_idempotent_upsert(self, handler):
        handler['users'].seed(1)
        handler['roles'].seed_permission(10, 'extra:run')
        h = handler['handler']
        h.handle_grant_permission(GrantPermissionCommand(user_id=1, permission='extra:run'))
        h.handle_grant_permission(GrantPermissionCommand(user_id=1, permission='extra:run'))
        assert len(handler['users'].overrides) == 1

    def test_grant_wildcard_forbidden(self, handler):
        handler['users'].seed(1)
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_grant_permission(
                GrantPermissionCommand(user_id=1, permission='*'))
        assert ei.value.error_code == AuthErrorCode.WILDCARD_FORBIDDEN

    def test_grant_unknown_code(self, handler):
        handler['users'].seed(1)
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_grant_permission(
                GrantPermissionCommand(user_id=1, permission='no:such'))
        assert ei.value.error_code == AuthErrorCode.PERMISSION_NOT_FOUND

    def test_grant_missing_user(self, handler):
        handler['roles'].seed_permission(10, 'extra:run')
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_grant_permission(
                GrantPermissionCommand(user_id=99, permission='extra:run'))
        assert ei.value.error_code == AuthErrorCode.USER_NOT_FOUND

    def test_revoke_baseline_perm_writes_override_false(self, handler):
        handler['users'].seed(1, baseline=['base:read'])
        handler['roles'].seed_permission(10, 'base:read')
        action = handler['handler'].handle_revoke_permission(
            RevokePermissionCommand(user_id=1, permission_id=10))
        assert action == 'override_revoke'
        assert handler['users'].overrides[(1, 10)] is False
        assert handler['audits'][0]['event'] == AuditEvent.AUTH_USER_PERMISSION_REVOKED

    def test_revoke_extra_grant_deletes_override(self, handler):
        handler['users'].seed(1, baseline=[])
        handler['roles'].seed_permission(11, 'extra:run')
        handler['handler'].handle_grant_permission(
            GrantPermissionCommand(user_id=1, permission='extra:run'))
        action = handler['handler'].handle_revoke_permission(
            RevokePermissionCommand(user_id=1, permission_id=11))
        assert action == 'delete_grant'
        assert (1, 11) not in handler['users'].overrides

    def test_revoke_noop_when_neither_baseline_nor_override(self, handler):
        handler['users'].seed(1, baseline=[])
        handler['roles'].seed_permission(12, 'other:perm')
        action = handler['handler'].handle_revoke_permission(
            RevokePermissionCommand(user_id=1, permission_id=12))
        assert action == 'noop'
        assert handler['audits'] == []

    def test_revoke_unknown_permission_id(self, handler):
        handler['users'].seed(1)
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_revoke_permission(
                RevokePermissionCommand(user_id=1, permission_id=999))
        assert ei.value.error_code == AuthErrorCode.PERMISSION_NOT_FOUND

    def test_revoke_wildcard_code_forbidden(self, handler):
        """撤销 '*' 按码定位 → WILDCARD_FORBIDDEN，无 override 写入、无审计。"""
        handler['users'].seed(1, baseline=['*'])
        handler['roles'].seed_permission(1, '*')
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_revoke_permission(
                RevokePermissionCommand(user_id=1, permission='*'))
        assert ei.value.error_code == AuthErrorCode.WILDCARD_FORBIDDEN
        assert handler['users'].overrides == {}
        assert handler['audits'] == []

    def test_revoke_wildcard_by_permission_id_forbidden(self, handler):
        """撤销 '*' 按 permission_id 定位同样拒绝（验收复现路径）。"""
        handler['users'].seed(1, baseline=['*'])
        handler['roles'].seed_permission(9, '*')
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_revoke_permission(
                RevokePermissionCommand(user_id=1, permission_id=9))
        assert ei.value.error_code == AuthErrorCode.WILDCARD_FORBIDDEN
        assert handler['users'].overrides == {}

    def test_regrant_restores_revoked_baseline_perm(self, handler):
        """角色基线权限被撤销后重新授予恢复生效（差量语义闭环）。"""
        handler['users'].seed(1, baseline=['base:read'])
        handler['roles'].seed_permission(10, 'base:read')
        h = handler['handler']
        h.handle_revoke_permission(RevokePermissionCommand(user_id=1, permission_id=10))
        assert handler['users'].overrides[(1, 10)] is False
        h.handle_grant_permission(GrantPermissionCommand(user_id=1, permission='base:read'))
        assert handler['users'].overrides[(1, 10)] is True


# ============================================================
# 用户管理命令
# ============================================================

class TestUserManagementHandlers:

    def test_create_user_duplicate_username(self, handler):
        handler['users'].seed(1, username='alice')
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_create_user(CreateUserCommand(
                username='alice', email=None, oauth_provider='',
                oauth_subject=''))
        assert ei.value.error_code == AuthErrorCode.USERNAME_DUPLICATED

    def test_create_user_resolves_role_name(self, handler):
        handler['roles'].seed_role(5, 'guest')
        uid = handler['handler'].handle_create_user(CreateUserCommand(
            username='bob', email=None, oauth_provider='',
            oauth_subject='', role_name='guest'))
        assert handler['users'].users[uid].role_id == 5

    def test_create_user_unknown_role(self, handler):
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_create_user(CreateUserCommand(
                username='bob', email=None, oauth_provider='',
                oauth_subject='', role_name='ghost'))
        assert ei.value.error_code == AuthErrorCode.ROLE_NOT_FOUND

    def test_create_user_audit(self, handler):
        uid = handler['handler'].handle_create_user(CreateUserCommand(
            username='carol', email=None, oauth_provider='', oauth_subject=''))
        assert handler['audits'][0]['event'] == AuditEvent.AUTH_USER_CREATED
        assert handler['audits'][0]['content']['target_id'] == uid
        assert handler['audits'][0]['content']['operator_id'] == 0

    def test_update_status_invalid(self, handler):
        handler['users'].seed(1)
        with pytest.raises(AuthDomainError):
            handler['handler'].handle_update_status(
                UpdateUserStatusCommand(user_id=1, status='deleted'))

    def test_update_status_missing_user(self, handler):
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_update_status(
                UpdateUserStatusCommand(user_id=42, status='active'))
        assert ei.value.error_code == AuthErrorCode.USER_NOT_FOUND

    def test_update_user_duplicate_username(self, handler):
        handler['users'].seed(1, username='alice')
        handler['users'].seed(2, username='bob')
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_update_user(UpdateUserCommand(
                user_id=1, username='bob'))
        assert ei.value.error_code == AuthErrorCode.USERNAME_DUPLICATED

    def test_update_user_keeps_own_username(self, handler):
        handler['users'].seed(1, username='alice')
        handler['handler'].handle_update_user(UpdateUserCommand(
            user_id=1, username='alice', email='a@x.com'))
        assert handler['users'].users[1].email == 'a@x.com'

    def test_update_user_status_audits_status_changed(self, handler):
        """规格§六：状态变更（含禁用）落 AUTH_USER_STATUS_CHANGED。"""
        handler['users'].seed(1)
        handler['handler'].handle_update_user(UpdateUserCommand(
            user_id=1, status='inactive'))
        assert handler['audits'][0]['event'] == AuditEvent.AUTH_USER_STATUS_CHANGED
        assert handler['audits'][0]['content']['delta']['status'] == 'inactive'

    def test_update_user_profile_only_audits_updated(self, handler):
        handler['users'].seed(1)
        handler['handler'].handle_update_user(UpdateUserCommand(
            user_id=1, email='n@x.com'))
        assert handler['audits'][0]['event'] == AuditEvent.AUTH_USER_UPDATED

    def test_delete_user_self_forbidden(self, handler):
        handler['users'].seed(7, username='admin1')
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_delete_user(
                DeleteUserCommand(user_id=7, operator_id=7))
        assert ei.value.error_code == AuthErrorCode.SELF_OPERATION_FORBIDDEN

    def test_delete_user_missing_user(self, handler):
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_delete_user(
                DeleteUserCommand(user_id=42, operator_id=1))
        assert ei.value.error_code == AuthErrorCode.USER_NOT_FOUND

    def test_delete_user_success_audits_status_changed(self, handler):
        handler['users'].seed(2, username='alice')
        handler['handler'].handle_delete_user(
            DeleteUserCommand(user_id=2, operator_id=1))
        assert handler['users'].users[2].status == 'deleted'
        assert handler['audits'][0]['event'] == AuditEvent.AUTH_USER_STATUS_CHANGED
        assert handler['audits'][0]['content']['delta'] == {'status': 'deleted'}

    def test_delete_user_clears_role_id(self, handler):
        """软删除解除角色引用：角色删除不再被已删除用户 ROLE_IN_USE 卡住。"""
        handler['users'].seed(2, username='alice', role_id=3)
        handler['handler'].handle_delete_user(
            DeleteUserCommand(user_id=2, operator_id=1))
        assert handler['users'].users[2].role_id is None

    def test_set_user_role_self_forbidden(self, handler):
        handler['users'].seed(7, username='admin1')
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_set_user_role(
                SetUserRoleCommand(user_id=7, role_id=2, operator_id=7))
        assert ei.value.error_code == AuthErrorCode.SELF_OPERATION_FORBIDDEN

    def test_set_user_role_missing_role(self, handler):
        handler['users'].seed(1)
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_set_user_role(
                SetUserRoleCommand(user_id=1, role_id=99, operator_id=2))
        assert ei.value.error_code == AuthErrorCode.ROLE_NOT_FOUND

    def test_set_user_role_success(self, handler):
        handler['users'].seed(1)
        handler['roles'].seed_role(3, 'tester')
        handler['handler'].handle_set_user_role(
            SetUserRoleCommand(user_id=1, role_id=3, operator_id=2))
        assert handler['users'].users[1].role_id == 3
        assert handler['audits'][0]['event'] == AuditEvent.AUTH_USER_ROLE_ASSIGNED

    def test_set_user_role_deleted_user_rejected(self, handler):
        """软删除用户对管理接口不可见：分配角色 → USER_NOT_FOUND（拒绝）。"""
        handler['users'].seed(1, role_id=3)
        handler['roles'].seed_role(3, 'tester')
        handler['users'].soft_delete(1)
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_set_user_role(
                SetUserRoleCommand(user_id=1, role_id=3, operator_id=2))
        assert ei.value.error_code == AuthErrorCode.USER_NOT_FOUND
        assert handler['audits'] == []


# ============================================================
# 角色管理命令
# ============================================================

class TestRoleManagementHandlers:

    def test_create_role_duplicate_name(self, handler):
        handler['roles'].seed_role(1, 'dup')
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_create_role(
                CreateRoleCommand(name='dup'))
        assert ei.value.error_code == AuthErrorCode.ROLE_NAME_DUPLICATED

    def test_create_role_unknown_permission_code(self, handler):
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_create_role(CreateRoleCommand(
                name='r1', permission_codes=['no:such']))
        assert ei.value.error_code == AuthErrorCode.PERMISSION_NOT_FOUND

    def test_create_role_success_with_permissions(self, handler):
        handler['roles'].seed_permission(10, 'task:read')
        role_id = handler['handler'].handle_create_role(CreateRoleCommand(
            name='r1', permission_codes=['task:read']))
        assert handler['roles'].roles[role_id].is_system is False
        assert handler['roles'].role_perms[role_id] == [10]
        assert handler['audits'][0]['event'] == AuditEvent.AUTH_ROLE_CREATED

    def test_update_role_missing(self, handler):
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_update_role(UpdateRoleCommand(role_id=99))
        assert ei.value.error_code == AuthErrorCode.ROLE_NOT_FOUND

    def test_update_role_duplicate_name(self, handler):
        handler['roles'].seed_role(1, 'a')
        handler['roles'].seed_role(2, 'b')
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_update_role(
                UpdateRoleCommand(role_id=1, name='b'))
        assert ei.value.error_code == AuthErrorCode.ROLE_NAME_DUPLICATED

    def test_set_role_permissions_admin_wildcard_removal_forbidden(self, handler):
        handler['roles'].seed_role(1, 'admin', is_system=True, perms=['*'])
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_set_role_permissions(
                SetRolePermissionsCommand(role_id=1, permission_codes=['task:read']))
        assert ei.value.error_code == AuthErrorCode.WILDCARD_FORBIDDEN

    def test_set_role_permissions_success(self, handler):
        handler['roles'].seed_role(2, 'custom', perms=['task:read'])
        handler['roles'].seed_permission(11, 'audio:read')
        handler['roles'].seed_permission(10, 'task:read')
        codes = handler['handler'].handle_set_role_permissions(
            SetRolePermissionsCommand(role_id=2,
                                      permission_codes=['audio:read', 'task:read']))
        assert codes == ['audio:read', 'task:read']
        assert handler['roles'].role_perms[2] == [11, 10]
        assert handler['audits'][0]['event'] == AuditEvent.AUTH_ROLE_PERMISSIONS_SET

    def test_delete_role_system_forbidden(self, handler):
        handler['roles'].seed_role(1, 'tester', is_system=True)
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_delete_role(DeleteRoleCommand(role_id=1))
        assert ei.value.error_code == AuthErrorCode.ROLE_IS_SYSTEM

    def test_delete_role_in_use(self, handler):
        handler['roles'].seed_role(5, 'custom')
        handler['roles'].user_refs[5] = 2
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_delete_role(DeleteRoleCommand(role_id=5))
        assert ei.value.error_code == AuthErrorCode.ROLE_IN_USE

    def test_delete_role_success(self, handler):
        handler['roles'].seed_role(5, 'custom')
        handler['roles'].role_perms[5] = [10]
        handler['handler'].handle_delete_role(DeleteRoleCommand(role_id=5))
        assert 5 not in handler['roles'].roles
        assert handler['audits'][0]['event'] == AuditEvent.AUTH_ROLE_DELETED

    def test_get_role_missing_raises(self, handler):
        with pytest.raises(AuthDomainError) as ei:
            handler['query'].handle_get_role(GetRoleQuery(role_id=99))
        assert ei.value.error_code == AuthErrorCode.ROLE_NOT_FOUND

    def test_list_permissions(self, handler):
        handler['roles'].seed_permission(1, 'task:read')
        perms = handler['query'].handle_list_permissions(ListPermissionsQuery())
        assert [p.code for p in perms] == ['task:read']


# ============================================================
# servicer：失败响应携带 AuthErrorCode
# ============================================================

class TestServicerErrorCodes:

    def _servicer(self):
        from auth_service.interfaces.grpc.servicers import AuthServicer
        return AuthServicer()

    def test_fail_with_error_code_writes_json_data(self):
        from auth_service.interfaces.grpc.servicers import _fail
        resp = _fail('角色不存在', AuthErrorCode.ROLE_NOT_FOUND)
        assert resp.success is False
        assert json.loads(resp.data) == {'error_code': 'ROLE_NOT_FOUND'}

    def test_fail_without_error_code_empty_data(self):
        from auth_service.interfaces.grpc.servicers import _fail
        resp = _fail('未知错误')
        assert resp.success is False
        assert resp.data == ''

    def test_get_user_not_found_maps_error_code(self):
        class _Handler:
            def handle_get_user(self, q):
                raise AuthDomainError('用户不存在: id=1', AuthErrorCode.USER_NOT_FOUND)

        servicer = self._servicer()
        servicer._query_handler = _Handler()
        from shared.proto import auth_service_pb2 as auth_pb
        resp = servicer.GetUser(auth_pb.GetUserRequest(user_id=1))
        assert resp.success is False
        assert json.loads(resp.data) == {'error_code': 'USER_NOT_FOUND'}

    def test_user_to_dict_includes_role_name_and_timestamps(self):
        from auth_service.interfaces.grpc.servicers import _user_to_dict
        user = UserAggregate(id=1, username='u', role_id=2, role_name='tester',
                             status='active')
        d = _user_to_dict(user, overrides=[
            {'permission_id': 10, 'code': 'task:read', 'granted': True}])
        assert d['role_name'] == 'tester'
        assert d['overrides'][0]['code'] == 'task:read'
        assert 'created_at' in d and 'last_login_at' in d


# ============================================================
# 网关：error_code → HTTP 映射 + notice 注入
# ============================================================

class _FakeStub:
    def __init__(self, responses):
        self._responses = responses

    def __getattr__(self, name):
        return lambda req: self._responses[name]


class TestGatewayErrorMapping:

    def _call(self, monkeypatch, resp):
        import api_gateway.application.services.auth.management_common as mc
        proxy = type('P', (), {'stub': _FakeStub({'DeleteRole': resp})})()
        monkeypatch.setattr(mc, 'auth_config_service', proxy)
        return mc.call_auth_rpc('DeleteRole', object())

    def test_role_in_use_maps_409(self, monkeypatch):
        from shared.proto import auth_service_pb2 as auth_pb
        resp = auth_pb.AuthResponse(
            success=False, message='角色仍被引用',
            data=json.dumps({'error_code': 'ROLE_IN_USE'}))
        data, fail = self._call(monkeypatch, resp)
        assert data is None and fail[1] == 409

    def test_role_is_system_maps_400(self, monkeypatch):
        from shared.proto import auth_service_pb2 as auth_pb
        resp = auth_pb.AuthResponse(
            success=False, message='系统内置角色不允许删除',
            data=json.dumps({'error_code': 'ROLE_IS_SYSTEM'}))
        data, fail = self._call(monkeypatch, resp)
        assert fail[1] == 400

    def test_self_operation_maps_403(self, monkeypatch):
        from shared.proto import auth_service_pb2 as auth_pb
        resp = auth_pb.AuthResponse(
            success=False, message='不允许删除自己',
            data=json.dumps({'error_code': 'SELF_OPERATION_FORBIDDEN'}))
        data, fail = self._call(monkeypatch, resp)
        assert fail[1] == 403

    def test_user_not_found_maps_404(self, monkeypatch):
        from shared.proto import auth_service_pb2 as auth_pb
        resp = auth_pb.AuthResponse(
            success=False, message='用户不存在',
            data=json.dumps({'error_code': 'USER_NOT_FOUND'}))
        data, fail = self._call(monkeypatch, resp)
        assert fail[1] == 404

    def test_unknown_error_code_defaults_400(self, monkeypatch):
        from shared.proto import auth_service_pb2 as auth_pb
        resp = auth_pb.AuthResponse(success=False, message='炸了', data='')
        data, fail = self._call(monkeypatch, resp)
        assert fail[1] == 400

    def test_success_returns_data_no_fail(self, monkeypatch):
        from shared.proto import auth_service_pb2 as auth_pb
        resp = auth_pb.AuthResponse(success=True, message='ok',
                                    data=json.dumps({'role_id': 5}))
        data, fail = self._call(monkeypatch, resp)
        assert fail is None and data == {'role_id': 5}


class TestGatewayNotice:

    def test_with_notice_injects_constant(self):
        from api_gateway.application.services.auth.management_common import (
            with_notice, PERMISSION_CHANGE_NOTICE,
        )
        payload, code = with_notice(({'success': True}, 200))
        assert payload['notice'] == PERMISSION_CHANGE_NOTICE
        assert '24h' in payload['notice']

    def test_notice_injected_on_write_response(self, monkeypatch):
        """管理写接口响应体带 notice（以 delete_role 为例）。"""
        import api_gateway.application.services.auth.management_common as mc
        import api_gateway.application.services.auth.role_management_service as rms
        from shared.proto import auth_service_pb2 as auth_pb
        proxy = type('P', (), {'stub': _FakeStub({
            'DeleteRole': auth_pb.AuthResponse(success=True, message='删除成功',
                                               data='{}'),
        })})()
        monkeypatch.setattr(mc, 'auth_config_service', proxy)
        monkeypatch.setattr(rms, 'current_operator_id', lambda: 1)
        payload, http_code = rms.RoleManagementService.delete_role(5)
        assert http_code == 200
        assert 'notice' in payload
