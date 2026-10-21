# -*- coding: utf-8 -*-
"""skill 下载 + MCP 适配端点路由（INT-1150 / INT-1140 分道 A）。

- GET  /api/v1/agent/skill   下载 skill 包 zip（SKILL.md + mcp.json 模板，
  base_url 注入；?base_url= → Origin 头 → Host 头兜底；需登录）
- POST /api/v1/mcp           MCP JSON-RPC 2.0 端点（initialize/tools/list/
  tools/call + tools 注册表；同一 access token 走同一条 AuthMiddleware 分支）
"""
import json
import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter()
mcp_router = APIRouter()


def _require_login(request: Request):
    """skill/MCP 均需真实登录身份（user_id 非空）。

    AuthMiddleware 注入 request.state.user_id：JWT=真实用户；
    access token（BE2 INT-1149 合入后）= 查证用户；AUTH_MODE=off 无 token
    回落 dev_user（user_id=0）视为未登录 → 401。
    """
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        return JSONResponse(status_code=401, content={'detail': '未登录或令牌无效'})
    return None


# ========================================================================
# skill 包下载
# ========================================================================

@router.get('/skill')
def download_skill(request: Request, base_url: str = ''):
    """下载 skill 包 zip：SKILL.md + mcp.json（base_url 注入）。"""
    from api_gateway.application.services.mcp.skill_package import (
        build_skill_zip, resolve_base_url, ZIP_FILENAME,
    )
    denied = _require_login(request)
    if denied is not None:
        return denied
    resolved = resolve_base_url(request)
    zip_bytes = build_skill_zip(resolved)
    return Response(
        content=zip_bytes,
        media_type='application/zip',
        headers={
            'Content-Disposition': f'attachment; filename="{ZIP_FILENAME}"',
        },
    )


# ========================================================================
# MCP 适配端点（JSON-RPC 2.0 / streamable HTTP）
# ========================================================================

def _format_sse_message(payload: dict) -> str:
    """MCP streamable HTTP 响应帧（event: message + data: JSON）。"""
    data = json.dumps(payload, ensure_ascii=False)
    return f'event: message\ndata: {data}\n\n'


@mcp_router.post('')
def mcp_endpoint(request: Request):
    """MCP JSON-RPC 2.0 端点。

    Accept 含 text/event-stream → SSE 帧包裹（streamable HTTP）；
    否则普通 JSON-RPC 响应。无 id 通知 → 202 空响应。
    """
    from api_gateway.application.services.mcp.mcp_handler import (
        handle_mcp_request,
    )
    denied = _require_login(request)
    if denied is not None:
        return denied
    payload, status = handle_mcp_request(request)
    if payload is None:
        # 通知：202 Accepted 空响应（streamable HTTP 语义）
        return Response(status_code=202)

    accept = request.headers.get('Accept', '')
    if 'text/event-stream' in accept:
        return StreamingResponse(
            iter([_format_sse_message(payload)]),
            media_type='text/event-stream',
            headers={'Cache-Control': 'no-cache',
                     'X-Accel-Buffering': 'no'},
        )
    return JSONResponse(content=payload, status_code=status)
