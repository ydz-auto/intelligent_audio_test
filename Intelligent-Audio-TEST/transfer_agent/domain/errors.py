# -*- coding: utf-8 -*-
"""transfer_agent 领域错误 — 带稳定错误码，interfaces 层据此映射 HTTP/gRPC 语义。

错误码命名：TRANSFER_<原因>，跨服务可见（ACL 防腐层依赖码值判断重试/放弃）。
"""
from __future__ import annotations


class TransferError(Exception):
    """传输域错误基类。"""

    code = 'TRANSFER_ERROR'
    http_status = 500

    def __init__(self, message: str = ''):
        super().__init__(message or self.code)
        self.message = message or self.code

    def to_dict(self) -> dict:
        return {'code': self.code, 'message': self.message}


class PackageNotFoundError(TransferError):
    code = 'TRANSFER_PACKAGE_NOT_FOUND'
    http_status = 404


class AccessTokenInvalidError(TransferError):
    """访问层错误：预共享 token 缺失或不匹配（5 层安全基座 · 访问控制层）。"""

    code = 'TRANSFER_ACCESS_TOKEN_INVALID'
    http_status = 401


class SignatureInvalidError(TransferError):
    """签名层错误：HMAC-SHA256 验签失败（5 层安全基座 · 签名层）。"""

    code = 'TRANSFER_SIGNATURE_INVALID'
    http_status = 401


class RouteNotAllowedError(TransferError):
    """网络隔离点/内容层错误：src_zone → dst_zone 的包类型不在路由白名单。"""

    code = 'TRANSFER_ROUTE_NOT_ALLOWED'
    http_status = 403


class InvalidPackageFieldError(TransferError):
    """传输包协议字段非法（pkg_type/zone/category 枚举外、ttl 越界等）。"""

    code = 'TRANSFER_PACKAGE_FIELD_INVALID'
    http_status = 400


class PackageExpiredError(TransferError):
    """TTL 过期：传输会话已超过 ttl，分片/临时文件将被清理回收。"""

    code = 'TRANSFER_PACKAGE_EXPIRED'
    http_status = 410


class DuplicateTransferConflictError(TransferError):
    """幂等冲突：同 transfer_id 已存在但 file_hash 不一致（视为新包，需换 ID）。"""

    code = 'TRANSFER_DUPLICATE_CONFLICT'
    http_status = 409


class ChunkChecksumMismatchError(TransferError):
    """分片校验失败：checksum 与数据不匹配，或与已收同位分片不一致。"""

    code = 'TRANSFER_CHUNK_CHECKSUM_MISMATCH'
    http_status = 409


class ChunkIndexOutOfRangeError(TransferError):
    code = 'TRANSFER_CHUNK_INDEX_OUT_OF_RANGE'
    http_status = 400


class ChunkSizeInvalidError(TransferError):
    """分片大小非法：超上限，或非末片不满块。"""

    code = 'TRANSFER_CHUNK_SIZE_INVALID'
    http_status = 413


class InvalidTransferStateError(TransferError):
    code = 'TRANSFER_STATE_INVALID'
    http_status = 409


class MissingChunksError(TransferError):
    code = 'TRANSFER_CHUNKS_MISSING'
    http_status = 409


class FileHashMismatchError(TransferError):
    """内容校验层错误：合并后整体 sha256 与声明 file_hash 不一致。"""

    code = 'TRANSFER_FILE_HASH_MISMATCH'
    http_status = 422
