# -*- coding: utf-8 -*-
"""用户模型 Key 加密存储（§6.4-2 / §6.4-7 / §13-7）。

口径：
- AES-256-GCM；每条记录独立随机 nonce（12 字节），nonce 与密文一起 base64
  落 ``api_key_ciphertext``；
- AAD 绑定 ``owner_id + provider_id``：把 A 的记录搬到 B 名下解密必然失败；
- 主密钥来自 ``AGENT_CREDENTIAL_MASTER_KEY``，支持多版本轮换：环境变量可以是
  单个密钥（当前版本由 ``AGENT_CREDENTIAL_KEY_VERSION`` 指定），也可以是
  JSON 对象（``{"1": "<base64>", "2": "<base64>"}``），旧版本仍在 keyring 里
  就能解密旧记录；
- 只存密文与掩码，不存明文；日志只记事件名与 provider_id，绝不记 Key；
- 生产缺少主密钥 fail-fast；开发环境允许显式配置 dev 值，但必须是 32 字节
  base64/hex，否则拒绝（避免把弱口令当密钥用）。
"""
import base64
import binascii
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from agent_service.domain.exceptions import (
    CredentialDecryptError, CredentialKeyUnavailable,
)

logger = logging.getLogger(__name__)

KEY_BYTES = 32          # AES-256
NONCE_BYTES = 12        # GCM 推荐 96-bit nonce
MASK_SUFFIX_LEN = 4
DEFAULT_KEY_VERSION = 1


@dataclass(frozen=True)
class EncryptedSecret:
    """加密结果：密文（base64）与主密钥版本。"""

    ciphertext: str
    key_version: int


def _decode_material(raw: str) -> Optional[bytes]:
    """把配置值解析成 32 字节密钥；无法解析返回 None（不臆造派生密钥）。"""
    value = (raw or '').strip()
    if not value:
        return None
    for altchars in (None, b'-_'):
        try:
            decoded = base64.b64decode(value, altchars=altchars,
                                       validate=True)
        except (binascii.Error, ValueError):
            continue
        if len(decoded) == KEY_BYTES:
            return decoded
    if len(value) == KEY_BYTES * 2:
        try:
            return bytes.fromhex(value)
        except ValueError:
            return None
    return None


def _parse_keyring(raw: str, version: int,
                   environment: str) -> Tuple[Dict[int, bytes], int]:
    raw = (raw or '').strip()
    if not raw:
        if environment == 'prod':
            raise CredentialKeyUnavailable(
                '生产环境缺少 AGENT_CREDENTIAL_MASTER_KEY，拒绝启动')
        logger.warning(
            'AGENT_CREDENTIAL_MASTER_KEY 未配置：供应商 Key 保存/解密将不可用'
            '（仅允许开发环境，生产必须配置 32 字节主密钥）')
        return {}, version

    keyring: Dict[int, bytes] = {}
    if raw.startswith('{'):
        try:
            parsed = json.loads(raw)
        except ValueError as exc:
            raise CredentialKeyUnavailable(
                'AGENT_CREDENTIAL_MASTER_KEY 不是合法 JSON') from exc
        if not isinstance(parsed, dict) or not parsed:
            raise CredentialKeyUnavailable(
                'AGENT_CREDENTIAL_MASTER_KEY JSON 必须是非空对象 {版本: 密钥}')
        for version_key, material in parsed.items():
            try:
                key_version = int(version_key)
            except (TypeError, ValueError) as exc:
                raise CredentialKeyUnavailable(
                    'AGENT_CREDENTIAL_MASTER_KEY 版本号必须是整数') from exc
            decoded = _decode_material(str(material))
            if decoded is None:
                raise CredentialKeyUnavailable(
                    f'AGENT_CREDENTIAL_MASTER_KEY 版本 {key_version} 不是 '
                    f'{KEY_BYTES} 字节 base64/hex 密钥')
            keyring[key_version] = decoded
        if version not in keyring:
            raise CredentialKeyUnavailable(
                f'当前版本 {version} 不在 AGENT_CREDENTIAL_MASTER_KEY keyring 中')
        return keyring, version

    decoded = _decode_material(raw)
    if decoded is None:
        if environment == 'prod':
            raise CredentialKeyUnavailable(
                f'AGENT_CREDENTIAL_MASTER_KEY 必须是 {KEY_BYTES} 字节 base64/hex')
        # 开发环境兜底：低熵值派生，打告警但可用（生产已在上面拒绝）
        logger.warning(
            'AGENT_CREDENTIAL_MASTER_KEY 不是 %d 字节 base64/hex，已按 SHA-256 '
            '派生（仅限开发环境）', KEY_BYTES)
        decoded = hashlib.sha256(raw.encode('utf-8')).digest()
    keyring[version] = decoded
    return keyring, version


