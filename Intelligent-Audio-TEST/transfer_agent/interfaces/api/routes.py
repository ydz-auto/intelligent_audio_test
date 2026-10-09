# -*- coding: utf-8 -*-
"""transfer_agent HTTP 收包/出站接口 — 跨区链路（设计文档 §4.2 interfaces/api）。

路由：/internal/transfer/*（网关白名单放行，跨区走 HTTPS）
- POST   /internal/transfer/packages                       创建传输会话
- POST   /internal/transfer/chunks?transfer_id=&chunk_index=  上传一个分片（raw body）
- GET    /internal/transfer/packages/{transfer_id}         查询状态与已收分片（断点续传）
- POST   /internal/transfer/packages/{transfer_id}/complete 合并 + file_hash 校验
- POST   /internal/transfer/outbound/{transfer_id}/dispatch 出站投递：transit 暂存包按
         第三方契约经 GW-2 投递 C，同步响应回传（B→C 数据面，§4.2.2 步骤⑤）
- GET    /internal/transfer/audit/{transfer_id}            传输包完整元数据（审计流水视图）

鉴权：X-Transfer-Token 头（预共享 Token，访问控制层）；
错误语义：domain errors → HTTP 状态码 + {code, message}。
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from transfer_agent.application.commands.transfer_commands import (
    CompleteTransferCommand,
    CreateTransferCommand,
    OutboundDispatchCommand,
    UploadChunkCommand,
)
from transfer_agent.application.queries.transfer_queries import (
    GetTransferQuery,
    GetTransferStatusQuery,
)
from transfer_agent.application.handlers.transfer_handlers import (
    TransferCommandHandler,
    TransferQueryHandler,
)
from transfer_agent.application.services.outbound_delivery_service import (
    OutboundDeliveryService,
)
from transfer_agent.application.services.relay_execution_service import (
    RelayExecutionService,
)
from transfer_agent.config.config import Config
from transfer_agent.domain.errors import ChunkSizeInvalidError, TransferError

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/internal/transfer')

_TOKEN_HEADER = 'X-Transfer-Token'
_CHECKSUM_HEADER = 'X-Chunk-Checksum'

_command_handler = TransferCommandHandler()
_query_handler = TransferQueryHandler()
_outbound_service = OutboundDeliveryService()


def _error_response(exc: TransferError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content={
        'success': False,
        'detail': exc.to_dict(),
    })


def _token(request: Request) -> str:
    return request.headers.get(_TOKEN_HEADER, '')


async def _json_body(request: Request) -> dict:
    """解析 JSON 请求体（空体/非法 JSON 按空 body 处理；与既有端点语义一致）。"""
    import json

    try:
        body = await request.body()
    except Exception:
        return {}
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


@router.post('/packages')
async def create_package(request: Request):
    """创建传输会话（幂等去重入口）。"""
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        result = _command_handler.create_transfer(CreateTransferCommand(
            transfer_id=str(body.get('transfer_id') or ''),
            pkg_type=str(body.get('pkg_type') or ''),
            src_zone=str(body.get('src_zone') or ''),
            dst_zone=str(body.get('dst_zone') or ''),
            category=str(body.get('category') or ''),
            key=str(body.get('key') or ''),
            file_hash=str(body.get('file_hash') or ''),
            file_size=int(body.get('file_size') or 0),
            ttl_seconds=int(body.get('ttl_seconds') or 0),
            ephemeral=bool(body.get('ephemeral') or False),
            timestamp=str(body.get('timestamp') or ''),
            signature=str(body.get('signature') or ''),
            token=_token(request) or str(body.get('token') or ''),
            meta=body.get('meta') or {},
            chunk_size=body.get('chunk_size'),
        ))
        return {'success': True, 'data': result}
    except TransferError as e:
        return _error_response(e)


@router.post('/chunks')
async def upload_chunk(request: Request):
    """上传一个分片（raw bytes body，元数据在 query/header）。"""
    transfer_id = request.query_params.get('transfer_id', '')
    try:
        chunk_index = int(request.query_params.get('chunk_index', '-1'))
    except ValueError:
        chunk_index = -1
    # 请求体上限预检：先看 Content-Length 再读 body，避免未认证方以超大 body 耗尽内存
    content_length = request.headers.get('content-length', '')
    if content_length.isdigit() and int(content_length) > Config.TRANSFER_CHUNK_SIZE:
        return _error_response(ChunkSizeInvalidError(
            f'分片请求体 {content_length}B 超过上限 {Config.TRANSFER_CHUNK_SIZE}B'
        ))
    try:
        data = await request.body()
        result = _command_handler.upload_chunk(UploadChunkCommand(
            transfer_id=transfer_id,
            chunk_index=chunk_index,
            data=data,
            checksum=request.headers.get(_CHECKSUM_HEADER, ''),
            token=_token(request),
        ))
        return {'success': True, 'data': result}
    except TransferError as e:
        return _error_response(e)


@router.get('/packages/{transfer_id}')
def get_transfer_status(transfer_id: str, request: Request):
    """查询状态与已收分片清单（断点续传依据）。"""
    try:
        result = _query_handler.get_transfer_status(GetTransferStatusQuery(
            transfer_id=transfer_id, token=_token(request),
        ))
        return {'success': True, 'data': result}
    except TransferError as e:
        return _error_response(e)


@router.post('/packages/{transfer_id}/complete')
def complete_transfer(transfer_id: str, request: Request):
    """合并分片并做 file_hash 完整性校验。"""
    try:
        result = _command_handler.complete_transfer(CompleteTransferCommand(
            transfer_id=transfer_id, token=_token(request),
        ))
        return {'success': True, 'data': result}
    except TransferError as e:
        return _error_response(e)


@router.post('/outbound/{transfer_id}/dispatch')
async def dispatch_outbound(transfer_id: str, request: Request):
    """出站投递（B→C 数据面）：COMPLETED 的 EVAL_REQUEST transit 暂存包按第三方
    契约（adapter_kind）经 GW-2 投递 C，同步返回投递视图（含 C 响应）。

    投递语义失败（C 不可达/4xx/5xx）以 delivered=False 随 200 返回（流水保持
    COMPLETED 可重投）；包不存在/状态非法/路由拒绝等走 TransferError 错误语义。
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        result = _outbound_service.dispatch(OutboundDispatchCommand(
            transfer_id=transfer_id,
            adapter_kind=str(body.get('adapter_kind') or ''),
            token=_token(request),
        ))
        return {'success': True, 'data': result}
    except TransferError as e:
        return _error_response(e)


