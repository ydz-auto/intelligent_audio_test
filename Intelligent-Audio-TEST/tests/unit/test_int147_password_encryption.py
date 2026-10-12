# -*- coding: utf-8 -*-
"""登录密码 RSA 加密传输单测（INT-147 对齐旧库 crypto.py 契约）。

覆盖 PasswordEncryptionService 纯密码学逻辑（不依赖 DB/gRPC）：
- 私钥首次访问自动生成并落盘，二次加载同钥（kid 稳定）；
- OAEP(SHA-256) 加解密 round-trip；
- kid 不一致（旧公钥密文重放）/ 密文篡改 / 长度不符 / 空入参 一律拒绝。
"""
import base64
import os
import tempfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int147_') + '/unit.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from api_gateway.application.services.auth.password_encryption import (
    PasswordEncryptionError,
    PasswordEncryptionService,
)


@pytest.fixture()
def key_path(tmp_path):
    return str(tmp_path / 'auth_key.pem')


@pytest.fixture()
def key_pair(key_path):
    """初始化服务并返回 (public_pem, kid)。"""
    return PasswordEncryptionService.get_public_key_info(key_path)


def _encrypt(public_pem: str, password: str) -> bytes:
    public_key = serialization.load_pem_public_key(public_pem.encode('utf-8'))
    return public_key.encrypt(
        password.encode('utf-8'),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )


class TestKeyManagement:

    def test_key_auto_generated_and_persisted(self, key_path):
        assert not os.path.exists(key_path)
        public_pem, kid = PasswordEncryptionService.get_public_key_info(key_path)
        assert os.path.exists(key_path)
        assert '-----BEGIN PUBLIC KEY-----' in public_pem
        assert len(kid) == 32 and all(c in '0123456789abcdef' for c in kid)

    def test_kid_stable_across_reloads(self, key_path):
        _, kid1 = PasswordEncryptionService.get_public_key_info(key_path)
        # 强制重载（对齐进程重启语义：缓存按路径失效后从盘加载）
        PasswordEncryptionService._private_key = None
        PasswordEncryptionService._key_path = None
        _, kid2 = PasswordEncryptionService.get_public_key_info(key_path)
        assert kid1 == kid2


class TestDecryptRoundTrip:

    def test_round_trip(self, key_pair, key_path):
        public_pem, kid = key_pair
        ciphertext = base64.b64encode(_encrypt(public_pem, 'S3cret-密码!')).decode()
        assert PasswordEncryptionService.decrypt_password(
            ciphertext, kid, key_path) == 'S3cret-密码!'

    def test_wrong_kid_rejected(self, key_pair, key_path):
        public_pem, _ = key_pair
        ciphertext = base64.b64encode(_encrypt(public_pem, 'pw123456')).decode()
        with pytest.raises(PasswordEncryptionError):
            PasswordEncryptionService.decrypt_password(
                ciphertext, '0' * 32, key_path)

    def test_tampered_ciphertext_rejected(self, key_pair, key_path):
        public_pem, kid = key_pair
        raw = bytearray(_encrypt(public_pem, 'pw123456'))
        raw[0] ^= 0xFF
        with pytest.raises(PasswordEncryptionError):
            PasswordEncryptionService.decrypt_password(
                base64.b64encode(bytes(raw)).decode(), kid, key_path)

    def test_wrong_length_rejected(self, key_pair, key_path):
        _, kid = key_pair
        with pytest.raises(PasswordEncryptionError):
            PasswordEncryptionService.decrypt_password(
                base64.b64encode(b'short').decode(), kid, key_path)

    @pytest.mark.parametrize('ciphertext,kid', [
        ('', ''),
        ('', 'a' * 32),
        ('x' * 16, ''),
        ('not-base64-!!!', 'a' * 32),
    ])
    def test_invalid_inputs_rejected(self, key_pair, key_path, ciphertext, kid):
        with pytest.raises(PasswordEncryptionError):
            PasswordEncryptionService.decrypt_password(ciphertext, kid, key_path)
