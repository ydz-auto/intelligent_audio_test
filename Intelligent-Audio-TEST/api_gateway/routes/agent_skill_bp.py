# -*- coding: utf-8 -*-
"""自定义 Skill 网关代理（INT-2549 / INT-2551 / 方案 §4.4 / §11）。

职责边界（§3.1）：身份、租户、限流、审计留在网关；本路由只做「鉴权后的
透明转发」，不绕过 AuthMiddleware。

权限码（RBAC 已注册，见 202608/seed_rbac.py）：
- ``agent:skill:read``：列表 / 详情 / 版本 / 导出；
- ``agent:skill:manage``：新建 / 保存 / 发布 / 停用 / 删除 / fork / 导入；
- ``agent:skill:admin``：TENANT 级共享 Skill 的写入口与发布审核
  （提交 / 审批 / 撤回 / 待审队列）。这是**双条件的第一半**：网关只放行
  持码者，agent_service 再复核租户管理员角色；前端隐藏入口不构成鉴权。

zip 导出 / 导入按原字节转发（``Content-Type`` / ``Content-Disposition``
原样带回），网关不做二次打包，保证与 agent_service 同一包结构。导入在
读入内存前按 ``AGENT_SKILL_MAX_UPLOAD_BYTES``（与 agent_service 同一口径）
拒绝超大包，回 413。

身份头（``X-User-Id`` / ``X-Tenant-Id`` / ``X-User-Permissions`` /
``X-User-Is-Admin``）由 ``agent_runtime_bp._forward`` 统一注入并覆盖，
客户端伪造的租户 / 管理员标记无效。
"""
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request

from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.routes.agent_guard import require_agent_enabled
from api_gateway.routes.agent_runtime_bp import _forward
from shared.constants.permissions import (
    SKILL_ADMIN_PERMISSION, WILDCARD_PERMISSION,
)
from shared.skill_package import DEFAULT_MAX_UPLOAD_BYTES

logger = logging.getLogger(__name__)

SKILL_READ_PERMISSION = 'agent:skill:read'
SKILL_MANAGE_PERMISSION = 'agent:skill:manage'
# 审核流专属权限码 ``SKILL_ADMIN_PERMISSION`` 与 agent_service 共用
# ``shared.constants.permissions`` 的字面值（INT-2594 P3：不再各写一份）

# 上传（压缩前）体积上限：与 agent_service 的 AGENT_SKILL_MAX_UPLOAD_BYTES
# 同一口径，在网关读入内存前拒绝超大 zip（INT-2549 返工 P3）。
SKILL_UPLOAD_MAX_BYTES = int(os.environ.get(
    'AGENT_SKILL_MAX_UPLOAD_BYTES', DEFAULT_MAX_UPLOAD_BYTES))

_READ = require_permission(SKILL_READ_PERMISSION)
_MANAGE = require_permission(SKILL_MANAGE_PERMISSION)
_ADMIN = require_permission(SKILL_ADMIN_PERMISSION)

router = APIRouter(dependencies=[Depends(require_agent_enabled)])


def _is_tenant_request(request: Request) -> bool:
    """创建请求是否请求 TENANT 作用域（``?scope=TENANT``）。"""
    raw = (request.query_params.get('scope') or '').strip().upper()
    return raw == 'TENANT'


def _manage_skill(request: Request) -> None:
    """写操作鉴权：TENANT 作用域额外要求 ``agent:skill:admin``。

    与 ``require_permission`` 同口径（``*`` 通配放行）；这里不能直接用
    ``_MANAGE``，因为「能不能建 TENANT 级」取决于查询参数而不是路径。
    """
    permissions = set(getattr(request.state, 'permissions', None) or [])
    if WILDCARD_PERMISSION in permissions:
        return
    if SKILL_MANAGE_PERMISSION not in permissions:
        raise HTTPException(
            status_code=403,
            detail=f'缺少权限: {SKILL_MANAGE_PERMISSION}')
    if _is_tenant_request(request) and SKILL_ADMIN_PERMISSION not in permissions:
        raise HTTPException(
            status_code=403,
            detail=f'缺少权限: {SKILL_ADMIN_PERMISSION}')


