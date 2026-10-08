# -*- coding: utf-8 -*-
"""auth_service 应用层 —— 命令/查询处理器（CQRS Handler）。

设计要点：
- AuthCommandHandler 处理所有写命令，通过 user_repository 操作 UserAggregate；
- AuthQueryHandler 处理所有读查询，通过 user_repository / role_repository 返回领域实体；
- Handler 不直接 import 任何 PO（持久化对象），仅与领域实体打交道，
  保证应用层与 ORM/持久化解耦；
- Handler 不返回 HTTP 响应格式（不耦合 success_response/error_response），
  只返回领域对象或基础类型，由上层 interfaces 层负责包装响应；
- 领域校验失败抛 AuthDomainError（携带 AuthErrorCode）；
- 管理写命令成功落库后写 auth 审计事件（旁路，失败不阻断，INT-30）。

归属：auth_service（用户与权限上下文）
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from auth_service.domain.entities.user import UserAggregate
from auth_service.domain.entities.role import PermissionEntity, RoleEntity
from auth_service.domain.exceptions import AuthDomainError
from auth_service.domain.services.auth_service import (
    validate_grant,
    validate_revoke,
    validate_role_deletion,
    validate_role_permission_set,
    validate_status_transition,
)
from auth_service.infrastructure.persistence.user_repository import (
    user_repository,
    role_repository,
)
from auth_service.application.services.auth_audit import write_auth_audit
from auth_service.application.commands.auth_commands import (
    RegisterUserCommand,
    UpdateUserStatusCommand,
    UpdateUserCommand,
    GrantPermissionCommand,
    RevokePermissionCommand,
    CreateUserCommand,
    DeleteUserCommand,
    SetUserRoleCommand,
    CreateRoleCommand,
    UpdateRoleCommand,
    SetRolePermissionsCommand,
    DeleteRoleCommand,
)
from auth_service.application.queries.auth_queries import (
    GetUserQuery,
    GetUserByUsernameQuery,
    GetUserByOAuthQuery,
    ListUsersQuery,
    GetUserPermissionsQuery,
    ListRolesQuery,
    GetRoleQuery,
    ListPermissionsQuery,
    ListUserOverridesQuery,
)
from shared.models.common_enums import AuditEvent, AuthErrorCode

_AUDIT_MODULE_USER = 'user_management'
_AUDIT_MODULE_ROLE = 'role_management'


def _raise_if(condition: bool, message: str,
              error_code: AuthErrorCode) -> None:
    """条件成立时抛 AuthDomainError（减少 if/raise 样板）。"""
    if condition:
        raise AuthDomainError(message, error_code)


class AuthCommandHandler:
    """认证命令处理器 —— 处理所有用户与权限相关写操作。

    通过 user_repository / role_repository 持久化，不直接操作 PO。
    事务边界由调用方（如 interfaces 层的工作单元）决定 commit 时机，
    repository 写操作仅 flush。
    """

    def handle_register_user(self, cmd: RegisterUserCommand) -> int:
        """注册本地账号用户，返回新用户 ID。

        与 handle_create_user 共享创建逻辑（重名校验 + 密码哈希落库）。
        """
        create_cmd = CreateUserCommand(
            username=cmd.username,
            email=cmd.email,
            oauth_provider='',
            oauth_subject='',
            role_id=cmd.role_id,
            password=cmd.password,
        )
        return self.handle_create_user(create_cmd)

    def handle_create_user(self, cmd: CreateUserCommand) -> int:
        """创建用户，返回新用户 ID。

        - username 必填且唯一（重名 → USERNAME_DUPLICATED）；
        - role_name 优先于 role_id 解析目标角色（默认注册走 role_name='guest'）；
        - 指定角色不存在 → ROLE_NOT_FOUND；
        - password 非空时由仓储哈希落库。
        """
        _raise_if(not cmd.username, '用户名不能为空', AuthErrorCode.USERNAME_DUPLICATED)
        _raise_if(
            user_repository.get_by_username(cmd.username) is not None,
            f'用户名已存在: {cmd.username}', AuthErrorCode.USERNAME_DUPLICATED,
        )
        role_id = self._resolve_role_id(cmd.role_name, cmd.role_id)
        aggregate = UserAggregate(
            username=cmd.username,
            email=cmd.email,
            oauth_provider=cmd.oauth_provider,
            oauth_subject=cmd.oauth_subject,
            role_id=role_id,
            status='active',
        )
        user_id = user_repository.add(aggregate, password=cmd.password or None)
        write_auth_audit(AuditEvent.AUTH_USER_CREATED, _AUDIT_MODULE_USER, {
            'operator_id': cmd.operator_id,
            'target_id': user_id,
            'delta': {
                'username': cmd.username, 'email': cmd.email,
                'role_id': role_id, 'oauth_provider': cmd.oauth_provider,
                'has_password': bool(cmd.password),
            },
        })
        return user_id

    def _resolve_role_id(self, role_name: str,
                         role_id: Optional[int]) -> Optional[int]:
        """角色解析：role_name 优先（按名查 id），否则透传 role_id。

        指定了角色（名或 ID）但不存在 → ROLE_NOT_FOUND。
        """
        if role_name:
            role = role_repository.get_by_name(role_name)
            _raise_if(role is None,
                      f'角色不存在: {role_name}', AuthErrorCode.ROLE_NOT_FOUND)
            return role.id
        if role_id:
            role = role_repository.get_by_id(role_id)
            _raise_if(role is None,
                      f'角色不存在: id={role_id}', AuthErrorCode.ROLE_NOT_FOUND)
            return role.id
        return None

    def handle_update_status(self, cmd: UpdateUserStatusCommand) -> None:
        """更新用户状态（active/inactive/locked；软删除走 handle_delete_user）。"""
        validate_status_transition(cmd.status)
        _raise_if(
            user_repository.get_by_id(cmd.user_id) is None,
            f'用户不存在: id={cmd.user_id}', AuthErrorCode.USER_NOT_FOUND,
        )
        user_repository.update_status(cmd.user_id, cmd.status)
        write_auth_audit(AuditEvent.AUTH_USER_STATUS_CHANGED, _AUDIT_MODULE_USER, {
            'operator_id': cmd.operator_id,
            'target_id': cmd.user_id,
            'delta': {'status': cmd.status},
        })

    def handle_update_user(self, cmd: UpdateUserCommand) -> None:
        """更新用户资料（None 字段不修改）。

        - username 唯一性校验（改为已存在的用户名 → USERNAME_DUPLICATED）；
        - status 经 UserStatus 枚举校验（active/inactive/locked）；
        - password 由仓储哈希落库。
        """
        aggregate = user_repository.get_by_id(cmd.user_id)
        _raise_if(aggregate is None,
                  f'用户不存在: id={cmd.user_id}', AuthErrorCode.USER_NOT_FOUND)
        if cmd.username is not None and cmd.username != aggregate.username:
            _raise_if(not cmd.username, '用户名不能为空',
                      AuthErrorCode.USERNAME_DUPLICATED)
            existing = user_repository.get_by_username(cmd.username)
            _raise_if(existing is not None and existing.id != cmd.user_id,
                      f'用户名已存在: {cmd.username}',
                      AuthErrorCode.USERNAME_DUPLICATED)
        if cmd.status is not None:
            validate_status_transition(cmd.status)
        user_repository.update_user_fields(
            cmd.user_id,
            username=cmd.username,
            email=cmd.email,
            status=cmd.status,
            password=cmd.password or None,
        )
        # 规格§六：AUTH_USER_STATUS_CHANGED 含禁用/解锁/锁定（软删走 DeleteUser）；
        # 仅资料字段变更才落 AUTH_USER_UPDATED
        event = (
            AuditEvent.AUTH_USER_STATUS_CHANGED
            if cmd.status is not None
            else AuditEvent.AUTH_USER_UPDATED
        )
        write_auth_audit(event, _AUDIT_MODULE_USER, {
            'operator_id': cmd.operator_id,
            'target_id': cmd.user_id,
            'delta': {
                'username': cmd.username, 'email': cmd.email,
                'status': cmd.status, 'password_changed': bool(cmd.password),
            },
        })

    def handle_delete_user(self, cmd: DeleteUserCommand) -> bool:
        """软删除用户（status='deleted'），返回是否执行了删除。

        - 不可删除自己（SELF_OPERATION_FORBIDDEN，防自我锁死）；
        - 目标不存在 → USER_NOT_FOUND。
        """
        _raise_if(
            cmd.operator_id and cmd.operator_id == cmd.user_id,
            '不允许删除当前登录用户自己', AuthErrorCode.SELF_OPERATION_FORBIDDEN,
        )
        _raise_if(
            user_repository.get_by_id(cmd.user_id) is None,
            f'用户不存在: id={cmd.user_id}', AuthErrorCode.USER_NOT_FOUND,
        )
        deleted = user_repository.soft_delete(cmd.user_id)
        if deleted:
            write_auth_audit(AuditEvent.AUTH_USER_STATUS_CHANGED,
                             _AUDIT_MODULE_USER, {
                                 'operator_id': cmd.operator_id,
                                 'target_id': cmd.user_id,
                                 'delta': {'status': 'deleted'},
                             })
        return deleted

    def handle_set_user_role(self, cmd: SetUserRoleCommand) -> None:
        """设置用户角色（管理端分配角色）。

        - 不可修改自己的角色（SELF_OPERATION_FORBIDDEN，防自我降权锁死）；
        - 用户不存在或已软删除 → USER_NOT_FOUND（软删除用户对管理接口不可见）；
        - 角色不存在 → ROLE_NOT_FOUND。
        """
        _raise_if(
            cmd.operator_id and cmd.operator_id == cmd.user_id,
            '不允许修改当前登录用户自己的角色',
            AuthErrorCode.SELF_OPERATION_FORBIDDEN,
        )
        aggregate = user_repository.get_by_id(cmd.user_id)
        _raise_if(
            aggregate is None or aggregate.deleted,
            f'用户不存在: id={cmd.user_id}', AuthErrorCode.USER_NOT_FOUND,
        )
        role = role_repository.get_by_id(cmd.role_id)
        _raise_if(role is None,
                  f'角色不存在: id={cmd.role_id}', AuthErrorCode.ROLE_NOT_FOUND)
        aggregate.role_id = role.id
        user_repository.save(aggregate)
        write_auth_audit(AuditEvent.AUTH_USER_ROLE_ASSIGNED, _AUDIT_MODULE_USER, {
            'operator_id': cmd.operator_id,
            'target_id': cmd.user_id,
            'delta': {'role_id': role.id, 'role_name': role.name},
        })

    def handle_grant_permission(self, cmd: GrantPermissionCommand) -> int:
        """向用户授予附加权限码（差量 upsert override granted=True），返回权限点 ID。

        - 通配 '*' 拒绝授予（WILDCARD_FORBIDDEN）；
        - 用户不存在 → USER_NOT_FOUND；权限码不存在 → PERMISSION_NOT_FOUND；
        - 幂等：重复授予覆盖同一 override 行，不产生重复数据。
        """
        validate_grant(cmd.permission)
        _raise_if(
            user_repository.get_by_id(cmd.user_id) is None,
            f'用户不存在: id={cmd.user_id}', AuthErrorCode.USER_NOT_FOUND,
        )
        perm = role_repository.get_permission_by_code(cmd.permission)
        _raise_if(perm is None,
                  f'权限不存在: {cmd.permission}', AuthErrorCode.PERMISSION_NOT_FOUND)
        user_repository.upsert_override(cmd.user_id, perm.id, granted=True)
        write_auth_audit(AuditEvent.AUTH_USER_PERMISSION_GRANTED,
                         _AUDIT_MODULE_USER, {
                             'operator_id': cmd.operator_id,
                             'target_id': cmd.user_id,
                             'delta': {
                                 'permission_id': perm.id,
                                 'permission': perm.code,
                                 'granted': True,
                             },
                         })
        return perm.id

    def handle_revoke_permission(self, cmd: RevokePermissionCommand) -> str:
        """差量撤销用户权限，返回执行动作（override_revoke/delete_grant/noop）。

        编排语义（spec §五.3）：
        0. 通配 '*' 拒绝撤销（WILDCARD_FORBIDDEN，与授予双向封禁）；
        1. 权限点不存在（按 permission_id 或 permission 码定位）→ PERMISSION_NOT_FOUND；
        2. 权限 ∈ 用户角色基线 → upsert_override(granted=False)（覆盖撤销角色权限）；
        3. 否则存在 granted=True 的 override 行 → delete_override（收回附加授予）；
        4. 否则幂等 no-op 返回成功。
        """
        _raise_if(
            user_repository.get_by_id(cmd.user_id) is None,
            f'用户不存在: id={cmd.user_id}', AuthErrorCode.USER_NOT_FOUND,
        )
        perm = self._resolve_permission(cmd)
        validate_revoke(perm.code)
        baseline = set(user_repository.get_user_role_baseline(cmd.user_id))
        action = 'noop'
        if perm.code in baseline:
            user_repository.upsert_override(cmd.user_id, perm.id, granted=False)
            action = 'override_revoke'
        else:
            overrides = {
                o['permission_id']: o
                for o in user_repository.list_overrides(cmd.user_id)
            }
            row = overrides.get(perm.id)
            if row is not None and row['granted']:
                user_repository.delete_override(cmd.user_id, perm.id)
                action = 'delete_grant'
        if action != 'noop':
            write_auth_audit(AuditEvent.AUTH_USER_PERMISSION_REVOKED,
                             _AUDIT_MODULE_USER, {
                                 'operator_id': cmd.operator_id,
                                 'target_id': cmd.user_id,
                                 'delta': {
                                     'permission_id': perm.id,
                                     'permission': perm.code,
                                     'action': action,
                                 },
                             })
        return action

    def _resolve_permission(self, cmd: RevokePermissionCommand) -> PermissionEntity:
        """按 permission_id 优先解析权限点，其次 permission 码。"""
        if cmd.permission_id:
            perm = role_repository.get_permission_by_id(cmd.permission_id)
            _raise_if(perm is None,
                      f'权限不存在: id={cmd.permission_id}',
                      AuthErrorCode.PERMISSION_NOT_FOUND)
            return perm
        perm = role_repository.get_permission_by_code(cmd.permission or '')
        _raise_if(perm is None,
                  f'权限不存在: {cmd.permission}', AuthErrorCode.PERMISSION_NOT_FOUND)
        return perm

    def handle_create_role(self, cmd: CreateRoleCommand) -> int:
        """创建自定义角色（is_system 固定 False），返回新角色 ID。

        - name 唯一（重名 → ROLE_NAME_DUPLICATED）；
        - 未知权限码 → PERMISSION_NOT_FOUND；
        - 权限映射随创建一并写入。
        """
        _raise_if(not cmd.name, '角色名不能为空', AuthErrorCode.ROLE_NAME_DUPLICATED)
        _raise_if(
            role_repository.get_by_name(cmd.name) is not None,
            f'角色名已存在: {cmd.name}', AuthErrorCode.ROLE_NAME_DUPLICATED,
        )
        permission_ids = self._resolve_permission_ids(cmd.permission_codes or [])
        role_id = role_repository.add(cmd.name, cmd.description, is_system=False)
        role_repository.set_permissions(role_id, permission_ids)
        write_auth_audit(AuditEvent.AUTH_ROLE_CREATED, _AUDIT_MODULE_ROLE, {
            'operator_id': cmd.operator_id,
            'target_id': role_id,
            'delta': {
                'name': cmd.name, 'description': cmd.description,
                'permission_codes': list(cmd.permission_codes or []),
            },
        })
        return role_id

    def handle_update_role(self, cmd: UpdateRoleCommand) -> None:
        """更新角色信息（name/description，None=不修改）。

        name 唯一性校验（重名 → ROLE_NAME_DUPLICATED）。
        """
        role = role_repository.get_by_id(cmd.role_id)
        _raise_if(role is None,
                  f'角色不存在: id={cmd.role_id}', AuthErrorCode.ROLE_NOT_FOUND)
        if cmd.name is not None and cmd.name != role.name:
            _raise_if(not cmd.name, '角色名不能为空',
                      AuthErrorCode.ROLE_NAME_DUPLICATED)
            existing = role_repository.get_by_name(cmd.name)
            _raise_if(existing is not None and existing.id != cmd.role_id,
                      f'角色名已存在: {cmd.name}',
                      AuthErrorCode.ROLE_NAME_DUPLICATED)
        entity = RoleEntity(
            id=role.id,
            name=cmd.name if cmd.name is not None else role.name,
            description=(cmd.description
                         if cmd.description is not None else role.description),
            is_system=role.is_system,
        )
        role_repository.save(entity)
        write_auth_audit(AuditEvent.AUTH_ROLE_UPDATED, _AUDIT_MODULE_ROLE, {
            'operator_id': cmd.operator_id,
            'target_id': cmd.role_id,
            'delta': {'name': cmd.name, 'description': cmd.description},
        })

    def handle_set_role_permissions(self, cmd: SetRolePermissionsCommand) -> List[str]:
        """全量替换角色权限映射，返回最终生效权限码列表。

        - admin 角色的 '*' 不可移除（WILDCARD_FORBIDDEN）；
        - 未知权限码 → PERMISSION_NOT_FOUND。
        """
        role = role_repository.get_by_id(cmd.role_id)
        _raise_if(role is None,
                  f'角色不存在: id={cmd.role_id}', AuthErrorCode.ROLE_NOT_FOUND)
        validate_role_permission_set(role.name, cmd.permission_codes or [])
        permission_ids = self._resolve_permission_ids(cmd.permission_codes or [])
        role_repository.set_permissions(cmd.role_id, permission_ids)
        write_auth_audit(AuditEvent.AUTH_ROLE_PERMISSIONS_SET,
                         _AUDIT_MODULE_ROLE, {
                             'operator_id': cmd.operator_id,
                             'target_id': cmd.role_id,
                             'delta': {
                                 'role_name': role.name,
                                 'permission_codes':
                                     list(cmd.permission_codes or []),
                             },
                         })
        return list(cmd.permission_codes or [])

    def handle_delete_role(self, cmd: DeleteRoleCommand) -> None:
        """删除角色（连带 role_permissions 行）。

        - 系统内置角色 → ROLE_IS_SYSTEM；
        - 仍有用户引用 → ROLE_IN_USE（提示先迁移）。
        """
        role = role_repository.get_by_id(cmd.role_id)
        _raise_if(role is None,
                  f'角色不存在: id={cmd.role_id}', AuthErrorCode.ROLE_NOT_FOUND)
        validate_role_deletion(role.is_system, role_repository.count_users(cmd.role_id))
        role_repository.delete(cmd.role_id)
        write_auth_audit(AuditEvent.AUTH_ROLE_DELETED, _AUDIT_MODULE_ROLE, {
            'operator_id': cmd.operator_id,
            'target_id': cmd.role_id,
            'delta': {'name': role.name},
        })

    def _resolve_permission_ids(self, codes: List[str]) -> List[int]:
        """权限码列表 → 权限点 ID 列表（未知码 → PERMISSION_NOT_FOUND）。"""
        ids: List[int] = []
        for code in dict.fromkeys(codes or []):
            perm = role_repository.get_permission_by_code(code)
            _raise_if(perm is None,
                      f'权限不存在: {code}', AuthErrorCode.PERMISSION_NOT_FOUND)
            ids.append(perm.id)
        return ids


class AuthQueryHandler:
    """认证查询处理器 —— 处理所有用户与权限相关读操作。

    通过 user_repository / role_repository 查询，返回领域实体，
    不泄漏 PO 结构。
    """

    def handle_get_user(self, query: GetUserQuery) -> UserAggregate:
        """按用户 ID 查询用户聚合（含生效权限），不存在抛 USER_NOT_FOUND。"""
        user = user_repository.get_by_id(query.user_id)
        if user is None:
            raise AuthDomainError(
                f'用户不存在: id={query.user_id}', AuthErrorCode.USER_NOT_FOUND,
            )
        return user

    def handle_get_user_by_username(
        self, query: GetUserByUsernameQuery
    ) -> Optional[UserAggregate]:
        """按用户名查询用户聚合（登录链路：不存在返回 None，不抛错）。"""
        return user_repository.get_by_username(query.username)

    def handle_get_user_by_oauth(
        self, query: GetUserByOAuthQuery
    ) -> Optional[UserAggregate]:
        """按 OAuth 提供商与外部主体 ID 查询用户聚合。"""
        return user_repository.get_by_oauth(query.provider, query.subject)

    def handle_list_users(
        self, query: ListUsersQuery
    ) -> Tuple[int, List[UserAggregate]]:
        """分页查询用户列表，返回 (总数, 当前页用户聚合列表)。

        status 为 None 表示不过滤状态；keyword 模糊匹配 username/email；
        role_id 过滤指定角色的用户。
        """
        return user_repository.list_users(
            page=query.page,
            page_size=query.page_size,
            status=query.status,
            keyword=query.keyword,
            role_id=query.role_id,
        )

    def handle_get_user_permissions(
        self, query: GetUserPermissionsQuery
    ) -> List[str]:
        """获取用户生效权限码列表。"""
        return user_repository.get_user_permissions(query.user_id)

    def handle_list_roles(self, query: ListRolesQuery) -> List[RoleEntity]:
        """列出全部角色（含权限码列表与 is_system 标记）。"""
        return role_repository.get_all()

    def handle_get_role(self, query: GetRoleQuery) -> RoleEntity:
        """按角色 ID 查询角色（含权限码列表），不存在抛 ROLE_NOT_FOUND。"""
        role = role_repository.get_by_id(query.role_id)
        if role is None:
            raise AuthDomainError(
                f'角色不存在: id={query.role_id}', AuthErrorCode.ROLE_NOT_FOUND,
            )
        return role

    def handle_list_permissions(self, query: ListPermissionsQuery) -> List[PermissionEntity]:
        """列出全部权限点（含描述，按 id 升序）。"""
        return role_repository.list_permissions()

    def handle_list_user_overrides(
        self, query: ListUserOverridesQuery
    ) -> List[dict]:
        """列出用户权限 override 明细 [{permission_id, code, granted}]。"""
        return user_repository.list_overrides(query.user_id)