@router.get('/audit/{transfer_id}')
def get_transfer(transfer_id: str, request: Request):
    """传输包完整元数据（审计流水视图）。"""
    try:
        result = _query_handler.get_transfer(GetTransferQuery(
            transfer_id=transfer_id, token=_token(request),
        ))
        return {'success': True, 'data': result}
    except TransferError as e:
        return _error_response(e)


# ================= 中转执行触发器端点（F2.3/INT-53 中枢侧生产触发） =================
_relay_service = RelayExecutionService()


@router.post('/relay/claim')
async def claim_relay(request: Request):
    """原子认领一个待执行中转包（中枢触发器轮询入口；无候选 data.transfer_id=null）。

    幂等去重前提（F2.3 验收 2）：仓储行锁 CAS，同一中转包不重复认领；
    访问控制：token 须为任一指向本区的预共享路由 token（fail-closed）。
    """
    try:
        body = await _json_body(request)
    except TransferError as e:
        return _error_response(e)
    try:
        package = _relay_service.claim_next(
            token=_token(request), stale_seconds=int(body.get('stale_seconds') or 0))
        return {'success': True,
                'data': {'transfer_id': package.transfer_id if package else None}}
    except TransferError as e:
        return _error_response(e)


@router.post('/relay/{transfer_id}/finish')
async def finish_relay(transfer_id: str, request: Request):
    """中转执行终态收敛（executed/failed；重复收敛/未认领幂等拒绝，流水不悬挂）。"""
    try:
        body = await _json_body(request)
    except TransferError as e:
        return _error_response(e)
    try:
        finished = _relay_service.finish(
            transfer_id=transfer_id, token=_token(request),
            state=str(body.get('state') or ''),
            error=str(body.get('error') or '') or None)
        return {'success': True, 'data': {'finished': bool(finished)}}
    except TransferError as e:
        return _error_response(e)
