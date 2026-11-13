# -*- coding: utf-8 -*-
"""用户模型供应商 REST 路由（§6.4 / §11 provider API）。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET  | /api/v1/agent/providers | 我的供应商（Key 掩码 + 有效窗口/来源）|
| POST | /api/v1/agent/providers | 新建（Key 加密入库，可带 context_window）|
| PUT  | /api/v1/agent/providers/{id} | 修改；Key 留空表示不变；可改 context_window |
| DELETE | /api/v1/agent/providers/{id} | 逻辑删除并清空密文 |
| POST | /api/v1/agent/providers/{id}/verify | 轻量连通性验证 |
| POST | /api/v1/agent/providers/{id}/set-default | 设为默认 |
| GET  | /api/v1/agent/model-catalog | 目录默认窗口 / 最大输出（表单预填）|

鉴权 / 租户 / 限流 / 审计在 api_gateway（权限码 ``agent:provider:manage``）；
本服务只消费网关注入的身份头，并按 owner + tenant 做归属校验。
"""
import logging

from fastapi import APIRouter, Depends, Request

from agent_service.interfaces.api.dependencies import (
    Identity, get_container, get_identity,
)
from agent_service.interfaces.api.schemas import (
    CreateProviderRequest, ProviderListResponse, ProviderResponse,
    UpdateProviderRequest, VerifyProviderResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _serialize(view) -> ProviderResponse:
    return ProviderResponse(**view.to_dict())


# ---------------------------------------------------------------- providers

@router.get('/providers', response_model=ProviderListResponse)
def list_providers(request: Request,
                   identity: Identity = Depends(get_identity)):
    service = get_container(request).provider_service
    items = service.list(identity.user_id, identity.tenant_id)
    return ProviderListResponse(items=[_serialize(item) for item in items])


@router.post('/providers', response_model=ProviderResponse, status_code=201)
def create_provider(payload: CreateProviderRequest, request: Request,
                    identity: Identity = Depends(get_identity)):
    service = get_container(request).provider_service
    view = service.create(
        owner_id=identity.user_id, tenant_id=identity.tenant_id,
        name=payload.name, protocol=payload.protocol,
        base_url=payload.base_url, model=payload.model,
        api_key=payload.api_key, context_window=payload.context_window,
    )
    return _serialize(view)


@router.put('/providers/{provider_id}', response_model=ProviderResponse)
def update_provider(provider_id: str, payload: UpdateProviderRequest,
                    request: Request,
                    identity: Identity = Depends(get_identity)):
    service = get_container(request).provider_service
    fields = payload.model_dump(exclude_unset=True)
    view = service.update(provider_id, identity.user_id, identity.tenant_id,
                          fields)
    return _serialize(view)


@router.delete('/providers/{provider_id}')
def delete_provider(provider_id: str, request: Request,
                    identity: Identity = Depends(get_identity)):
    service = get_container(request).provider_service
    service.delete(provider_id, identity.user_id, identity.tenant_id)
    return {'id': provider_id, 'status': 'DELETED'}


@router.post('/providers/{provider_id}/verify',
             response_model=VerifyProviderResponse)
def verify_provider(provider_id: str, request: Request,
                    identity: Identity = Depends(get_identity)):
    service = get_container(request).provider_service
    return VerifyProviderResponse(**service.verify(
        provider_id, identity.user_id, identity.tenant_id))


@router.post('/providers/{provider_id}/set-default',
             response_model=ProviderResponse)
def set_default_provider(provider_id: str, request: Request,
                         identity: Identity = Depends(get_identity)):
    service = get_container(request).provider_service
    view = service.set_default(provider_id, identity.user_id,
                               identity.tenant_id)
    return _serialize(view)


# ---------------------------------------------------------------- catalog

@router.get('/model-catalog')
def model_catalog(request: Request,
                  identity: Identity = Depends(get_identity)):
    return get_container(request).provider_service.catalog()
