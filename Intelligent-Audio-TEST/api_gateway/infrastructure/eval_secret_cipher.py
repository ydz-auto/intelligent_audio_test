# -*- coding: utf-8 -*-
"""评估配置密钥加解密（AES-256-GCM）。

口径对齐 agent_service 的 CredentialStore（同一套算法，独立主密钥）：
- 每条记录独立随机 nonce（12 字节），与密文一起 base64 落库；
- AAD 绑定选项键：把 A 键的密文挪到 B 键必然解密失败；
- 主密钥来自 ``EVAL_CONFIG_MASTER_KEY``（32 字节 base64/hex）；
- 未配置主密钥时 fail-closed：密钥保存/解密接口返回明确错误，不静默降级明文。
"""
import base64
import binascii
import os
import threading
from typing import Optional, Tuple

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_BYTES = 32
NONCE_BYTES = 12
MASK_SUFFIX_LEN = 4
MASTER_KEY_ENV = 'EVAL_CONFIG_MASTER_KEY'

_lock = threading.Lock()
_cached_key: Optional[bytes] = None


class EvalSecretUnavailable(RuntimeError):
    """主密钥未配置或不可用（调用方应返回 503 并提示运维配置）。"""


class EvalSecretDecryptError(RuntimeError):
    """密文损坏 / 主密钥不匹配。"""


def _decode_material(raw: str) -> Optional[bytes]:
    value = (raw or '').strip()
    if not value:
        return None
    try:
        decoded = base64.b64decode(value, validate=True)
        if len(decoded) == KEY_BYTES:
            return decoded
    except (binascii.Error, ValueError):
        pass
    if len(value) == KEY_BYTES * 2:
        try:
            return bytes.fromhex(value)
        except ValueError:
            return None
    return None


def _master_key() -> bytes:
    """读取并缓存主密钥；缺失/非法时抛 EvalSecretUnavailable。"""
    global _cached_key
    with _lock:
        if _cached_key is not None:
            return _cached_key
        decoded = _decode_material(os.environ.get(MASTER_KEY_ENV, ''))
        if decoded is None:
            raise EvalSecretUnavailable(
                f'{MASTER_KEY_ENV} 未配置或不是 {KEY_BYTES} 字节 base64/hex，'
                '评估密钥的保存与解密不可用')
        _cached_key = decoded
        return decoded


def available() -> bool:
    """主密钥是否可用（不抛异常）。"""
    try:
        _master_key()
        return True
    except EvalSecretUnavailable:
        return False


def encrypt(key: str, plaintext: str) -> Tuple[str, int]:
    """加密明文，返回 (base64(nonce + blob), key_version=1)。"""
    master = _master_key()
    nonce = os.urandom(NONCE_BYTES)
    blob = AESGCM(master).encrypt(
        nonce, (plaintext or '').encode('utf-8'), key.encode('utf-8'))
    return base64.b64encode(nonce + blob).decode('ascii'), 1


def decrypt(key: str, ciphertext: str, key_version: int = 1) -> str:
    """解密（AAD = 选项键）；失败抛 EvalSecretDecryptError。"""
    master = _master_key()
    try:
        blob = base64.b64decode(ciphertext, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise EvalSecretDecryptError('密文不是合法 base64') from exc
    if len(blob) <= NONCE_BYTES:
        raise EvalSecretDecryptError('密文长度非法')
    try:
        plaintext = AESGCM(master).decrypt(
            blob[:NONCE_BYTES], blob[NONCE_BYTES:], key.encode('utf-8'))
    except InvalidTag as exc:
        raise EvalSecretDecryptError('密文校验失败（主密钥变更或数据被篡改）') from exc
    return plaintext.decode('utf-8')


def mask(value: str) -> str:
    """``sk-xxxxxxxxabcd`` → ``sk-****abcd``；过短只留 ``****``。"""
    text = (value or '').strip()
    if not text:
        return ''
    if len(text) < 12:
        return '****'
    prefix = ''
    if '-' in text:
        head = text.split('-', 1)[0]
        if 2 <= len(head) <= 8 and head.isalpha():
            prefix = head + '-'
    return f'{prefix}****{text[-MASK_SUFFIX_LEN:]}'
