# -*- coding: utf-8 -*-
"""评估服务系统设置：密钥加解密 / 掩码 / 运行时配置组装。

覆盖：
- AES-GCM 密文往返 + AAD 绑定（换键解密失败）；
- 掩码规则；
- SystemOptionService.get_runtime_eval_config 的普通项覆盖与密钥解密；
- 未配置主密钥时 upsert_eval_secret 返回 503（fail-closed）。
"""
import base64
import os

import pytest

from api_gateway.infrastructure import eval_secret_cipher
from shared.config.eval_settings import EvalOptionKey, llm_model_key

SECRET_KEY = 'eval.llm.api_key'


def _reset_cipher_cache(monkeypatch):
    monkeypatch.setattr(eval_secret_cipher, '_cached_key', None)


@pytest.fixture()
def master_key(monkeypatch):
    raw = base64.b64encode(os.urandom(32)).decode('ascii')
    monkeypatch.setenv(eval_secret_cipher.MASTER_KEY_ENV, raw)
    _reset_cipher_cache(monkeypatch)
    yield raw
    _reset_cipher_cache(monkeypatch)


class TestCipher:
    def test_roundtrip(self, master_key):
        ciphertext, version = eval_secret_cipher.encrypt(
            SECRET_KEY, 'sk-abcdefgh1234')
        assert version == 1
        assert eval_secret_cipher.decrypt(SECRET_KEY, ciphertext) == 'sk-abcdefgh1234'

    def test_aad_binding_rejects_other_key(self, master_key):
        ciphertext, _ = eval_secret_cipher.encrypt(SECRET_KEY, 'sk-abcdefgh1234')
        with pytest.raises(eval_secret_cipher.EvalSecretDecryptError):
            eval_secret_cipher.decrypt(EvalOptionKey.RELAY_TOKEN_A_B.value, ciphertext)

    def test_mask(self):
        assert eval_secret_cipher.mask('sk-abcdefgh1234') == 'sk-****1234'
        assert eval_secret_cipher.mask('short') == '****'
        assert eval_secret_cipher.mask('') == ''


class TestRuntimeConfig:
    def test_runtime_config_merges_options_and_secrets(self, master_key, monkeypatch):
        from api_gateway.application.services import system_option_service as module

        ciphertext, version = eval_secret_cipher.encrypt(SECRET_KEY, 'sk-live-9999')
        monkeypatch.setattr(module.SystemOptionService, '_repo', _FakeOptionRepo({
            EvalOptionKey.LLM_API_BASE.value: 'https://llm.example/v1',
            EvalOptionKey.LLM_DEFAULT_MODEL.value: 'gpt-test',
            llm_model_key('reject_judge'): 'gpt-audio',
            EvalOptionKey.ASR_URL.value: 'http://asr.local:10095',
            'site.name': '忽略非评估键',
        }))
        monkeypatch.setattr(module.SystemOptionService, '_secret_repo', _FakeSecretRepo({
            SECRET_KEY: {'ciphertext': ciphertext, 'key_version': version},
        }))

        cfg = module.SystemOptionService.get_runtime_eval_config()

        assert cfg['options'][EvalOptionKey.LLM_API_BASE.value] == 'https://llm.example/v1'
        assert 'site.name' not in cfg['options']
        assert llm_model_key('reject_judge') not in cfg['options']
        assert cfg['dimensionModels']['reject_judge'] == 'gpt-audio'
        assert cfg['secrets'][SECRET_KEY] == 'sk-live-9999'

    def test_upsert_secret_fails_closed_without_master_key(self, monkeypatch):
        from api_gateway.application.services import system_option_service as module

        monkeypatch.delenv(eval_secret_cipher.MASTER_KEY_ENV, raising=False)
        _reset_cipher_cache(monkeypatch)

        result = module.SystemOptionService.upsert_eval_secret(
            SECRET_KEY, 'sk-x', updated_by=1)
        _payload, http_code = result
        assert http_code == 503


class _FakeOptionRepo:
    def __init__(self, values):
        self._values = values

    def get_all(self):
        return dict(self._values)

    def upsert(self, key, value):  # pragma: no cover - 本用例不写
        self._values[key] = value


class _FakeSecretRepo:
    def __init__(self, rows):
        self._rows = rows

    def list_meta(self):
        return [{'key': k, 'mask': 'sk-****9999', 'updated_at': None}
                for k in self._rows]

    def get_ciphertext(self, key):
        row = self._rows.get(key)
        return {'key': key, **row} if row else {}

    def upsert(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError('不应走到写库')
