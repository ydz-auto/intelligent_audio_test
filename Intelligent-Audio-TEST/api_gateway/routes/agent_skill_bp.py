# -*- coding: utf-8 -*-
"""自定义 Skill 网关代理（INT-2549 / 方案 §4.4 / §11）。

职责边界（§3.1）：身份、租户、限流、审计留在网关；本路由只做「鉴权后的
透明转发」，不绕过 AuthMiddleware。

权限码（RBAC 已注册，见 202608/seed_rbac.py）：
- ``agent:skill:read``：列表 / 详情 / 版本 / 导出；
- ``agent:skill:manage``：新建 / 保存 / 发布 / 停用 / 删除 / fork / 导入。

zip 导出 / 导入按原字节转发（``Content-Type`` / ``Content-Disposition``
原样带回），网关不做二次打包，保证与 agent_service 同一包结构。
"""
import logging

from fastapi import APIRouter, Depends, Request

from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.routes.agent_guard import require_agent_enabled
from api_gateway.routes.agent_runtime_bp import _forward

logger = logging.getLogger(__name__)

SKILL_READ_PERMISSION = 'agent:skill:read'
SKILL_MANAGE_PERMISSION = 'agent:skill:manage'

_READ = require_permission(SKILL_READ_PERMISSION)
_MANAGE = require_permission(SKILL_MANAGE_PERMISSION)

router = APIRouter(dependencies=[Depends(require_agent_enabled)])


@router.get('/skills')
async def proxy_list_skills(request: Request, _: None = _READ):
    """本人可见 Skill 列表（``?scope=`` / ``?status=`` 原样转发）。"""
    return await _forward(request, 'GET')


@router.post('/skills')
async def proxy_create_skill(request: Request, _: None = _MANAGE):
    return await _forward(request, 'POST')


@router.post('/skills/import')
async def proxy_import_skill(request: Request, _: None = _MANAGE):
    """zip 导入（multipart，原字节转发）。"""
    return await _forward(request, 'POST')


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
