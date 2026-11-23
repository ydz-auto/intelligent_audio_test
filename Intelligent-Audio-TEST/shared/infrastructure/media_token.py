# -*- coding: utf-8 -*-
"""媒体取流短效签名 token。

背景：浏览器 `<audio>/<video>` 无法携带 `Authorization` 头，网关又对取流端点
做鉴权（AUTH_MODE=dev/prod）。若把用户 JWT 塞进 URL 容易被 nginx 访问日志 /
浏览器历史泄露。这里改为：取流 URL 内嵌一枚「绑定对象路径 + 过期时间」的
HMAC 签名 token，网关校验后仅授予 `audio:read` 权限。

签名密钥优先取 `MEDIA_TOKEN_SECRET`；缺省回落到 OSS_SECRET_KEY 派生值——
各服务（网关验签 / 任务·音频服务签发）共享同一 OSS 凭据，无需额外部署配置。
"""
from __future__ import annotations

import hashlib
import hmac
import time

from shared.infrastructure.config import BaseConfig

# 默认有效期（秒）：够一次试听/重试，过期后重新取 stream 端点换新地址
DEFAULT_TTL = 3600


def _secret() -> bytes:
    explicit = (getattr(BaseConfig, 'MEDIA_TOKEN_SECRET', '') or '').strip()
    if explicit:
        return explicit.encode('utf-8')
    base = f'iat-media|{BaseConfig.OSS_SECRET_KEY}'
    return hashlib.sha256(base.encode('utf-8')).digest()


def _signature(path: str, exp: int) -> str:
    payload = f'{path}|{exp}'.encode('utf-8')
    return hmac.new(_secret(), payload, hashlib.sha256).hexdigest()


def sign_media_token(path: str, ttl: int = DEFAULT_TTL) -> str:
    """为对象路径签发短效 token：`{exp}.{hmac}`。"""
    exp = int(time.time()) + int(ttl)
    return f'{exp}.{_signature(path, exp)}'


def verify_media_token(path: str, token: str) -> bool:
    """校验 token：格式、过期时间、绑定路径与签名一致性。"""
    if not path or not token:
        return False
    try:
        exp_s, sig = token.split('.', 1)
        exp = int(exp_s)
    except (ValueError, AttributeError):
        return False
    if exp < int(time.time()):
        return False
    return hmac.compare_digest(sig, _signature(path, exp))
