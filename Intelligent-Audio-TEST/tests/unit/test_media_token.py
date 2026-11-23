# -*- coding: utf-8 -*-
"""媒体取流短效签名 token 单元测试。

覆盖：签名/验签往返、错误路径拒绝、篡改拒绝、过期拒绝、空输入拒绝。
"""
import os
import time

os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

from shared.infrastructure.media_token import (
    sign_media_token,
    verify_media_token,
)

_PATH = 'oss://case_result/473/6YF0126211000225/a.wav'


def test_sign_verify_roundtrip():
    token = sign_media_token(_PATH)
    assert token.count('.') == 1
    assert verify_media_token(_PATH, token) is True


def test_wrong_path_rejected():
    token = sign_media_token(_PATH)
    assert verify_media_token('oss://case_result/473/6YF0126211000225/b.wav', token) is False


def test_tampered_token_rejected():
    token = sign_media_token(_PATH)
    exp, sig = token.split('.')
    forged = f"{exp}.{'x' * len(sig)}"
    assert forged != token
    assert verify_media_token(_PATH, forged) is False


def test_expired_token_rejected():
    # ttl=-1 → exp 已过期
    token = sign_media_token(_PATH, ttl=-1)
    assert verify_media_token(_PATH, token) is False


def test_empty_input_rejected():
    assert verify_media_token('', '1.abc') is False
    assert verify_media_token(_PATH, '') is False
    assert verify_media_token(_PATH, 'not-a-token') is False


def test_custom_ttl_still_valid():
    token = sign_media_token(_PATH, ttl=300)
    assert verify_media_token(_PATH, token) is True
