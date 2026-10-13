# -*- coding: utf-8 -*-
"""INT-245 双 padding 降级单测：主 kid=OAEP(SHA-256) / 降级 kid=PKCS1v15。

WebCrypto subtle 仅存在于安全上下文（https/localhost），http+LAN-IP 访问
时前端走 jsencrypt PKCS1v15 + 降级公钥（INT-245）。覆盖：
- 降级密钥自动生成落盘、kid 独立稳定、与主 kid 不同；
- decrypt_password 按 kid 归属分派算法（OAEP / PKCS1v15 round-trip）；
- 交叉填充（OAEP 密文报降级 kid / PKCS1v15 密文报主 kid）与未知 kid
  一律拒绝（kid 即算法绑定）；
- 降级路径未配置（fallback_key_path=None）时降级 kid 拒绝；
- 公钥端点同时下发主/降级两套（真实路由）；登录路由（表单契约）收
  降级 kid PKCS1v15 密文可达凭据校验，主路径不回退。
"""
import base64
import os
import tempfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int245_') + '/unit.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from api_gateway.application.services.auth.password_encryption import (
    PasswordEncryptionError,
    PasswordEncryptionService,
)


@pytest.fixture()
def primary_key_path(tmp_path):
    return str(tmp_path / 'auth_key.pem')


@pytest.fixture()
def fallback_key_path(tmp_path):
    return str(tmp_path / 'auth_key_fallback.pem')


@pytest.fixture()
def primary_info(primary_key_path):
    return PasswordEncryptionService.get_public_key_info(primary_key_path)


@pytest.fixture()
def fallback_info(fallback_key_path):
    return PasswordEncryptionService.get_fallback_public_key_info(
        fallback_key_path)


def _encrypt_oaep(public_pem: str, password: str) -> bytes:
    public_key = serialization.load_pem_public_key(public_pem.encode('utf-8'))
    return public_key.encrypt(
        password.encode('utf-8'),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )


def _encrypt_pkcs1v15(public_pem: str, password: str) -> bytes:
    """模拟 jsencrypt（PKCS#1 v1.5，纯 JS）产出的密文。"""
    public_key = serialization.load_pem_public_key(public_pem.encode('utf-8'))
    return public_key.encrypt(password.encode('utf-8'), padding.PKCS1v15())


class TestFallbackKeyManagement:

    def test_fallback_key_auto_generated_and_persisted(self, fallback_key_path):
        assert not os.path.exists(fallback_key_path)
        public_pem, kid = PasswordEncryptionService. \
            get_fallback_public_key_info(fallback_key_path)
        assert os.path.exists(fallback_key_path)
        assert '-----BEGIN PUBLIC KEY-----' in public_pem
        assert len(kid) == 32 and all(c in '0123456789abcdef' for c in kid)

    def test_fallback_kid_stable_across_reloads(self, fallback_key_path):
        _, kid1 = PasswordEncryptionService.get_fallback_public_key_info(
            fallback_key_path)
        PasswordEncryptionService._fallback_private_key = None
        PasswordEncryptionService._fallback_key_path = None
        _, kid2 = PasswordEncryptionService.get_fallback_public_key_info(
            fallback_key_path)
        assert kid1 == kid2

    def test_primary_and_fallback_kids_distinct(self, primary_info,
                                                fallback_info):
        """密钥成对独立 → kid 天然不同（kid 即算法绑定的前提）。"""
        assert primary_info[1] != fallback_info[1]

    def test_fallback_and_primary_same_path_reuses_primary_kid(
            self, primary_key_path):
        """误配置（两路径同文件）不产生第二把密钥：主 kid 优先命中。"""
        _, kid = PasswordEncryptionService.get_fallback_public_key_info(
            primary_key_path)
        assert kid == PasswordEncryptionService.get_public_key_info(
            primary_key_path)[1]


