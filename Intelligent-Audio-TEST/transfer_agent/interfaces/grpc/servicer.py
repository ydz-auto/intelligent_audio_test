# -*- coding: utf-8 -*-
"""transfer_agent gRPC servicer。

继承 proto 生成的 TransferAgentServiceServicer 基类，委托应用层 handler 处理，
不直接操作 PO；域错误转译为统一响应结构（success/message/data）。
"""
from __future__ import annotations

import json
import logging

from shared.proto import transfer_agent_pb2 as transfer_pb
from shared.proto import transfer_agent_pb2_grpc as transfer_grpc
from shared.utils.grpc_json import dumps as _dumps

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
from transfer_agent.domain.errors import TransferError

logger = logging.getLogger(__name__)


def _ok(data, message: str = 'ok') -> transfer_pb.TransferActionResponse:
    return transfer_pb.TransferActionResponse(
        success=True,
        message=message,
        data=_dumps(data),
    )


def _fail(exc: Exception) -> transfer_pb.TransferActionResponse:
    if isinstance(exc, TransferError):
        return transfer_pb.TransferActionResponse(
            success=False,
            message=f'{exc.code}: {exc.message}',
            data='',
        )
    logger.exception('transfer gRPC 未预期异常')
    return transfer_pb.TransferActionResponse(
        success=False,
        message=f'TRANSFER_INTERNAL_ERROR: {exc}',
        data='',
    )


class TransferAgentServicer(transfer_grpc.TransferAgentServiceServicer):
    """跨区传输服务 gRPC servicer（本区微服务经此发起/查询传输）。"""

    def __init__(self):
        self._command_handler = None
        self._query_handler = None

    @property
    def command_handler(self) -> TransferCommandHandler:
        if self._command_handler is None:
            self._command_handler = TransferCommandHandler()
        return self._command_handler

    @property
    def query_handler(self) -> TransferQueryHandler:
        if self._query_handler is None:
            self._query_handler = TransferQueryHandler()
        return self._query_handler

    def CreateTransfer(self, request, context):
        try:
            meta = json.loads(request.meta) if request.meta else {}
            result = self.command_handler.create_transfer(CreateTransferCommand(
                transfer_id=request.transfer_id,
                pkg_type=request.pkg_type,
                src_zone=request.src_zone,
                dst_zone=request.dst_zone,
                category=request.category,
                key=request.key,
                file_hash=request.file_hash,
                file_size=request.file_size,
                ttl_seconds=request.ttl_seconds,
                ephemeral=request.ephemeral,
                timestamp=request.timestamp,
                signature=request.signature,
                token=request.token,
                meta=meta,
            ))
            return _ok(result)
        except Exception as e:
            return _fail(e)

    def UploadChunk(self, request, context):
        try:
            result = self.command_handler.upload_chunk(UploadChunkCommand(
                transfer_id=request.transfer_id,
                chunk_index=request.chunk_index,
                data=request.data,
                checksum=request.checksum,
                token=request.token,
            ))
            return _ok(result)
        except Exception as e:
            return _fail(e)

    def GetTransferStatus(self, request, context):
        try:
            result = self.query_handler.get_transfer_status(GetTransferStatusQuery(
                transfer_id=request.transfer_id,
                token=request.token,
            ))
            return _ok(result)
        except Exception as e:
            return _fail(e)

    def CompleteTransfer(self, request, context):
        try:
            result = self.command_handler.complete_transfer(CompleteTransferCommand(
                transfer_id=request.transfer_id,
                token=request.token,
            ))
            return _ok(result)
        except Exception as e:
            return _fail(e)

    def GetTransfer(self, request, context):
        try:
            result = self.query_handler.get_transfer(GetTransferQuery(
                transfer_id=request.transfer_id,
                token=request.token,
            ))
            return _ok(result)
        except Exception as e:
            return _fail(e)
