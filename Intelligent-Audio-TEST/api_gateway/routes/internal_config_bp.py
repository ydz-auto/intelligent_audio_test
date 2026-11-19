# -*- coding: utf-8 -*-
"""内部配置端点（服务间调用，不走 JWT）。

``GET /api/internal/eval-config``：评估服务（eval_server / evaluation_service）
启动后按需拉取系统设置里的评估配置（含解密后的密钥），5s 级缓存由调用方维护。

鉴权：共享密钥头 ``X-Internal-Token`` 与 ``INTERNAL_EVAL_CONFIG_TOKEN`` 比对；
未配置直接 503（fail-closed），不返回任何配置。
"""
import hmac
import logging
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from api_gateway.application.services.system_option_service import SystemOptionService

logger = logging.getLogger(__name__)

router = APIRouter()

INTERNAL_TOKEN_ENV = 'INTERNAL_EVAL_CONFIG_TOKEN'


@router.get('/internal/eval-config')
def get_eval_config(x_internal_token: Optional[str] = Header(default=None)):
    """运行时评估配置（明文密钥仅对合法内部 token 返回）。"""
    expected = os.environ.get(INTERNAL_TOKEN_ENV, '')
    if not expected:
        raise HTTPException(status_code=503, detail='内部配置通道未启用')
    if not x_internal_token or not hmac.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=403, detail='内部 token 校验失败')
    return SystemOptionService.get_runtime_eval_config()
