# -*- coding: utf-8 -*-
"""INT-2488 AES-256-GCM 密钥库（§6.4-2 / §6.4-7 / §13-7）。"""
import base64
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.domain.exceptions import (
    CredentialDecryptError, CredentialKeyUnavailable,
)
from agent_service.infrastructure.llm.credential_store import CredentialStore

KEY1 = base64.b64encode(b'k' * 32).decode()
KEY2 = base64.b64encode(b'j' * 32).decode()
PLAINTEXT = 'sk-live-1234567890abcdef'


@pytest.fixture()
def store():
    return CredentialStore.from_secret(KEY1)


def test_roundtrip(store):
    secret = store.encrypt(PLAINTEXT, owner_id=7, provider_id='p1')
    assert secret.key_version == 1
    assert PLAINTEXT not in secret.ciphertext
    assert store.decrypt(secret.ciphertext, key_version=secret.key_version,
                         owner_id=7, provider_id='p1') == PLAINTEXT


def test_nonce_is_unique_per_record(store):
    a = store.encrypt(PLAINTEXT, owner_id=7, provider_id='p1')
    b = store.encrypt(PLAINTEXT, owner_id=7, provider_id='p1')
    assert a.ciphertext != b.ciphertext


def test_aad_binds_owner_and_provider(store):
    secret = store.encrypt(PLAINTEXT, owner_id=7, provider_id='p1')
    with pytest.raises(CredentialDecryptError):
        store.decrypt(secret.ciphertext, key_version=1,
                      owner_id=8, provider_id='p1')
    with pytest.raises(CredentialDecryptError):
        store.decrypt(secret.ciphertext, key_version=1,
                      owner_id=7, provider_id='p2')


def test_tampered_ciphertext_rejected(store):
    secret = store.encrypt(PLAINTEXT, owner_id=7, provider_id='p1')
    blob = bytearray(base64.b64decode(secret.ciphertext))
    blob[-1] ^= 0xFF
    with pytest.raises(CredentialDecryptError):
        store.decrypt(base64.b64encode(bytes(blob)).decode(),
                      key_version=1, owner_id=7, provider_id='p1')


def test_key_rotation_old_records_still_decrypt():
    old_store = CredentialStore(keyring={1: b'k' * 32}, current_version=1)
    old_secret = old_store.encrypt(PLAINTEXT, owner_id=7, provider_id='p1')

    rotated = CredentialStore(keyring={1: b'k' * 32, 2: b'j' * 32},
                              current_version=2)
    # 旧记录仍可解密
    assert rotated.decrypt(old_secret.ciphertext, key_version=1,
                           owner_id=7, provider_id='p1') == PLAINTEXT
    # 新写入用新版本
    new_secret = rotated.encrypt(PLAINTEXT, owner_id=7, provider_id='p2')
    assert new_secret.key_version == 2
    assert rotated.decrypt(new_secret.ciphertext, key_version=2,
                           owner_id=7, provider_id='p2') == PLAINTEXT
    # 缺旧版本时明确失败
    only_new = CredentialStore(keyring={2: b'j' * 32}, current_version=2)
    with pytest.raises(CredentialKeyUnavailable):
        only_new.decrypt(old_secret.ciphertext, key_version=1,
                         owner_id=7, provider_id='p1')


def test_mask_format():
    assert CredentialStore.mask('sk-1234567890abcdef') == 'sk-****cdef'
    assert CredentialStore.mask('sk-abc') == '****'
    assert CredentialStore.mask('') == ''
    # 样本 Key 的掩码不得包含完整 Key
    masked = CredentialStore.mask(PLAINTEXT)
    assert masked == 'sk-****cdef'
    assert PLAINTEXT not in masked


def test_prod_requires_master_key(monkeypatch):
    monkeypatch.setenv('LOG_ENVIRONMENT', 'prod')
    monkeypatch.delenv('AGENT_CREDENTIAL_MASTER_KEY', raising=False)
    with pytest.raises(CredentialKeyUnavailable):
        CredentialStore.from_env()


def test_prod_rejects_weak_material(monkeypatch):
    monkeypatch.setenv('LOG_ENVIRONMENT', 'prod')
    monkeypatch.setenv('AGENT_CREDENTIAL_MASTER_KEY', 'dev-short-value')
    with pytest.raises(CredentialKeyUnavailable):
        CredentialStore.from_env()


def test_dev_allows_missing_key_but_encrypt_fails(monkeypatch):
    monkeypatch.setenv('LOG_ENVIRONMENT', 'dev')
    monkeypatch.delenv('AGENT_CREDENTIAL_MASTER_KEY', raising=False)
    store = CredentialStore.from_env()
    assert store.available() is False
    with pytest.raises(CredentialKeyUnavailable):
        store.encrypt(PLAINTEXT, owner_id=7, provider_id='p1')


def test_env_supports_json_keyring(monkeypatch):
    monkeypatch.setenv('LOG_ENVIRONMENT', 'dev')
    monkeypatch.setenv('AGENT_CREDENTIAL_MASTER_KEY',
                       '{"1": "%s", "2": "%s"}' % (KEY1, KEY2))
    monkeypatch.setenv('AGENT_CREDENTIAL_KEY_VERSION', '2')
    store = CredentialStore.from_env()
    secret = store.encrypt(PLAINTEXT, owner_id=1, provider_id='p1')
    assert secret.key_version == 2
    assert store.decrypt(secret.ciphertext, key_version=2,
                         owner_id=1, provider_id='p1') == PLAINTEXT
