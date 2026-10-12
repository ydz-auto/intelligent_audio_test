# -*- coding: utf-8 -*-
"""purge（彻底删除）权限收敛助手（INT-141）。

规则：仅 admin（网关按 '*' 通配权限判定，经 x-user-is-admin metadata 透传）
或资源 owner（创建人/删除人）可彻底删除；其余一律 403。

AUTH_MODE=off 时网关注入 dev 身份 permissions=['*'] → is_admin=True，
与 dev 默认 admin 角色口径一致。
"""


class PurgePermissionDenied(PermissionError):
    """purge 权限不足（HTTP 403 语义）"""


def check_purge_permission(user_id, is_admin: bool, owner_user_ids) -> None:
    """校验 purge 权限，不允许时抛 PurgePermissionDenied。

    Args:
        user_id: 操作人（x-user-id；未认证为 None）
        is_admin: 是否 admin（x-user-is-admin）
        owner_user_ids: 该批资源的创建人/删除人 user_id 集合（可含 None）
    """
    if is_admin:
        return
    if user_id is not None and user_id in set(owner_user_ids or ()):
        return
    raise PurgePermissionDenied('彻底删除仅限管理员或资源所有者（owner）操作')
