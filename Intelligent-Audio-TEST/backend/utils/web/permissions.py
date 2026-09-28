"""
权限校验工具 (Permission Utility)

职责：
- 集中定义权限点常量（enum 化，拒绝魔法字符串），对齐主文档「资源:操作」命名规范；
- 提供路由级权限校验函数 require_permission，供各业务接口挂接。

过渡策略（V9.7.10 无认证体系，G 域 RBAC 尚未落地）：
- AUTH_ENABLED=false（默认）：直接放行，不影响现有功能；
- AUTH_ENABLED=true：从请求头 X-User-Permissions（逗号分隔的权限点列表）校验，
  '*' 通配放行（对齐 admin 语义）；G 域接入 JWT 后可切换到 request.state.permissions。
"""
from flask import request, current_app


class PermissionPoints:
    """权限点常量（16 域之外的已发布任务域，命名规范：资源:操作）"""

    # 任务域扩展
    TASK_PUBLISH = 'task:publish'                       # 发布已发布任务

    # 已发布任务域
    PUBLISHED_TASK_READ = 'published_task:read'         # 查看已发布任务
    PUBLISHED_TASK_EXECUTE = 'published_task:execute'   # 执行已发布任务
    PUBLISHED_TASK_VERSION = 'published_task:version'   # 创建新版本
    PUBLISHED_TASK_ARCHIVE = 'published_task:archive'   # 归档已发布任务

    # 全部已发布任务域权限点（便于批量授权/测试）
    PUBLISHED_TASK_ALL = (
        PUBLISHED_TASK_READ,
        PUBLISHED_TASK_EXECUTE,
        PUBLISHED_TASK_VERSION,
        PUBLISHED_TASK_ARCHIVE,
    )


def require_permission(perm: str):
    """路由级权限校验。

    Args:
        perm: 权限点名称，如 PermissionPoints.PUBLISHED_TASK_READ。
    """
    if not current_app.config.get('AUTH_ENABLED', False):
        return

    permissions = request.headers.get('X-User-Permissions', '')
    perm_set = {p.strip() for p in permissions.split(',') if p.strip()}
    if perm in perm_set or '*' in perm_set:
        return

    from backend.utils.web.response import error_response
    from backend.utils.web.error_codes import ErrorCode
    return error_response(f'缺少权限: {perm}', code=ErrorCode.FORBIDDEN, http_code=403)