class TestKidDispatchedDecrypt:

    def test_oaep_round_trip_with_primary_kid(self, primary_info,
                                              primary_key_path):
        public_pem, kid = primary_info
        ciphertext = base64.b64encode(
            _encrypt_oaep(public_pem, 'S3cret-密码!')).decode()
        assert PasswordEncryptionService.decrypt_password(
            ciphertext, kid, primary_key_path) == 'S3cret-密码!'

    def test_pkcs1v15_round_trip_with_fallback_kid(
            self, fallback_info, fallback_key_path, primary_key_path):
        """jsencrypt 语义：PKCS1v15 密文 + 降级 kid → 解密成功。"""
        public_pem, kid = fallback_info
        ciphertext = base64.b64encode(
            _encrypt_pkcs1v15(public_pem, 'S3cret-密码!')).decode()
        assert PasswordEncryptionService.decrypt_password(
            ciphertext, kid, primary_key_path,
            fallback_key_path=fallback_key_path) == 'S3cret-密码!'

    def test_oaep_ciphertext_with_fallback_kid_rejected(
            self, primary_info, fallback_info, fallback_key_path,
            primary_key_path):
        """kid 即算法绑定：OAEP 密文报降级 kid → PKCS1v15 解密必失败。"""
        fb_pem, fb_kid = fallback_info
        ciphertext = base64.b64encode(_encrypt_oaep(fb_pem, 'pw123456')).decode()
        with pytest.raises(PasswordEncryptionError):
            PasswordEncryptionService.decrypt_password(
                ciphertext, fb_kid, primary_key_path,
                fallback_key_path=fallback_key_path)

    def test_pkcs1v15_ciphertext_with_primary_kid_rejected(
            self, primary_info, primary_key_path, fallback_key_path):
        pub_pem, kid = primary_info
        ciphertext = base64.b64encode(
            _encrypt_pkcs1v15(pub_pem, 'pw123456')).decode()
        with pytest.raises(PasswordEncryptionError):
            PasswordEncryptionService.decrypt_password(
                ciphertext, kid, primary_key_path,
                fallback_key_path=fallback_key_path)

    def test_unknown_kid_rejected(self, primary_key_path, fallback_key_path,
                                  primary_info, fallback_info):
        pub_pem, _ = primary_info
        ciphertext = base64.b64encode(_encrypt_oaep(pub_pem, 'pw123456')).decode()
        for bad_kid in ('0' * 32, fallback_info[1] + '0'):
            with pytest.raises(PasswordEncryptionError):
                PasswordEncryptionService.decrypt_password(
                    ciphertext, bad_kid, primary_key_path,
                    fallback_key_path=fallback_key_path)

    def test_fallback_kid_without_fallback_path_rejected(
            self, fallback_info, primary_key_path):
        """降级路径未配置（旧部署形态）：降级 kid 不可用，拒绝不崩溃。"""
        fb_pem, fb_kid = fallback_info
        ciphertext = base64.b64encode(
            _encrypt_pkcs1v15(fb_pem, 'pw123456')).decode()
        with pytest.raises(PasswordEncryptionError):
            PasswordEncryptionService.decrypt_password(
                ciphertext, fb_kid, primary_key_path, fallback_key_path=None)

    def test_pkcs1v15_non_utf8_plaintext_rejected(
            self, fallback_info, fallback_key_path, primary_key_path):
        """与 OAEP 同语义：PKCS1v15 解出非 UTF-8 字节收敛为加密错误。"""
        fb_pem, fb_kid = fallback_info
        public_key = serialization.load_pem_public_key(fb_pem.encode('utf-8'))
        ciphertext = public_key.encrypt(
            b'\xff\xfe\x00\x9c not-utf8 \x80', padding.PKCS1v15())
        with pytest.raises(PasswordEncryptionError):
            PasswordEncryptionService.decrypt_password(
                base64.b64encode(ciphertext).decode(), fb_kid,
                primary_key_path, fallback_key_path=fallback_key_path)


# ---- 路由层（真实 auth_bp：公钥下发 + 登录表单契约）----

class TestAuthRoutesDualPadding:

    @pytest.fixture()
    def client(self, monkeypatch, tmp_path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api_gateway.config.config import Config
        from api_gateway.application.services.auth.auth_service import (
            AuthService,
        )
        from api_gateway.routes.auth_bp import router as auth_router

        monkeypatch.setattr(
            Config, 'AUTH_RSA_KEY_PATH', str(tmp_path / 'auth_key.pem'))
        monkeypatch.setattr(
            Config, 'AUTH_RSA_FALLBACK_KEY_PATH',
            str(tmp_path / 'auth_key_fallback.pem'))
        monkeypatch.setattr(Config, 'AUTH_PASSWORD_ENCRYPTION_ENABLED', True)
        monkeypatch.setattr(
            AuthService, 'login_with_password',
            staticmethod(lambda u, p: {
                'access_token': 'tk-int245', 'token_type': 'bearer',
                'user': {'username': u},
            }))
        app = FastAPI()
        app.include_router(auth_router, prefix='/api/v1/auth')
        return TestClient(app, raise_server_exceptions=False)

    def _key_payload(self, client) -> dict:
        resp = client.get('/api/v1/auth/login/encryption-key')
        assert resp.status_code == 200, resp.text
        return resp.json().get('data') or resp.json()

    def test_payload_contains_primary_and_fallback(self, client):
        body = self._key_payload(client)
        assert body['enabled'] is True
        assert body['kid'] and 'BEGIN PUBLIC KEY' in body['public_key']
        assert body['fallback']['kid'], '降级公钥未随响应下发（INT-245）'
        assert 'BEGIN PUBLIC KEY' in body['fallback']['public_key']
        assert body['fallback']['kid'] != body['kid']

    def _submit(self, client, username, ciphertext, kid):
        return client.post('/api/v1/auth/login', data={
            'username': username,
            'password_encrypted': ciphertext,
            'encryption_key_id': kid,
        })

    def test_login_via_fallback_kid_pkcs1v15(self, client):
        """http+IP 降级链路：降级 kid + PKCS1v15 密文 → 登录可达。"""
        body = self._key_payload(client)
        ciphertext = base64.b64encode(
            _encrypt_pkcs1v15(body['fallback']['public_key'],
                              'pass245')).decode()
        resp = self._submit(client, 'u245', ciphertext, body['fallback']['kid'])
        assert resp.status_code == 200, resp.text
        assert resp.json().get('access_token') == 'tk-int245'

    def test_login_via_primary_kid_oaep_no_regression(self, client):
        """安全上下文主路径不回退：主 kid + OAEP 密文 → 登录可达。"""
        body = self._key_payload(client)
        ciphertext = base64.b64encode(
            _encrypt_oaep(body['public_key'], 'pass245')).decode()
        resp = self._submit(client, 'u245', ciphertext, body['kid'])
        assert resp.status_code == 200, resp.text
        assert resp.json().get('access_token') == 'tk-int245'

    def test_login_cross_padding_rejected_401(self, client):
        """OAEP 密文报降级 kid → 路由层 401 加密语义（不落凭据校验）。"""
        from api_gateway.utils.error_codes import ErrorCode
        body = self._key_payload(client)
        ciphertext = base64.b64encode(
            _encrypt_oaep(body['fallback']['public_key'],
                          'pass245')).decode()
        resp = self._submit(client, 'u245', ciphertext, body['fallback']['kid'])
        assert resp.status_code == 401, resp.text
        assert resp.json()['code'] == ErrorCode.AUTH_ENCRYPTION_INVALID
