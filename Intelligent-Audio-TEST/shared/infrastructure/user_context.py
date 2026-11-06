# -*- coding: utf-8 -*-
"""操作人 user_id 跨服务传播（INT-141 方案 A：gRPC metadata 透传）。

api_gateway 从 JWT 解析当前用户（AuthMiddleware 注入 request.state.user_id，
AUTH_MODE=off 时为 0，归一化为 None 不得充当真实用户），经 gRPC metadata
把 user_id 传给下游服务；下游服务在 servicer 入口读取后写入 CUD 操作人列
（created_by_user_id / updated_by_user_id / deleted_by_user_id）。

- 网关侧：请求入口 set_current_user_id()，出站 gRPC 拦截器
  （client_user_context_interceptor）自动附加 metadata；
- 服务侧：servicer 入口用 user_id_from_context(context) 读取，
  执行引擎工作线程入口 set_current_user_id() 传播（copy 语义），
  ORM 写入点用 get_current_user_id() 填充操作人列。

红线：user_id 为 None/0 时禁止硬编码兜底为真实用户——一律保持 NULL。
"""
import contextvars

# gRPC metadata key（ASCII 小写，符合 HTTP/2 header 规范）
USER_ID_METADATA_KEY = 'x-user-id'
# 网关计算的 RBAC 管理员标志（'*' 通配权限），purge 等权限收敛操作用
USER_IS_ADMIN_METADATA_KEY = 'x-user-is-admin'

_current_user_id: contextvars.ContextVar = contextvars.ContextVar(
    'current_user_id', default=None)
_current_user_is_admin: contextvars.ContextVar = contextvars.ContextVar(
    'current_user_is_admin', default=False)


def normalize_user_id(value):
    """归一化用户 ID：None/''/0/非法值 → None（未认证），其余 int(value)。

    0 是 AuthMiddleware AUTH_MODE=off 的占位身份，不视为真实用户。
    """
    if value is None or value == '' or value == 0 or value == '0':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def set_current_user_id(user_id) -> None:
    """在当前执行上下文设置操作人 user_id（None 表示清除/未认证）"""
    _current_user_id.set(normalize_user_id(user_id))


def get_current_user_id():
    """读取当前上下文的操作人 user_id（未设置返回 None）"""
    return _current_user_id.get()


def capture_identity():
    """捕获当前操作人身份 (user_id, is_admin)，供线程池 / 后台线程显式透传。

    contextvars 不跨线程传播：提交到共享线程池的任务要带着身份进 worker，
    否则出站 gRPC 不带 x-user-id，下游按未认证身份过滤可见性（INT-1572）。
    """
    return (_current_user_id.get(), bool(_current_user_is_admin.get()))


def run_with_identity(identity, fn, *args, **kwargs):
    """在工作线程里恢复操作人身份后执行 fn，结束后复原（线程池线程复用防串号）。

    identity 取自 ``capture_identity()``；为 None 时按未认证身份执行。
    只透传身份，不透传其他上下文（请求预算 deadline / DB session scope 属于
    发起请求本身，后台线程沿用会读到已过期的截止时刻）。
    """
    user_id, is_admin = identity if identity else (None, False)
    prev_user_id = _current_user_id.get()
    prev_is_admin = _current_user_is_admin.get()
    _current_user_id.set(normalize_user_id(user_id))
    _current_user_is_admin.set(bool(is_admin))
    try:
        return fn(*args, **kwargs)
    finally:
        _current_user_id.set(prev_user_id)
        _current_user_is_admin.set(prev_is_admin)


def set_current_user_is_admin(is_admin: bool) -> None:
    """设置当前上下文的管理员标志（网关按 '*' 通配权限判定）"""
    _current_user_is_admin.set(bool(is_admin))


def get_current_user_is_admin() -> bool:
    """读取当前上下文的管理员标志（未设置返回 False）"""
    return bool(_current_user_is_admin.get())


def user_id_metadata():
    """构造出站 gRPC metadata 列表片段（未设置时返回空列表）"""
    value = _current_user_id.get()
    if value is not None:
        return [(USER_ID_METADATA_KEY, str(value))]
    return []


def user_admin_metadata():
    """构造出站 gRPC 管理员标志 metadata（False 时返回空列表，省带宽）"""
    if _current_user_is_admin.get():
        return [(USER_IS_ADMIN_METADATA_KEY, 'true')]
    return []


def user_id_from_context(context):
    """服务端从 grpc ServicerContext 读取入站操作人 user_id metadata"""
    if context is None:
        return None
    try:
        for key, value in (context.invocation_metadata() or ()):
            if key == USER_ID_METADATA_KEY:
                return normalize_user_id(value)
    except Exception:
        pass
    return None


def user_is_admin_from_context(context) -> bool:
    """服务端从 grpc ServicerContext 读取入站管理员标志 metadata"""
    if context is None:
        return False
    try:
        for key, value in (context.invocation_metadata() or ()):
            if key == USER_IS_ADMIN_METADATA_KEY:
                return str(value).lower() == 'true'
    except Exception:
        pass
    return False
