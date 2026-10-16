# -*- coding: utf-8 -*-
"""行级可见性（visibility）过滤助手（INT-423 数据可见性体系一期基座）。

规则：admin（网关按 '*' 通配权限判定，经 x-user-is-admin metadata 透传）
可见全部；其余用户仅可见 visibility='shared' 的行 + 自己创建（owner）的行。
PRIVATE 行对非 owner 一律不可见——网关层把 VisibilityDenied 映射为 403/404，
读路径（列表/批量）则逐行过滤，不可见行不进入结果集。

user_id / is_admin 一律取自 user_context.py 的 x-user-id / x-user-is-admin
（经 gRPC metadata 透传），禁止从业务表反查当前用户身份。
"""

from sqlalchemy import or_, true

from shared.models.common_enums import Visibility


class VisibilityDenied(PermissionError):
    """行级可见性不足（网关层映射 403/404）

    语义与 purge_permission.PurgePermissionDenied 同族：单资源访问
    （get/detail）不通过时抛出，由网关统一映射 HTTP 状态码。
    """


def visible_condition(owner_col, vis_col, user_id, is_admin: bool):
    """构造 SQLAlchemy 可见性条件：`is_admin OR vis_col=='shared' OR owner_col==user_id`。

    Args:
        owner_col: owner 列（如 test_tasks.created_by_user_id，可为 None 列）
        vis_col: visibility 列
        user_id: 操作人（x-user-id；未认证为 None）
        is_admin: 是否 admin（x-user-is-admin）

    Returns:
        SQLAlchemy BooleanClause；可直接传入 `where()` / `and_()` / `or_()`。
        - admin：恒真 `true()`（Python 侧短路，不拼接无谓条件）
        - 未认证（user_id=None）：仅 `vis_col == 'shared'`
        - 认证用户：`or_(vis_col == 'shared', owner_col == user_id)`
    """
    if is_admin:
        return true()
    shared_cond = vis_col == Visibility.SHARED.value
    if user_id is None:
        return shared_cond
    return or_(shared_cond, owner_col == user_id)


def check_visible(owner, vis, user_id, is_admin: bool) -> None:
    """校验单行可见性，不通过抛 VisibilityDenied（网关层映射 403/404）。

    Args:
        owner: 该行 owner user_id（可为 None——存量行无 owner 归属）
        vis: 该行 visibility 值（'shared' / 'private'）
        user_id: 操作人（未认证为 None）
        is_admin: 是否 admin

    Raises:
        VisibilityDenied: 非 admin 访问 PRIVATE 且非 owner（含未认证）时抛出
    """
    if is_admin:
        return
    if vis == Visibility.SHARED.value:
        return
    if user_id is not None and user_id == owner:
        return
    raise VisibilityDenied('资源不存在或无权访问')


def filter_visible_owners(rows, user_id, is_admin: bool) -> list:
    """批量可见性逐行过滤（镜像 purge_permission.filter_purgeable_owners 的逐行口径）。

    禁止"整批任一可见即放行整批"的越权：非 admin 仅保留
    `visibility == 'shared'` 或 `owner == 操作人` 的行，其余行跳过。
    读路径过滤后为空返回空列表（区别于 purge 的 403 语义——列表查询
    无数据不是错误）。

    Args:
        rows: [(id, owner_user_id, visibility), ...]（owner 可为 None）
        user_id: 操作人（未认证为 None）
        is_admin: 是否 admin

    Returns:
        可见 id 列表（保持入参顺序）
    """
    if is_admin:
        return [r[0] for r in rows]
    shared_value = Visibility.SHARED.value
    if user_id is None:
        return [r[0] for r in rows if r[2] == shared_value]
    return [r[0] for r in rows if r[2] == shared_value or r[1] == user_id]
