# -*- coding: utf-8 -*-
"""评估运行时配置客户端（服务间只读）。

调用网关内部端点 ``GET /api/internal/eval-config``（X-Internal-Token），
5s TTL 缓存；未配置地址/token 或请求失败时返回空配置，调用方回落 env 默认值。
仅用于服务端内部消费，禁止把 ``secrets`` 下的明文写日志或下发前端。
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

PLATFORM_URL_ENV = 'PLATFORM_INTERNAL_URL'
INTERNAL_TOKEN_ENV = 'INTERNAL_EVAL_CONFIG_TOKEN'
CACHE_TTL_SECONDS = 5.0
HTTP_TIMEOUT_SECONDS = 3.0

# 评估配置键（与 shared/config/eval_settings.py 同口径的关键子集）
KEY_LLM_API_KEY = 'eval.llm.api_key'
KEY_RELAY_SELF_ZONE = 'eval.relay.self_zone'
KEY_RELAY_HUB_ZONE = 'eval.relay.hub_zone'
KEY_RELAY_SYNC_BACK_ZONE = 'eval.relay.sync_back_zone'
KEY_RELAY_TRIGGER_ENABLED = 'eval.relay.trigger_enabled'
KEY_RELAY_FALLBACK_URLS = 'eval.relay.fallback_urls'
KEY_RELAY_C_API_BASE_URL = 'eval.relay.c_api_base_url'
KEY_RELAY_TOKEN_A_B = 'eval.relay.token_a_b'
KEY_RELAY_TOKEN_B_C = 'eval.relay.token_b_c'


class EvalConfigClient:
    """带 TTL 缓存的评估运行时配置读取器（单例）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cached_at = 0.0
        self._cached: Dict[str, Any] = {}

    def _fetch(self) -> Dict[str, Any]:
        base = (os.environ.get(PLATFORM_URL_ENV) or '').rstrip('/')
        token = os.environ.get(INTERNAL_TOKEN_ENV) or ''
        if not base or not token:
            return {}
        request = urllib.request.Request(
            f'{base}/api/internal/eval-config',
            headers={'X-Internal-Token': token})
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data if isinstance(data, dict) else {}
        except (urllib.error.URLError, ValueError, OSError):
            return {}

    def get(self) -> Dict[str, Any]:
        """当前运行时配置（失败返回上次成功值或空 dict）。"""
        now = time.monotonic()
        with self._lock:
            if self._cached and now - self._cached_at < CACHE_TTL_SECONDS:
                return self._cached
        data = self._fetch()
        with self._lock:
            if data:
                self._cached = data
                self._cached_at = now
            return self._cached

    def option(self, key: str) -> Optional[Any]:
        """普通项覆盖值（未配置返回 None）。"""
        return (self.get().get('options') or {}).get(key)

    def secret(self, key: str) -> Optional[str]:
        """密钥明文（未配置返回 None；禁止记录日志）。"""
        value = (self.get().get('secrets') or {}).get(key)
        return value if isinstance(value, str) and value else None


eval_config_client = EvalConfigClient()