@router.get('/skills')
async def proxy_list_skills(request: Request, _: None = _READ):
    """本人可见 Skill 列表（``?scope=`` / ``?status=`` 原样转发）。"""
    return await _forward(request, 'GET')


@router.get('/skills/reviews')
async def proxy_list_skill_reviews(request: Request, _: None = _ADMIN):
    """管理员待审队列（本租户；``?status=`` 缺省 PENDING_REVIEW）。"""
    return await _forward(request, 'GET')


@router.post('/skills')
async def proxy_create_skill(request: Request, _: None = Depends(_manage_skill)):
    """新建草稿；``?scope=TENANT`` 额外要求 ``agent:skill:admin``。"""
    return await _forward(request, 'POST')


@router.post('/skills/import')
async def proxy_import_skill(request: Request, _: None = _MANAGE):
    """zip 导入（multipart，原字节转发；读入内存前按上传上限拒绝）。"""
    return await _forward(request, 'POST',
                          max_body_bytes=SKILL_UPLOAD_MAX_BYTES)


@router.put('/skills/{skill_id}')
async def proxy_update_skill(skill_id: str, request: Request,
                             _: None = _MANAGE):
    return await _forward(request, 'PUT')


@router.delete('/skills/{skill_id}')
async def proxy_delete_skill(skill_id: str, request: Request,
                             _: None = _MANAGE):
    return await _forward(request, 'DELETE')


@router.post('/skills/{skill_id}/publish')
async def proxy_publish_skill(skill_id: str, request: Request,
                              _: None = _MANAGE):
    return await _forward(request, 'POST')


@router.post('/skills/{skill_id}/disable')
async def proxy_disable_skill(skill_id: str, request: Request,
                              _: None = _MANAGE):
    return await _forward(request, 'POST')


# ---- INT-2551 TENANT 级审核流（权限码 agent:skill:admin）----

@router.post('/skills/{skill_id}/submit-review')
async def proxy_submit_skill_review(skill_id: str, request: Request,
                                    _: None = _ADMIN):
    return await _forward(request, 'POST')


@router.post('/skills/{skill_id}/review')
async def proxy_decide_skill_review(skill_id: str, request: Request,
                                    _: None = _ADMIN):
    return await _forward(request, 'POST')


@router.post('/skills/{skill_id}/withdraw')
async def proxy_withdraw_skill_review(skill_id: str, request: Request,
                                      _: None = _ADMIN):
    return await _forward(request, 'POST')


@router.get('/skills/{skill_id}/reviews')
async def proxy_skill_review_history(skill_id: str, request: Request,
                                     _: None = _ADMIN):
    return await _forward(request, 'GET')


@router.post('/skills/{skill_id}/fork')
async def proxy_fork_skill(skill_id: str, request: Request,
                           _: None = _MANAGE):
    return await _forward(request, 'POST')


@router.get('/skills/{skill_id}/export')
async def proxy_export_skill(skill_id: str, request: Request,
                             _: None = _READ):
    """导出 zip：根级 ``SKILL.md``（与 ``GET /api/v1/agent/skill`` 同一口径）。"""
    return await _forward(request, 'GET')


@router.get('/skills/{skill_id}/versions')
async def proxy_skill_versions(skill_id: str, request: Request,
                               _: None = _READ):
    return await _forward(request, 'GET')


@router.get('/runs/{run_id}/skills')
async def proxy_run_skills(run_id: str, request: Request, _: None = _READ):
    """run 的 Skill 版本快照 / 回放（归属校验由 agent_service 判定）。"""
    return await _forward(request, 'GET')


__all__ = ['router']
