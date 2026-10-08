# -*- coding: utf-8 -*-
"""签名服务 — 5 层安全基座的访问控制层 + 签名层。

- 访问层：预共享 Token 比对（TOKEN_A_B / TOKEN_B_C，来源：环境变量或
  shared/config/secrets_config.json），缺失或不匹配即拒绝（fail-closed）。
- 签名层：TransferPackage 规范串 HMAC-SHA256 验签，防止网关白名单内篡改。

密钥不做任何硬编码默认值；路由未配置 token 时所有请求一律拒绝。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Dict, Optional

from transfer_agent.domain.errors import AccessTokenInvalidError, SignatureInvalidError


class SignatureService:
    """预共享 Token + HMAC-SHA256 签名验证。"""

    def __init__(self, tokens: Dict[str, str]):
        # 键归一：TOKEN_A_B / A_B 两种写法统一为 route_key('A_B')，
        # 一对站点双向共用预共享 token
        self._tokens = {}
        for key, value in (tokens or {}).items():
            if not value:
                continue
            norm = str(key).upper()
            if norm.startswith('TOKEN_'):
                norm = norm[len('TOKEN_'):]
            self._tokens[norm] = value

    @staticmethod
    def route_key(src_zone: str, dst_zone: str) -> str:
        return '_'.join(sorted([src_zone.upper(), dst_zone.upper()]))

    def get_token(self, src_zone: str, dst_zone: str) -> Optional[str]:
        return self._tokens.get(self.route_key(src_zone, dst_zone))

    # ---- 访问控制层 ----
    def verify_token(self, src_zone: str, dst_zone: str, token: Optional[str]) -> None:
        expected = self.get_token(src_zone, dst_zone)
        if not expected or not token or not hmac.compare_digest(str(token), expected):
            raise AccessTokenInvalidError(
                f'路由 {src_zone}->{dst_zone} 预共享 token 缺失或不匹配'
            )

    # ---- 签名层 ----
    CANONICAL_FIELDS = (
        'transfer_id', 'pkg_type', 'src_zone', 'dst_zone', 'category', 'key',
        'file_hash', 'file_size', 'ttl_seconds', 'timestamp',
    )

    @staticmethod
    def canonical_string(
        transfer_id: str,
        pkg_type: str,
        src_zone: str,
        dst_zone: str,
        category: str,
        key: str,
        file_hash: str,
        file_size: int,
        ttl_seconds: int,
        timestamp: str,
    ) -> str:
        """传输包规范串 — 字段序固定，任何字段被篡改都会导致验签失败。"""
        return '|'.join([
            str(transfer_id), str(pkg_type), str(src_zone), str(dst_zone),
            str(category), str(key), str(file_hash), str(int(file_size)),
            str(int(ttl_seconds)), str(timestamp),
        ])

    @classmethod
    def compute_signature(cls, secret: str, **fields) -> str:
        try:
            canonical = cls.canonical_string(**{k: fields[k] for k in cls.CANONICAL_FIELDS})
        except KeyError as e:
            raise SignatureInvalidError(f'签名缺少必要字段: {e}') from e
        return hmac.new(
            secret.encode('utf-8'), canonical.encode('utf-8'), hashlib.sha256,
        ).hexdigest()

    def verify_signature(self, fields: dict) -> None:
        """验签：fields 为传输包协议字段（含 signature），任一字段被篡改即失败。"""
        provided = str(fields.get('signature') or '')
        src_zone = str(fields.get('src_zone') or '').upper()
        dst_zone = str(fields.get('dst_zone') or '').upper()
        secret = self.get_token(src_zone, dst_zone)
        if not secret:
            raise SignatureInvalidError(f'路由 {src_zone}->{dst_zone} 未配置签名密钥')
        signable = {k: v for k, v in fields.items() if k != 'signature'}
        expected = self.compute_signature(secret, **signable)
        if not hmac.compare_digest(expected, provided):
            raise SignatureInvalidError(
                f'transfer {fields.get("transfer_id")} HMAC-SHA256 验签失败'
            )


def load_tokens_from_secrets_file(path: str) -> Dict[str, str]:
    """从 secrets_config.json 读取预共享 token（{"TOKEN_A_B": "...", ...}）。"""
    if not path or not os.path.isfile(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f) or {}
    return {str(k).upper(): str(v) for k, v in data.items() if str(k).upper().startswith('TOKEN_') and v}
