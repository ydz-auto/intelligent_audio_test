# -*- coding: utf-8 -*-
"""出站 ACL 防腐层 — 远端 transfer_agent HTTP 客户端。

跨区链路走 HTTPS（过网关白名单），对接远端 /internal/transfer/* 接口；
负责把远端错误响应转译为 transfer_agent.domain.errors（防腐：网络/协议细节不外泄）。

发送侧 ChunkedUploadService 经 RemoteTransferClientABC 依赖本类。
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

import requests

from transfer_agent.domain.errors import (
    AccessTokenInvalidError,
    ChunkChecksumMismatchError,
    ChunkIndexOutOfRangeError,
    ChunkSizeInvalidError,
    DuplicateTransferConflictError,
    FileHashMismatchError,
    InvalidPackageFieldError,
    InvalidTransferStateError,
    MissingChunksError,
    PackageExpiredError,
    PackageNotFoundError,
    RouteNotAllowedError,
    SignatureInvalidError,
    TransferError,
)
from transfer_agent.domain.repositories.transfer_repository_abc import (
    RemoteTransferClientABC,
)

logger = logging.getLogger(__name__)

# 远端错误码 → 本域异常（错误语义跨区透传）
_CODE_ERRORS = {
    'TRANSFER_PACKAGE_NOT_FOUND': PackageNotFoundError,
    'TRANSFER_ACCESS_TOKEN_INVALID': AccessTokenInvalidError,
    'TRANSFER_SIGNATURE_INVALID': SignatureInvalidError,
    'TRANSFER_ROUTE_NOT_ALLOWED': RouteNotAllowedError,
    'TRANSFER_PACKAGE_FIELD_INVALID': InvalidPackageFieldError,
    'TRANSFER_PACKAGE_EXPIRED': PackageExpiredError,
    'TRANSFER_DUPLICATE_CONFLICT': DuplicateTransferConflictError,
    'TRANSFER_CHUNK_CHECKSUM_MISMATCH': ChunkChecksumMismatchError,
    'TRANSFER_CHUNK_INDEX_OUT_OF_RANGE': ChunkIndexOutOfRangeError,
    'TRANSFER_CHUNK_SIZE_INVALID': ChunkSizeInvalidError,
    'TRANSFER_STATE_INVALID': InvalidTransferStateError,
    'TRANSFER_CHUNKS_MISSING': MissingChunksError,
    'TRANSFER_FILE_HASH_MISMATCH': FileHashMismatchError,
}

_HTTP_STATUS_ERRORS = {
    400: InvalidPackageFieldError,
    401: SignatureInvalidError,
    403: RouteNotAllowedError,
    404: PackageNotFoundError,
    409: TransferError,
    410: PackageExpiredError,
    413: ChunkSizeInvalidError,
    422: FileHashMismatchError,
}


class RemoteTransferClient(RemoteTransferClientABC):
    """远端 transfer_agent HTTP 客户端（ACL）。"""

    def __init__(self, base_url: str, token: str, timeout_seconds: int = 30,
                 session: Optional[requests.Session] = None):
        self._base_url = base_url.rstrip('/')
        self._token = token
        self._timeout = timeout_seconds
        self._session = session or requests.Session()

    # ---- 出站端口实现 ----
    def create_transfer(self, fields: Dict) -> Dict:
        body = dict(fields)
        body.setdefault('token', self._token)
        return self._request('POST', '/internal/transfer/packages', json_body=body)

    def get_transfer_status(self, transfer_id: str) -> Dict:
        return self._request(
            'GET', f'/internal/transfer/packages/{transfer_id}',
        )

    def upload_chunk(self, transfer_id: str, chunk_index: int,
                     data: bytes, checksum: str) -> Dict:
        headers = {
            'Content-Type': 'application/octet-stream',
            'X-Transfer-Token': self._token,
            'X-Chunk-Checksum': checksum,
        }
        return self._request(
            'POST', f'/internal/transfer/chunks?transfer_id={transfer_id}&chunk_index={chunk_index}',
            data=data, headers=headers,
        )

    def complete_transfer(self, transfer_id: str) -> Dict:
        return self._request(
            'POST', f'/internal/transfer/packages/{transfer_id}/complete',
            headers={'X-Transfer-Token': self._token},
        )

    # ---- 内部：请求与错误转译 ----
    def _request(self, method: str, path: str, **kwargs) -> Dict:
        url = f'{self._base_url}{path}'
        try:
            resp = self._session.request(method, url, timeout=self._timeout, **kwargs)
        except requests.RequestException as e:
            raise TransferError(f'远端 transfer_agent 不可达: {url} ({e})') from e
        return self._parse(resp, url)

    @staticmethod
    def _parse(resp: requests.Response, url: str) -> Dict:
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        if resp.status_code >= 400 or not payload.get('success', False):
            detail = payload.get('detail') or {}
            if isinstance(detail, dict):
                code = detail.get('code', '')
                message = detail.get('message', resp.text[:200])
            else:
                code, message = '', str(detail)
            if code in _CODE_ERRORS:
                raise _CODE_ERRORS[code](message)
            err_cls = _HTTP_STATUS_ERRORS.get(resp.status_code, TransferError)
            raise err_cls(f'{url} -> HTTP {resp.status_code}: {message}')
        data = payload.get('data')
        return data if isinstance(data, dict) else {}
