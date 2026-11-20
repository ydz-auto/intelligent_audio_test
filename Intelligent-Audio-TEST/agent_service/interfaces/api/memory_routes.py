# -*- coding: utf-8 -*-
"""长期记忆 REST（INT-2490，方案 §8.6 / §8.6.1）。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET  | /api/v1/agent/memory/metadata | 本人记忆元数据（条数 / 更新时间 / 用量）|
| GET  | /api/v1/agent/memory/proposals | 待审批提案（含预演内容）|
| POST | /api/v1/agent/memory/proposals/{id}/approve | 批准：按预演内容落盘 |
| POST | /api/v1/agent/memory/proposals/{id}/reject | 拒绝：无副作用 |
| GET  | /api/v1/agent/memory/break-glass | 读取正文（需专用权限，留审计）|

审批边界：``memory_write`` 的正文不落库，故不并入 INT-2466 的
``agent_approval`` 通用审批表；本组端点继续承载记忆写入的提案 / 审批
（文件式提案，审批前不落盘，``approval_id`` / ``path`` / ``status`` 结构不变）。
业务写工具的通用审批见 ``/api/v1/agent/approvals/{id}/decision``。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from agent_service.domain.exceptions import (
    MemoryError, MemoryPermissionDenied, MemoryProposalConflict,
    MemoryProposalNotFound, MemoryPathRejected, MemorySensitiveRejected,
)
from agent_service.interfaces.api.dependencies import (
    Identity, get_container, get_identity,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _service(request: Request):
    container = get_container(request)
    service = getattr(container, 'memory_service', None)
    if service is None:
        raise HTTPException(status_code=503, detail='长期记忆服务未装配')
    return service


def _http_error(exc: MemoryError) -> HTTPException:
    if isinstance(exc, MemoryProposalNotFound):
        return HTTPException(status_code=404, detail='not found')
    if isinstance(exc, MemoryPermissionDenied):
        return HTTPException(status_code=403, detail='无权重')
    if isinstance(exc, MemoryProposalConflict):
        return HTTPException(status_code=409,
                             detail=str(exc), headers={'X-Memory-Code': exc.code})
    if isinstance(exc, (MemoryPathRejected, MemorySensitiveRejected)):
        return HTTPException(status_code=400,
                             detail=str(exc), headers={'X-Memory-Code': exc.code})
    return HTTPException(status_code=400,
                         detail=str(exc), headers={'X-Memory-Code': exc.code})


@router.get('/memory/metadata')
def memory_metadata(request: Request, identity: Identity = Depends(get_identity)):
    service = _service(request)
    return service.metadata(tenant_id=identity.tenant_id,
                            owner_id=identity.user_id)


@router.get('/memory/proposals')
def list_memory_proposals(request: Request,
                          identity: Identity = Depends(get_identity)):
    service = _service(request)
    return {'items': service.list_proposals(
        tenant_id=identity.tenant_id, owner_id=identity.user_id)}


@router.post('/memory/proposals/{approval_id}/approve')
def approve_memory_proposal(approval_id: str, request: Request,
                            identity: Identity = Depends(get_identity)):
    service = _service(request)
    try:
        return service.approve(tenant_id=identity.tenant_id,
                               owner_id=identity.user_id,
                               approval_id=approval_id)
    except MemoryError as exc:
        raise _http_error(exc)


@router.post('/memory/proposals/{approval_id}/reject')
def reject_memory_proposal(approval_id: str, request: Request,
                           identity: Identity = Depends(get_identity)):
    service = _service(request)
    try:
        return service.reject(tenant_id=identity.tenant_id,
                              owner_id=identity.user_id,
                              approval_id=approval_id)
    except MemoryError as exc:
        raise _http_error(exc)


@router.get('/memory/break-glass')
def memory_break_glass(request: Request,
                       path: str = Query(..., min_length=1, max_length=512),
                       owner_id: int = Query(...),
                       identity: Identity = Depends(get_identity)):
    """break-glass 读取：管理端专用，权限未授予时一律 403（fail-closed）。"""
    service = _service(request)
    try:
        return service.break_glass_read(
            tenant_id=identity.tenant_id, owner_id=owner_id,
            relative_path=path, actor_id=identity.user_id,
            permissions=identity.permissions)
    except MemoryError as exc:
        raise _http_error(exc)


__all__ = ['router']
