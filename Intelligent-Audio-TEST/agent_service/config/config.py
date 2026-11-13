# -*- coding: utf-8 -*-
"""agent_service 领域配置。

所有预算、阈值、超时、并发数与模型参数一律配置化（env + 本目录
``agent_defaults.json``），代码中不硬编码。环境变量前缀 ``AGENT_``；
模型调用不再读服务端统一 LLM Key / model（§6.4）：base_url / model /
protocol / api_key 全部来自用户自己的 ``agent_llm_provider``，本文件只保留
运行时超时 / 温度 / 流式选项与「有效窗口 → 预算」的派生系数。
"""
import json
import os

from shared.config.service_ports import AGENT_SERVICE_HTTP_PORT
from shared.infrastructure.config import BaseConfig, _get_bool, _get_float, _get_int


def _load_defaults() -> dict:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'agent_defaults.json')
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        # 配置文件缺失/损坏不阻断启动：全部预算仍可由环境变量给出
        return {}


_DEFAULTS = _load_defaults()
_BUDGET_DEFAULTS = _DEFAULTS.get('budget', {})
_CONTEXT_DEFAULTS = _DEFAULTS.get('context', {})
_STREAM_DEFAULTS = _DEFAULTS.get('event_stream', {})


class Config(BaseConfig):
    """agent_service 配置（HTTP 端口 5011，见 shared/config/service_ports.py）。"""

    PORT = _get_int('PORT', AGENT_SERVICE_HTTP_PORT)
    SERVICE_NAME = 'agent_service'
    DB_POOL_SIZE = _get_int('AGENT_DB_POOL_SIZE', 5)

    # ===== LLM 运行时参数（供应商由用户自带，见下）=====
    LLM_TIMEOUT_SECONDS = _get_float('LLM_TIMEOUT_SECONDS', 60.0)
    LLM_TEMPERATURE = _get_float('LLM_TEMPERATURE', 0.2)
    LLM_STREAM_INCLUDE_USAGE = _get_bool('LLM_STREAM_INCLUDE_USAGE', True)
    ANTHROPIC_VERSION = os.environ.get('ANTHROPIC_VERSION', '2023-06-01')

    # ===== 用户模型供应商 / 加密密钥库（§6.4）=====
    # 平台 Key 分支不实现：开关只保留 false 位，置 true 即拒绝启动。
    AGENT_ALLOW_PLATFORM_KEY = _get_bool('AGENT_ALLOW_PLATFORM_KEY', False)
    # 主密钥：单个 base64 32 字节值，或 JSON 对象 {"版本": "密钥"} 支持轮换
    CREDENTIAL_MASTER_KEY = os.environ.get('AGENT_CREDENTIAL_MASTER_KEY', '')
    CREDENTIAL_KEY_VERSION = _get_int('AGENT_CREDENTIAL_KEY_VERSION', 1)
    # 模型目录；空 = 用 agent_service/config/model_catalog.json
    MODEL_CATALOG_PATH = os.environ.get('AGENT_MODEL_CATALOG_PATH', '').strip()
    PROVIDER_VERIFY_TIMEOUT_SECONDS = _get_float(
        'AGENT_PROVIDER_VERIFY_TIMEOUT_SECONDS', 10.0)
    # 预算与压缩阈值按有效窗口 W 派生（§8.3），不写死 128k
    TOKEN_BUDGET_MULTIPLIER_DEFAULT = _get_int(
        'AGENT_TOKEN_BUDGET_MULTIPLIER_DEFAULT', 2)
    TOKEN_BUDGET_MULTIPLIER_AUTO = _get_int(
        'AGENT_TOKEN_BUDGET_MULTIPLIER_AUTO', 4)
    OUTPUT_TOKEN_RATIO = _get_float('AGENT_OUTPUT_TOKEN_RATIO', 0.10)
    OUTPUT_TOKEN_CAP = _get_int('AGENT_OUTPUT_TOKEN_CAP', 8192)
    COMPACTION_SOFT_RATIO = _get_float('AGENT_COMPACTION_SOFT_RATIO', 0.60)
    COMPACTION_HARD_RATIO = _get_float('AGENT_COMPACTION_HARD_RATIO', 0.80)

    # ===== 能否直连（网关转发时必带 X-User-Id）=====
    AUTH_REQUIRED = _get_bool('AGENT_AUTH_REQUIRED', True)
    DEFAULT_TENANT_ID = os.environ.get('AGENT_DEFAULT_TENANT_ID', 'default')

    # ===== 每 run 预算（§9.3）=====
    MAX_ROUNDS = _get_int('AGENT_MAX_ROUNDS', int(_BUDGET_DEFAULTS.get('max_rounds', 12)))
    MAX_TOOL_CALLS = _get_int(
        'AGENT_MAX_TOOL_CALLS', int(_BUDGET_DEFAULTS.get('max_tool_calls', 40)))
    # 0 = 按有效上下文窗口派生（默认 2×W，见 TOKEN_BUDGET_MULTIPLIER_*）；
    # 显式正数作为运营方的硬上限（取 min）。
    MAX_TOKENS = _get_int('AGENT_MAX_TOKENS', int(_BUDGET_DEFAULTS.get('max_tokens', 0)))
    MAX_DURATION_SECONDS = _get_int(
        'AGENT_MAX_DURATION_SECONDS', int(_BUDGET_DEFAULTS.get('max_duration_seconds', 600)))
    MAX_OUTPUT_BYTES = _get_int(
        'AGENT_MAX_OUTPUT_BYTES', int(_BUDGET_DEFAULTS.get('max_output_bytes', 262144)))
    MAX_CONSECUTIVE_TOOL_FAILURES = _get_int(
        'AGENT_MAX_CONSECUTIVE_TOOL_FAILURES',
        int(_DEFAULTS.get('max_consecutive_tool_failures', 3)))

    # ===== 并发 =====
    WORKER_CONCURRENCY = _get_int(
        'AGENT_WORKER_CONCURRENCY', int(_DEFAULTS.get('worker_concurrency', 4)))
    TOOL_MAX_CONCURRENCY = _get_int(
        'AGENT_TOOL_MAX_CONCURRENCY', int(_DEFAULTS.get('tool_max_concurrency', 8)))
    TOOL_RESULT_MAX_CHARS = _get_int(
        'AGENT_TOOL_RESULT_MAX_CHARS', int(_DEFAULTS.get('tool_result_max_chars', 8000)))
    # 流式期间回读取消标志的间隔（每 N 个片段查一次 DB），避免每片段一次查询
    CANCEL_DB_CHECK_EVERY = _get_int('AGENT_CANCEL_DB_CHECK_EVERY', 16)
    # 重建上下文 / 恢复时单 run 扫描事件的页上限
    EVENT_SCAN_LIMIT = _get_int('AGENT_EVENT_SCAN_LIMIT', 10000)

    # ===== 上下文（§5.1 第 1 步；压缩由 m0-04 落地）=====
    CONTEXT_MAX_RUNS = _get_int(
        'AGENT_CONTEXT_MAX_RUNS', int(_CONTEXT_DEFAULTS.get('max_runs', 20)))
    CONTEXT_MAX_MESSAGES = _get_int(
        'AGENT_CONTEXT_MAX_MESSAGES', int(_CONTEXT_DEFAULTS.get('max_messages', 120)))
    CONTEXT_RECENT_MESSAGES = _get_int(
        'AGENT_CONTEXT_RECENT_MESSAGES', int(_CONTEXT_DEFAULTS.get('recent_messages', 50)))
    SYSTEM_PROMPT = os.environ.get(
        'AGENT_SYSTEM_PROMPT', _DEFAULTS.get('system_prompt', ''))

    # ===== SSE 事件流（§11）=====
    EVENT_PAGE_SIZE = _get_int(
        'AGENT_EVENT_PAGE_SIZE', int(_STREAM_DEFAULTS.get('page_size', 200)))
    EVENT_POLL_INTERVAL_SECONDS = _get_float(
        'AGENT_EVENT_POLL_INTERVAL_SECONDS',
        float(_STREAM_DEFAULTS.get('poll_interval_seconds', 0.5)))
    EVENT_HEARTBEAT_SECONDS = _get_float(
        'AGENT_EVENT_HEARTBEAT_SECONDS',
        float(_STREAM_DEFAULTS.get('heartbeat_seconds', 15)))
    # 终态先落、run_finished 事件后落库的窗口内，SSE 最多再等多久
    EVENT_TERMINAL_GRACE_SECONDS = _get_float(
        'AGENT_EVENT_TERMINAL_GRACE_SECONDS',
        float(_STREAM_DEFAULTS.get('terminal_grace_seconds', 5)))
    # redis：发布唤醒消息（正文仍回表读）；local：仅进程内唤醒 + 轮询
    EVENT_WAKEUP_BACKEND = os.environ.get('AGENT_EVENT_WAKEUP_BACKEND', 'redis').strip().lower()
    # 勤务通道：与现有 EventChannel 五通道隔离，只作 wakeup，不承载事件正文
    EVENT_CHANNEL = (BaseConfig.EVENT_CHANNEL_PREFIX or '') + 'agent_run_wakeup'

    # ===== 重启恢复（§9.2）=====
    RECOVERY_ON_STARTUP = _get_bool('AGENT_RECOVERY_ON_STARTUP', True)

    @classmethod
    def budget_defaults(cls) -> dict:
        return {
            'max_rounds': cls.MAX_ROUNDS,
            'max_tool_calls': cls.MAX_TOOL_CALLS,
            'max_tokens': cls.MAX_TOKENS,
            'max_duration_seconds': cls.MAX_DURATION_SECONDS,
            'max_output_bytes': cls.MAX_OUTPUT_BYTES,
        }

    @classmethod
    def validate(cls):
        super().validate()
        if cls.WORKER_CONCURRENCY <= 0:
            raise ValueError('AGENT_WORKER_CONCURRENCY 必须为正数')
        if cls.AGENT_ALLOW_PLATFORM_KEY:
            raise ValueError(
                'AGENT_ALLOW_PLATFORM_KEY 只保留 false 开关位：'
                '平台 Key 分支未实现，禁止开启')
        if cls.LOG_ENVIRONMENT == 'prod' and not cls.CREDENTIAL_MASTER_KEY:
            raise ValueError(
                '生产环境缺少 AGENT_CREDENTIAL_MASTER_KEY，拒绝启动')
        if not 0 < cls.OUTPUT_TOKEN_RATIO <= 1:
            raise ValueError('AGENT_OUTPUT_TOKEN_RATIO 必须在 (0, 1] 内')
        if not 0 < cls.COMPACTION_SOFT_RATIO < cls.COMPACTION_HARD_RATIO <= 1:
            raise ValueError(
                'AGENT_COMPACTION_SOFT_RATIO / HARD_RATIO 必须满足 '
                '0 < soft < hard <= 1')
        if cls.TOKEN_BUDGET_MULTIPLIER_DEFAULT <= 0 \
                or cls.TOKEN_BUDGET_MULTIPLIER_AUTO <= 0:
            raise ValueError('AGENT_TOKEN_BUDGET_MULTIPLIER_* 必须为正数')
