# -*- coding: utf-8 -*-
"""EVAL_REQUEST / EVAL_RESULT 传输链路出站客户端（ACL 防腐层）。

对接本区/中枢 transfer_agent 的 /internal/transfer/* 收包契约（发送侧），
将远端错误响应转译为 ThirdPartyEvalError（防腐：传输协议细节不外泄到调用方）。
签名使用与接收侧一致的 HMAC-SHA256 规范串（集成测试经真实接收端验签守护契约一致）。
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


class ThirdPartyEvalError(Exception):
    """第三方评估链路错误（传输/适配/校验统一异常）。"""


# 规范串字段序必须与 transfer_agent 接收侧 SignatureService.CANONICAL_FIELDS 一致
_CANONICAL_FIELDS = (
    'transfer_id', 'pkg_type', 'src_zone', 'dst_zone', 'category', 'key',
    'file_hash', 'file_size', 'ttl_seconds', 'timestamp',
)


def compute_transfer_signature(secret: str, **fields) -> str:
    """HMAC-SHA256 传输包签名（与 transfer_agent SignatureService 规范一致）。"""
    canonical = '|'.join([
        str(fields[name]) for name in _CANONICAL_FIELDS
    ])
    return hmac.new(secret.encode('utf-8'), canonical.encode('utf-8'), hashlib.sha256).hexdigest()


def load_transfer_tokens(secrets_file: Optional[str] = None) -> Dict[str, str]:
    """预共享 token 装载（环境变量优先，shared/config/secrets_config.json 兜底）。

    与 transfer_agent.config.Config.transfer_tokens 同源同格式（fail-closed：
    路由未配置 token 时传输链路拒绝发出）。
    """
    tokens: Dict[str, str] = {}
    path = secrets_file or os.path.join(_REPO_ROOT, 'shared', 'config', 'secrets_config.json')
    if path and os.path.isfile(path):
        try:
            import json
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f) or {}
            for key, value in data.items():
                norm = str(key).upper()
                if norm.startswith('TOKEN_') and value:
                    tokens[norm[len('TOKEN_'):]] = str(value)
        except Exception:
            logger.warning('secrets_config.json 读取失败，忽略: %s', path, exc_info=True)
    for env_key in ('TRANSFER_TOKEN_A_B', 'TRANSFER_TOKEN_B_C'):
        val = os.environ.get(env_key, '')
        if val:
            tokens[env_key.replace('TRANSFER_TOKEN_', '', 1)] = val
    return tokens


class TransferEvalClient:
    """transfer_agent /internal/transfer/* 发送侧客户端（EVAL 传输链路专用）。

    契约：收包（/packages、/chunks、/complete、/audit）+ 出站投递
    （/outbound/{transfer_id}/dispatch，B→C 数据面，F2.1/INT-49 起）。
    """

    def __init__(self, base_url: str, tokens: Dict[str, str],
                 timeout_seconds: int = 120, chunk_size: int = 4 * 1024 * 1024,
                 dispatch_timeout_seconds: Optional[int] = None,
                 session: Optional[requests.Session] = None):
        self._base_url = base_url.rstrip('/')
        self._tokens = dict(tokens or {})
        self._timeout = timeout_seconds
        self._chunk_size = chunk_size
        # 出站投递同步等待 C 端执行（T-B 侧含重试退避），超时须大于其最坏投递时长
        self._dispatch_timeout = dispatch_timeout_seconds or max(timeout_seconds, 600)
        self._session = session or requests.Session()

    @property
    def tokens(self) -> Dict[str, str]:
        return dict(self._tokens)

    def get_token(self, src_zone: str, dst_zone: str) -> Optional[str]:
        route = '_'.join(sorted([src_zone.upper(), dst_zone.upper()]))
        return self._tokens.get(route)

    def create_transfer(self, fields: Dict, token: str) -> Dict:
        body = dict(fields)
        return self._request('POST', '/internal/transfer/packages',
                             json_body=body, token=token)

    def get_transfer(self, transfer_id: str, token: str) -> Dict:
        return self._request('GET', f'/internal/transfer/audit/{transfer_id}',
                             token=token)

    def get_transfer_status(self, transfer_id: str, token: str) -> Dict:
        return self._request('GET', f'/internal/transfer/packages/{transfer_id}',
                             token=token)

    def upload_chunk(self, transfer_id: str, chunk_index: int, data: bytes,
                     checksum: str, token: str) -> Dict:
        return self._request(
            'POST',
            f'/internal/transfer/chunks?transfer_id={transfer_id}&chunk_index={chunk_index}',
            data=data, token=token,
            headers={
                'Content-Type': 'application/octet-stream',
                'X-Chunk-Checksum': checksum,
            })

    def complete_transfer(self, transfer_id: str, token: str) -> Dict:
        return self._request('POST', f'/internal/transfer/packages/{transfer_id}/complete',
                             token=token)

    def dispatch_outbound(self, *, transfer_id: str, adapter_kind: str,
                          src_zone: str, dst_zone: str) -> Dict:
        """T-B 出站投递契约（B→C 数据面）：投递暂存包并同步取回投递视图。

        token 取暂存包自身路由（中枢内联 B→C 与中转 A→B 包路由不同）；
        返回 data={'delivered', 'dst_status', 'dst_body', 'dst_text', 'attempts', ...}。
        """
        token = self.get_token(src_zone, dst_zone)
        if not token:
            raise ThirdPartyEvalError(
                f'路由 {src_zone}->{dst_zone} 未配置预共享 token，出站投递拒绝发出（fail-closed）')
        return self._request(
            'POST', f'/internal/transfer/outbound/{transfer_id}/dispatch',
            json_body={'adapter_kind': adapter_kind}, token=token,
            timeout_seconds=self._dispatch_timeout)

    def send_file(self, *, transfer_id: str, pkg_type: str, src_zone: str, dst_zone: str,
                  category: str, key: str, local_path: str, ephemeral: bool = True,
                  ttl_seconds: int = 3600, meta: Optional[Dict] = None) -> Dict:
        """打包→签名→分片上传→完成（幂等：重复调用同 transfer_id 直接去重返回）。"""
        token = self.get_token(src_zone, dst_zone)
        if not token:
            raise ThirdPartyEvalError(
                f'路由 {src_zone}->{dst_zone} 未配置预共享 token，EVAL 传输拒绝发出（fail-closed）')
        file_hash, file_size = self._hash_file(local_path)
        timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
        fields = {
            'transfer_id': transfer_id,
            'pkg_type': pkg_type,
            'src_zone': src_zone,
            'dst_zone': dst_zone,
            'category': category,
            'key': key,
            'file_hash': file_hash,
            'file_size': file_size,
            'ttl_seconds': int(ttl_seconds),
            'timestamp': timestamp,
        }
        fields['signature'] = compute_transfer_signature(token, **fields)
        created = self.create_transfer({**fields, 'meta': meta or {}, 'ephemeral': ephemeral},
                                       token=token)
        if not created.get('dedup', False):
            total = (file_size + self._chunk_size - 1) // self._chunk_size
            with open(local_path, 'rb') as f:
                for index in range(total):
                    data = f.read(self._chunk_size)
                    checksum = hashlib.sha256(data).hexdigest()
                    self.upload_chunk(transfer_id, index, data, checksum, token=token)
        return self.complete_transfer(transfer_id, token=token)

    # ---- 内部 ----
    def _request(self, method: str, path: str, token: str = '',
                 json_body: Optional[Dict] = None, data: Optional[bytes] = None,
                 headers: Optional[Dict] = None,
                 timeout_seconds: Optional[int] = None) -> Dict:
        url = f'{self._base_url}{path}'
        all_headers = {'X-Transfer-Token': token or ''}
        if headers:
            all_headers.update(headers)
        try:
            resp = self._session.request(method, url, json=json_body, data=data,
                                         headers=all_headers,
                                         timeout=timeout_seconds or self._timeout)
        except requests.RequestException as e:
            raise ThirdPartyEvalError(f'transfer_agent 不可达: {url} ({e})') from e
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        if resp.status_code >= 400 or not payload.get('success', False):
            detail = payload.get('detail') or {}
            if isinstance(detail, dict):
                message = detail.get('message') or resp.text[:200]
            else:
                message = str(detail) or resp.text[:200]
            raise ThirdPartyEvalError(
                f'transfer_agent 响应异常 {url} -> HTTP {resp.status_code}: {message}')
        result = payload.get('data')
        return result if isinstance(result, dict) else {}

    @staticmethod
    def _hash_file(local_path: str) -> tuple:
        sha = hashlib.sha256()
        size = 0
        with open(local_path, 'rb') as f:
            while True:
                block = f.read(1024 * 1024)
                if not block:
                    break
                sha.update(block)
                size += len(block)
        return f'sha256:{sha.hexdigest()}', size
