"""
路由层权限校验依赖

用法：

    from api_gateway.application.services.auth.dependencies import require_permission

    @router.post('')
    def create_task(_: None = require_permission('task:create')):
        ...

    # 多权限（任一满足即可）
    @router.get('/{id}')
    def get_task(_: None = require_permission('task:read', 'task:execute')):
        ...
"""
from fastapi import Request, HTTPException, Depends


def require_permission(*perms: str):
    """
    返回 FastAPI 依赖，校验当前用户是否拥有指定权限之一。

    - 拥有 ``*`` 通配权限的用户（admin）直接放行
    - 多个权限参数为 OR 关系（任一满足即可）
    - 权限列表由 AuthMiddleware 注入到 ``request.state.permissions``
    - AUTH_MODE=off 时中间件注入 ``['*']``（admin 通配），此函数放行所有请求
    """
    required = set(perms)

    def _checker(request: Request) -> None:
        user_perms = set(getattr(request.state, 'permissions', None) or [])
        # admin 通配
        if '*' in user_perms:
            return
        # OR 关系
        if required & user_perms:
            return
        raise HTTPException(
            status_code=403,
            detail=f'缺少权限: {", ".join(required)}',
        )

    return Depends(_checker)


def require_auth(request: Request) -> None:
    """
    仅校验用户已登录（AuthMiddleware 已注入 user_id），不检查权限。

    适用于 AUTH_MODE=off 场景下仍需区分"已认证"的路由。
    """
    if getattr(request.state, 'user_id', None) is None:
        raise HTTPException(status_code=401, detail='未登录或令牌已过期')
