# -*- coding: utf-8 -*-
"""评估服务运行时配置（系统设置 → 评估服务）。

数据源：网关内部端点 ``GET /api/internal/eval-config``（X-Internal-Token 校验）。
- 每 5s 最多拉一次；拉取失败静默回退到 env/config.yaml 的静态配置；
- 未配置 ``PLATFORM_INTERNAL_URL`` / ``EVAL_INTERNAL_TOKEN`` 时完全走静态配置；
- 只做「覆盖」：系统设置为空的字段不覆盖静态值，保证不配也能正常评估。
"""
import logging
import os
import threading
import time
from typing import Any, Dict, Tuple

import requests

logger = logging.getLogger(__name__)

PLATFORM_URL_ENV = 'PLATFORM_INTERNAL_URL'
INTERNAL_TOKEN_ENV = 'EVAL_INTERNAL_TOKEN'
CACHE_TTL_SECONDS = 5.0
HTTP_TIMEOUT_SECONDS = 3.0

# 选项键常量（与 shared/config/eval_settings.py 同口径）
KEY_LLM_API_BASE = 'eval.llm.api_base'
KEY_LLM_API_KEY = 'eval.llm.api_key'
KEY_LLM_DEFAULT_MODEL = 'eval.llm.default_model'
KEY_LLM_MAX_TOKENS = 'eval.llm.max_tokens'
KEY_LLM_TEMPERATURE = 'eval.llm.temperature'
KEY_LLM_TIMEOUT = 'eval.llm.timeout'
KEY_LLM_AUDIO_COMPRESS = 'eval.llm.audio_compress'
KEY_ASR_URL = 'eval.asr.url'
KEY_ASR_TIMEOUT = 'eval.asr.timeout'

_lock = threading.Lock()
_cached_at = 0.0
_cached: Dict[str, Any] = {}


def _fetch() -> Dict[str, Any]:
    base = (os.environ.get(PLATFORM_URL_ENV) or '').rstrip('/')
    token = os.environ.get(INTERNAL_TOKEN_ENV) or ''
    if not base or not token:
        return {}
    try:
        resp = requests.get(
            f'{base}/api/internal/eval-config',
            headers={'X-Internal-Token': token},
            timeout=HTTP_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            logger.debug('运行时评估配置拉取失败: HTTP %s', resp.status_code)
            return {}
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # 网络异常不打断评估主流程
        logger.debug('运行时评估配置拉取异常: %s', exc)
        return {}


def get() -> Dict[str, Any]:
    """带 TTL 的运行时配置（异常时返回上次成功值或空 dict）。"""
    global _cached, _cached_at
    now = time.monotonic()
    with _lock:
        if _cached and now - _cached_at < CACHE_TTL_SECONDS:
            return _cached
    data = _fetch()
    with _lock:
        if data:
            _cached = data
            _cached_at = now
        return _cached


def _option(data: Dict[str, Any], key: str) -> Any:
    options = data.get('options') or {}
    return options.get(key)


def _secret(data: Dict[str, Any], key: str) -> str:
    secrets = data.get('secrets') or {}
    value = secrets.get(key)
    return value.strip() if isinstance(value, str) else ''


def merge_llm(base: Dict[str, Any]) -> Dict[str, Any]:
    """把系统设置里的 LLM 配置覆盖到静态配置上（空值不覆盖）。"""
    data = get()
    cfg = dict(base or {})
    api_base = _option(data, KEY_LLM_API_BASE)
    if isinstance(api_base, str) and api_base.strip():
        cfg['api_base_url'] = api_base.strip()
    api_key = _secret(data, KEY_LLM_API_KEY)
    if api_key:
        cfg['api_key'] = api_key
    default_model = _option(data, KEY_LLM_DEFAULT_MODEL)
    if isinstance(default_model, str) and default_model.strip():
        cfg['default_model'] = default_model.strip()

    dimension_models = dict(cfg.get('dimension_models') or {})
    for dim, model in (data.get('dimensionModels') or {}).items():
        if isinstance(model, str) and model.strip():
            dimension_models[dim] = model.strip()
    cfg['dimension_models'] = dimension_models

    for key, cfg_key in (
        (KEY_LLM_MAX_TOKENS, 'max_tokens'),
        (KEY_LLM_TIMEOUT, 'timeout'),
    ):
        value = _option(data, key)
        if isinstance(value, (int, float)) and value > 0:
            cfg[cfg_key] = int(value)

    temperature = _option(data, KEY_LLM_TEMPERATURE)
    if isinstance(temperature, (int, float)) and temperature >= 0:
        cfg['temperature'] = float(temperature)

    audio_compress = _option(data, KEY_LLM_AUDIO_COMPRESS)
    if isinstance(audio_compress, str) and audio_compress.strip():
        cfg['audio_compress'] = audio_compress.strip()
    return cfg


def asr_settings(default_url: str, default_timeout: int) -> Tuple[str, int]:
    """ASR 地址与超时（系统设置优先，缺省回落 env）。"""
    data = get()
    url = _option(data, KEY_ASR_URL)
    url = url.strip().rstrip('/') if isinstance(url, str) and url.strip() else default_url
    timeout = _option(data, KEY_ASR_TIMEOUT)
    if isinstance(timeout, (int, float)) and timeout > 0:
        return url, int(timeout)
    return url, default_timeout
