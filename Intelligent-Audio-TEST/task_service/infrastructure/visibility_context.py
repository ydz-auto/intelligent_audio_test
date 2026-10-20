# -*- coding: utf-8 -*-
"""task_service 行级可见性上下文读取（INT-423/463）。

统一从 shared.infrastructure.user_context 读取操作人 user_id / is_admin
（经 gRPC metadata 透传 + ServerUserContextInterceptor 写入 contextvar），
供查询侧列表注入 visible_condition、命令侧单资源校验 check_visible、
批量操作 filter_visible_owners 使用。

显式 user_id 参数（收藏过滤等既有入口）优先于 contextvar——生产环境二者
同值，测试可显式传 user_id 免去 set_current_user_id 前置。
"""
from shared.infrastructure.user_context import (
    get_current_user_id,
    get_current_user_is_admin,
)


def visibility_identity(user_id=None):
    """返回 (user_id, is_admin)：显式 user_id 优先，否则取用户上下文。"""
    uid = user_id if user_id is not None else get_current_user_id()
    return uid, get_current_user_is_admin()


def is_visible(owner, vis):
    """单资源可见性判定（读路径 404 语义：不可见视为不存在）。

    使用当前用户上下文（get_current_user_id / get_current_user_is_admin）；
    返回 True 放行，False 表示不可见（调用方映射 404）。
    """
    from shared.infrastructure.visibility_filter import VisibilityDenied, check_visible
    try:
        check_visible(owner, vis, get_current_user_id(), get_current_user_is_admin())
        return True
    except VisibilityDenied:
        return False


def check_object_visible(obj, user_id=None, is_admin=None):
    """PO/替身对象级可见性校验（INT-423 命令侧统一入口）。

    - created_by_user_id / visibility 缺省的对象（测试替身、旧形态 PO）按
      存量形态处理：owner=None + visibility='shared' → 放行（零回归）；
    - 不可见抛 VisibilityDenied（调用方映射 403/404）。
    """
    from shared.infrastructure.visibility_filter import check_visible
    owner = getattr(obj, 'created_by_user_id', None)
    vis = getattr(obj, 'visibility', 'shared') or 'shared'
    if user_id is None or is_admin is None:
        uid, admin = visibility_identity()
        user_id = user_id if user_id is not None else uid
        is_admin = is_admin if is_admin is not None else admin
    check_visible(owner, vis, user_id, is_admin)
