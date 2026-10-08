# -*- coding: utf-8 -*-
"""transfer_agent HTTP 收包接口 — 跨区链路接收端（设计文档 §4.2 interfaces/api）。

路由：/internal/transfer/*（网关白名单放行，跨区走 HTTPS）
- POST   /internal/transfer/packages                       创建传输会话
- POST   /internal/transfer/chunks?transfer_id=&chunk_index=  上传一个分片（raw body）
- GET    /internal/transfer/packages/{transfer_id}         查询状态与已收分片（断点续传）
- POST   /internal/transfer/packages/{transfer_id}/complete 合并 + file_hash 校验

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
from transfer_agent.config.config import Config
from transfer_agent.domain.errors import ChunkSizeInvalidError, TransferError

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/internal/transfer')

_TOKEN_HEADER = 'X-Transfer-Token'
_CHECKSUM_HEADER = 'X-Chunk-Checksum'

_command_handler = TransferCommandHandler()
_query_handler = TransferQueryHandler()


def _error_response(exc: TransferError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content={
        'success': False,
        'detail': exc.to_dict(),
    })


def _token(request: Request) -> str:
    return request.headers.get(_TOKEN_HEADER, '')


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