class CredentialStore:
    """AES-256-GCM 加解密器；不持有任何明文。"""

    def __init__(self, *, keyring: Mapping[int, bytes],
                 current_version: int = DEFAULT_KEY_VERSION,
                 environment: str = 'dev'):
        self._keyring = {int(k): bytes(v) for k, v in (keyring or {}).items()}
        self._current_version = int(current_version)
        self._environment = (environment or 'dev').lower()
        if self._environment == 'prod' and not self._keyring:
            raise CredentialKeyUnavailable(
                '生产环境缺少 AGENT_CREDENTIAL_MASTER_KEY，拒绝启动')

    # ------------------------------------------------------------ factories

    @classmethod
    def from_env(cls) -> 'CredentialStore':
        environment = os.environ.get('LOG_ENVIRONMENT', 'dev').strip().lower()
        raw_version = os.environ.get('AGENT_CREDENTIAL_KEY_VERSION',
                                     str(DEFAULT_KEY_VERSION)).strip()
        try:
            version = int(raw_version)
        except ValueError as exc:
            raise CredentialKeyUnavailable(
                'AGENT_CREDENTIAL_KEY_VERSION 必须是整数') from exc
        keyring, version = _parse_keyring(
            os.environ.get('AGENT_CREDENTIAL_MASTER_KEY', ''), version,
            environment)
        return cls(keyring=keyring, current_version=version,
                   environment=environment)

    @classmethod
    def from_secret(cls, secret: str,
                    version: int = DEFAULT_KEY_VERSION) -> 'CredentialStore':
        """测试 / 内部工具：用单个 base64 或原始 32 字节密钥构造。"""
        key = _decode_material(secret)
        if key is None:
            raw = (secret or '').encode('utf-8')
            if len(raw) != KEY_BYTES:
                raise CredentialKeyUnavailable(
                    f'主密钥必须是 {KEY_BYTES} 字节 base64/hex 或原始 '
                    f'{KEY_BYTES} 字节')
            key = raw
        return cls(keyring={version: key}, current_version=version)

    # ------------------------------------------------------------ properties

    @property
    def current_version(self) -> int:
        return self._current_version

    def available(self) -> bool:
        return bool(self._keyring)

    # ------------------------------------------------------------ crypto

    @staticmethod
    def aad(owner_id: int, provider_id: str) -> bytes:
        return f'{int(owner_id)}:{provider_id}'.encode('utf-8')

    def _key(self, version: int) -> bytes:
        key = self._keyring.get(int(version))
        if key is None:
            raise CredentialKeyUnavailable(
                f'主密钥版本 {version} 未配置（轮换期间需保留旧版本）')
        return key

    def encrypt(self, plaintext: str, *, owner_id: int,
                provider_id: str) -> EncryptedSecret:
        if not self._keyring:
            raise CredentialKeyUnavailable(
                'AGENT_CREDENTIAL_MASTER_KEY 未配置，无法保存供应商 Key')
        key = self._key(self._current_version)
        nonce = os.urandom(NONCE_BYTES)
        blob = AESGCM(key).encrypt(
            nonce, (plaintext or '').encode('utf-8'),
            self.aad(owner_id, provider_id))
        return EncryptedSecret(
            ciphertext=base64.b64encode(nonce + blob).decode('ascii'),
            key_version=self._current_version,
        )

    def decrypt(self, ciphertext: str, *, key_version: int, owner_id: int,
                provider_id: str) -> str:
        if not ciphertext:
            raise CredentialDecryptError('密文为空')
        try:
            blob = base64.b64decode(ciphertext, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise CredentialDecryptError('密文不是合法 base64') from exc
        if len(blob) <= NONCE_BYTES:
            raise CredentialDecryptError('密文长度非法')
        key = self._key(key_version)
        try:
            plaintext = AESGCM(key).decrypt(
                blob[:NONCE_BYTES], blob[NONCE_BYTES:],
                self.aad(owner_id, provider_id))
        except InvalidTag as exc:
            raise CredentialDecryptError(
                '密文校验失败（密钥版本 / AAD 不匹配或数据被篡改）') from exc
        return plaintext.decode('utf-8')

    # ------------------------------------------------------------ masking

    @staticmethod
    def mask(api_key: str) -> str:
        """``sk-xxxxxxxxabcd`` → ``sk-****abcd``；过短的 Key 只留 ``****``。"""
        key = (api_key or '').strip()
        if not key:
            return ''
        # 太短的 Key 去掉末 4 位后几乎不剩信息，直接全遮
        if len(key) < 12:
            return '****'
        prefix = ''
        if '-' in key:
            head = key.split('-', 1)[0]
            if 2 <= len(head) <= 8 and head.isalpha():
                prefix = head + '-'
        return f'{prefix}****{key[-MASK_SUFFIX_LEN:]}'


__all__ = ['CredentialStore', 'EncryptedSecret', 'KEY_BYTES', 'NONCE_BYTES']
