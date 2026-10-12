# -*- coding: utf-8 -*-
"""密码 RSA 加密传输服务（INT-147 对齐旧库 auth 登录安全基线）。

对齐 V9.7.10 backend/services/auth/crypto.py 契约：
- RSA-2048 OAEP(SHA-256)；私钥 PKCS#8 PEM 持久化，首次访问自动生成；
- kid = 公钥 SPKI DER 的 SHA-256 前 32 hex，防旧公钥密文重放；
- 解密失败统一抛 PasswordEncryptionError（对外收敛为登录失败语义，
  不向未认证客户端暴露密码学细节）。

归属：api_gateway（transport 安全关注点在 HTTP 边界终结，gRPC 内网
链路仍传明文密码，与 TLS 终结于网关同理）。
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import threading

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

logger = logging.getLogger(__name__)

_RSA_KEY_BITS = 2048
_RSA_PUBLIC_EXPONENT = 65537
_KID_HEX_LEN = 32


class PasswordEncryptionError(Exception):
    """密码加解密失败（调用方映射为与凭证错误一致的 401/400 语义）。"""


class PasswordEncryptionService:
    """RSA 密钥管理与密码解密（进程内缓存私钥，路径变更时自动重载）。"""

    _lock = threading.Lock()
    _private_key = None
    _key_path: str | None = None

    # ---- 查询侧 ----

    @classmethod
    def get_public_key_info(cls, key_path: str) -> tuple:
        """返回 (public_key_pem, kid)。私钥文件不存在时自动生成。"""
        private_key = cls._get_active_private_key(key_path)
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode('utf-8')
        return public_pem, cls._kid(private_key)

    # ---- 解密侧 ----

    @classmethod
    def decrypt_password(cls, ciphertext_b64: str, key_id: str,
                         key_path: str) -> str:
        """解密前端提交的 RSA 密文（base64），返回明文密码。

        校验顺序：kid 一致 → base64 → 密文长度 = 密钥字节数 → OAEP 解密
        → 非空 → UTF-8。任一失败抛 PasswordEncryptionError（INT-147 审计
        P4：OAEP 合法但明文非 UTF-8 字节时不得逃逸 UnicodeDecodeError）。
        """
        if not ciphertext_b64 or not key_id:
            raise PasswordEncryptionError(
                'password encryption payload is invalid')
        private_key = cls._get_active_private_key(key_path)
        if key_id != cls._kid(private_key):
            raise PasswordEncryptionError(
                'password encryption payload is invalid')
        try:
            ciphertext = base64.b64decode(ciphertext_b64)
        except Exception as exc:
            raise PasswordEncryptionError(
                'password encryption payload is invalid') from exc
        if len(ciphertext) != private_key.key_size // 8:
            raise PasswordEncryptionError(
                'password encryption payload is invalid')
        try:
            plaintext = private_key.decrypt(
                ciphertext,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )
        except Exception as exc:
            raise PasswordEncryptionError(
                'password encryption payload is invalid') from exc
        if not plaintext:
            raise PasswordEncryptionError(
                'password encryption payload is invalid')
        try:
            return plaintext.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise PasswordEncryptionError(
                'password encryption payload is invalid') from exc

    # ---- 内部方法 ----

    @classmethod
    def _get_active_private_key(cls, key_path: str):
        with cls._lock:
            if (cls._private_key is None or cls._key_path != key_path):
                cls._private_key = cls._load_or_create_private_key(key_path)
                cls._key_path = key_path
            return cls._private_key

    @staticmethod
    def _load_or_create_private_key(key_path: str):
        """加载 PEM 私钥；文件不存在时生成 RSA-2048 并写盘（dev 自举）。"""
        if os.path.exists(key_path):
            with open(key_path, 'r', encoding='utf-8') as f:
                return serialization.load_pem_private_key(
                    f.read().encode('utf-8'), password=None)
        private_key = rsa.generate_private_key(
            public_exponent=_RSA_PUBLIC_EXPONENT,
            key_size=_RSA_KEY_BITS,
        )
        os.makedirs(os.path.dirname(key_path) or '.', exist_ok=True)
        with open(key_path, 'w', encoding='utf-8') as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ).decode('utf-8'))
        logger.info('已生成登录密码加密 RSA 私钥: %s', key_path)
        return private_key

    @staticmethod
    def _kid(private_key) -> str:
        """kid = 公钥 SPKI DER SHA-256 前 32 hex（对齐旧库 public_key_info）。"""
        public_der = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return hashlib.sha256(public_der).hexdigest()[:_KID_HEX_LEN]
