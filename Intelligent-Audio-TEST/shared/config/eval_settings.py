# -*- coding: utf-8 -*-
"""评估服务可配置项（系统设置 → 评估服务）。

键口径与 ``system_options`` 一致：``eval.<分区>.<字段>``。
- 普通项：存 ``system_options``，经 ``GET /api/option/`` 下发；
- 密钥项：存 ``system_option_secrets``（AES-GCM 密文 + 掩码），
  永远不出现在全量 KV 响应里，仅管理员可写、只回显掩码。

运行时消费方：
- eval_server（LLM Judge / ASR）：经网关内部端点读取，env/config.yaml 兜底；
- evaluation_service（第三方评估中转）：同源读取，env/配置文件兜底。

新增字段时改这里 + 前端 ``SYSTEM_OPTION_DEFAULTS``/resolver 即可。
"""
from enum import StrEnum


class EvalOptionKey(StrEnum):
    """评估配置键（域.分区.字段）。"""

    # ── LLM Judge（eval_server）──
    LLM_API_BASE = 'eval.llm.api_base'
    LLM_API_KEY = 'eval.llm.api_key'
    LLM_DEFAULT_MODEL = 'eval.llm.default_model'
    LLM_MAX_TOKENS = 'eval.llm.max_tokens'
    LLM_TEMPERATURE = 'eval.llm.temperature'
    LLM_TIMEOUT = 'eval.llm.timeout'
    LLM_AUDIO_COMPRESS = 'eval.llm.audio_compress'

    # ── ASR（eval_server → asr_server）──
    ASR_URL = 'eval.asr.url'
    ASR_TIMEOUT = 'eval.asr.timeout'

    # ── 第三方评估中转（evaluation_service）──
    RELAY_SELF_ZONE = 'eval.relay.self_zone'
    RELAY_HUB_ZONE = 'eval.relay.hub_zone'
    RELAY_SYNC_BACK_ZONE = 'eval.relay.sync_back_zone'
    RELAY_TRIGGER_ENABLED = 'eval.relay.trigger_enabled'
    RELAY_C_API_BASE_URL = 'eval.relay.c_api_base_url'
    RELAY_FALLBACK_URLS = 'eval.relay.fallback_urls'
    RELAY_TOKEN_A_B = 'eval.relay.token_a_b'
    RELAY_TOKEN_B_C = 'eval.relay.token_b_c'


#: 密钥类键：只进 system_option_secrets，密文落库、掩码回显
EVAL_SECRET_KEYS: frozenset[str] = frozenset({
    EvalOptionKey.LLM_API_KEY.value,
    EvalOptionKey.RELAY_TOKEN_A_B.value,
    EvalOptionKey.RELAY_TOKEN_B_C.value,
})

#: LLM 分维度模型支持的维度标识（与 eval_server config.LLM_JUDGE 对齐）
EVAL_LLM_DIMENSIONS: tuple[str, ...] = (
    'turn_eval', 'high_freq_llm_judge', 'false_takeover', 'reply_quality',
    'interruption_judge', 'reject_judge', 'env_judge',
)


def llm_model_key(dimension: str) -> str:
    """维度专用模型的选项键（一维一键，避免 JSON 对象类型扩散到 KV 契约）。"""
    return f'eval.llm.model.{dimension}'


#: 普通项默认值（未配置时不下发覆盖值；消费方回落 env/config.yaml）
EVAL_OPTION_DEFAULTS: dict = {
    EvalOptionKey.LLM_API_BASE.value: '',
    EvalOptionKey.LLM_DEFAULT_MODEL.value: '',
    EvalOptionKey.LLM_MAX_TOKENS.value: 0,
    EvalOptionKey.LLM_TEMPERATURE.value: -1.0,
    EvalOptionKey.LLM_TIMEOUT.value: 0,
    EvalOptionKey.LLM_AUDIO_COMPRESS.value: '',
    EvalOptionKey.ASR_URL.value: '',
    EvalOptionKey.ASR_TIMEOUT.value: 0,
    EvalOptionKey.RELAY_SELF_ZONE.value: '',
    EvalOptionKey.RELAY_HUB_ZONE.value: '',
    EvalOptionKey.RELAY_SYNC_BACK_ZONE.value: '',
    EvalOptionKey.RELAY_TRIGGER_ENABLED.value: False,
    EvalOptionKey.RELAY_C_API_BASE_URL.value: '',
    EvalOptionKey.RELAY_FALLBACK_URLS.value: [],
}
EVAL_OPTION_DEFAULTS.update({llm_model_key(dim): '' for dim in EVAL_LLM_DIMENSIONS})

#: 全部可写键（校验用）
EVAL_OPTION_KEYS: frozenset[str] = frozenset(
    {key.value for key in EvalOptionKey}
    | {llm_model_key(dim) for dim in EVAL_LLM_DIMENSIONS}
)
