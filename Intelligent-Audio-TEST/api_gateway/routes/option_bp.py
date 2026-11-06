# -*- coding: utf-8 -*-
"""系统选项路由（INT-620）：GET/PUT /api/option/

对位 newAPI `/api/option/` KV 通道：
- GET /api/option/ ：全量 KV 拉取（领域默认基线 ∪ 库中已存覆盖）
- PUT /api/option/ ：单键写入 `{ key, value }`

权限码：option:read / option:write。
"""
from fastapi import APIRouter

from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.application.services.system_option_service import SystemOptionService
from api_gateway.routes._response import to_response
from api_gateway.schemas.system_option import SystemOptionUpdateRequest

router = APIRouter()


@router.get('/option/')
def get_options(_: None = require_permission('option:read')):
    """全量系统选项 KV 拉取。"""
    return to_response(SystemOptionService.get_all())


@router.put('/option/')
def put_option(body: SystemOptionUpdateRequest, _: None = require_permission('option:write')):
    """单键写入系统选项。"""
    return to_response(SystemOptionService.upsert(body.key, body.value))
