# -*- coding: utf-8 -*-
"""agent_service 领域配置。

所有预算、阈值、超时、并发数与模型参数一律配置化（env + 本目录
``agent_defaults.json``），代码中不硬编码。环境变量前缀 ``AGENT_``；
LLM 四项（base_url / api_key / model / timeout）按卡面口径用 ``LLM_*``，
默认模型待负责人拍板，未配置时服务照常启动，只在该 run 执行时以
``LLM_NOT_CONFIGURED`` 失败。
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

    # ===== LLM（OpenAI 兼容，§12.1）=====
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', '')
    LLM_API_KEY = os.environ.get('LLM_API_KEY') or os.environ.get('OPENAI_API_KEY', '')
    LLM_MODEL = os.environ.get('LLM_MODEL', '')
    LLM_TIMEOUT_SECONDS = _get_float('LLM_TIMEOUT_SECONDS', 60.0)
    LLM_TEMPERATURE = _get_float('LLM_TEMPERATURE', 0.2)
    LLM_MAX_OUTPUT_TOKENS = _get_int('LLM_MAX_OUTPUT_TOKENS', 0)
    LLM_STREAM_INCLUDE_USAGE = _get_bool('LLM_STREAM_INCLUDE_USAGE', True)

    # ===== 能否直连（网关转发时必带 X-User-Id）=====
    AUTH_REQUIRED = _get_bool('AGENT_AUTH_REQUIRED', True)
    DEFAULT_TENANT_ID = os.environ.get('AGENT_DEFAULT_TENANT_ID', 'default')

    # ===== 每 run 预算（§9.3）=====
    MAX_ROUNDS = _get_int('AGENT_MAX_ROUNDS', int(_BUDGET_DEFAULTS.get('max_rounds', 12)))
    MAX_TOOL_CALLS = _get_int(
        'AGENT_MAX_TOOL_CALLS', int(_BUDGET_DEFAULTS.get('max_tool_calls', 40)))
    MAX_TOKENS = _get_int('AGENT_MAX_TOKENS', int(_BUDGET_DEFAULTS.get('max_tokens', 60000)))
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
