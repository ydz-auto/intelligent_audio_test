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


def filter_purgeable_owners(rows, user_id, is_admin: bool) -> list:
    """批量 purge 的逐行 owner 过滤（INT-141 审计 P2-1）。

    禁止"整批任一 owner 即放行整批"的越权：非 admin 仅保留操作人命中该行
    created_by/deleted_by 的行，其余行跳过（与活跃行跳过同口径，体现在
    返回计数）；过滤后为空抛 PurgePermissionDenied（403 语义）。

    Args:
        rows: [(id, created_by_user_id, deleted_by_user_id), ...]（已限定软删行）
        user_id: 操作人（未认证为 None）
        is_admin: 是否 admin

    Returns:
        purgeable id 列表（保持入参顺序）
    """
    if is_admin:
        return [r[0] for r in rows]
    if user_id is None:
        raise PurgePermissionDenied('彻底删除仅限管理员或资源所有者（owner）操作')
    purgeable = [r[0] for r in rows if r[1] == user_id or r[2] == user_id]
    if not purgeable:
        raise PurgePermissionDenied('彻底删除仅限管理员或资源所有者（owner）操作')
    return purgeable
