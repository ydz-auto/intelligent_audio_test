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
from pathlib import Path

from shared.config.service_ports import AGENT_SERVICE_HTTP_PORT, API_GATEWAY_PORT
from shared.infrastructure.config import BaseConfig, _get_bool, _get_float, _get_int

_SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_DIR = os.path.dirname(_SERVICE_DIR)


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
_SKILL_DEFAULTS = _DEFAULTS.get('skills', {})


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
    # 预算与压缩阈值按有效窗口 W 派生（§8.3），不写死 128k。
    # AUTO 乘数只保留配置位：run 的 Auto 模式属 M1（INT-2477），M0 尚未接线。
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

    # ===== 上下文（§5.1 第 1 步 + §8 无感压缩）=====
    CONTEXT_MAX_RUNS = _get_int(
        'AGENT_CONTEXT_MAX_RUNS', int(_CONTEXT_DEFAULTS.get('max_runs', 20)))
    CONTEXT_MAX_MESSAGES = _get_int(
        'AGENT_CONTEXT_MAX_MESSAGES', int(_CONTEXT_DEFAULTS.get('max_messages', 120)))
    CONTEXT_RECENT_MESSAGES = _get_int(
        'AGENT_CONTEXT_RECENT_MESSAGES', int(_CONTEXT_DEFAULTS.get('recent_messages', 50)))
    # 最近 N 轮原文永不压缩（§8.4-6，N 配置化）
    CONTEXT_KEEP_RECENT_TURNS = _get_int(
        'AGENT_CONTEXT_KEEP_RECENT_TURNS',
        int(_CONTEXT_DEFAULTS.get('keep_recent_turns', 3)))
    # L1：摘要长度 / 单条摘要上限 / 大结果外置阈值（字符）
    CONTEXT_TOOL_SUMMARY_CHARS = _get_int(
        'AGENT_CONTEXT_TOOL_SUMMARY_CHARS',
        int(_CONTEXT_DEFAULTS.get('tool_summary_chars', 600)))
    CONTEXT_MAX_SUMMARY_CHARS = _get_int(
        'AGENT_CONTEXT_MAX_SUMMARY_CHARS',
        int(_CONTEXT_DEFAULTS.get('max_summary_chars', 2400)))
    CONTEXT_ARTIFACT_THRESHOLD_CHARS = _get_int(
        'AGENT_CONTEXT_ARTIFACT_THRESHOLD_CHARS',
        int(_CONTEXT_DEFAULTS.get('artifact_threshold_chars', 4000)))
    # 外置上传的有界等待（秒）：OSS 不可用时快速降级为截断，不拖住 Loop
    CONTEXT_ARTIFACT_TIMEOUT_SECONDS = _get_float(
        'AGENT_CONTEXT_ARTIFACT_TIMEOUT_SECONDS',
        float(_CONTEXT_DEFAULTS.get('artifact_timeout_seconds', 10.0)))
    # L2：列表只留计数 + TopN + 查询入口
    CONTEXT_LIST_TOP_N = _get_int(
        'AGENT_CONTEXT_LIST_TOP_N',
        int(_CONTEXT_DEFAULTS.get('list_top_n', 5)))
    CONTEXT_LIST_TRIM_THRESHOLD_CHARS = _get_int(
        'AGENT_CONTEXT_LIST_TRIM_THRESHOLD_CHARS',
        int(_CONTEXT_DEFAULTS.get('list_trim_threshold_chars', 1200)))
    CONTEXT_MAX_KEY_FIELDS = _get_int(
        'AGENT_CONTEXT_MAX_KEY_FIELDS',
        int(_CONTEXT_DEFAULTS.get('max_key_fields', 24)))
    # L3 备忘单轮输出上限
    CONTEXT_MEMO_MAX_OUTPUT_TOKENS = _get_int(
        'AGENT_CONTEXT_MEMO_MAX_OUTPUT_TOKENS',
        int(_CONTEXT_DEFAULTS.get('memo_max_output_tokens', 2048)))
    # L3 防抖动：可压缩消息少于此数时不重复调模型（超过模型窗口强制压缩）
    CONTEXT_MEMO_MIN_CANDIDATES = _get_int(
        'AGENT_CONTEXT_MEMO_MIN_CANDIDATES',
        int(_CONTEXT_DEFAULTS.get('memo_min_candidates', 6)))
    # 调试模式：context_compacted 事件附带被裁消息 ID 与备忘，供回放（§8.5）
    CONTEXT_DEBUG = _get_bool(
        'AGENT_CONTEXT_DEBUG', bool(_CONTEXT_DEFAULTS.get('debug', False)))
    # 区段占比（§8.3，合计 1.0）：每项可用环境变量单独覆盖
    _CONTEXT_RATIO_DEFAULTS = _CONTEXT_DEFAULTS.get('section_ratios') or {}
    CONTEXT_RATIO_SYSTEM = _get_float(
        'AGENT_CONTEXT_RATIO_SYSTEM',
        float(_CONTEXT_RATIO_DEFAULTS.get('system', 0.15)))
    CONTEXT_RATIO_SCRATCHPAD = _get_float(
        'AGENT_CONTEXT_RATIO_SCRATCHPAD',
        float(_CONTEXT_RATIO_DEFAULTS.get('scratchpad', 0.10)))
    CONTEXT_RATIO_DIALOGUE = _get_float(
        'AGENT_CONTEXT_RATIO_DIALOGUE',
        float(_CONTEXT_RATIO_DEFAULTS.get('dialogue', 0.35)))
    CONTEXT_RATIO_TOOL_RESULTS = _get_float(
        'AGENT_CONTEXT_RATIO_TOOL_RESULTS',
        float(_CONTEXT_RATIO_DEFAULTS.get('tool_results', 0.30)))
    CONTEXT_RATIO_RESERVE = _get_float(
        'AGENT_CONTEXT_RATIO_RESERVE',
        float(_CONTEXT_RATIO_DEFAULTS.get('reserve', 0.10)))
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

    # ===== 工具层（INT-2453）=====
    # 意图工具 → 网关 REST 的基址：容器内用 http://api_gateway:5000，
    # 本机 docker 栈用宿主映射端口；默认取网关 HTTP 端口。
    TOOL_GATEWAY_BASE_URL = os.environ.get(
        'AGENT_TOOL_GATEWAY_BASE_URL',
        f'http://127.0.0.1:{API_GATEWAY_PORT}')
    TOOL_HTTP_TIMEOUT_SECONDS = _get_float('AGENT_TOOL_HTTP_TIMEOUT_SECONDS', 30.0)
    # run 级 Authorization 暂存 TTL（只在 run 执行窗口内需要，不落库）
    TOOL_CREDENTIAL_TTL_SECONDS = _get_int(
        'AGENT_TOOL_CREDENTIAL_TTL_SECONDS', 3600)

    # ===== 重启恢复（§9.2）=====
    RECOVERY_ON_STARTUP = _get_bool('AGENT_RECOVERY_ON_STARTUP', True)

    # ===== T1 沙箱接线（INT-2495；执行器参数仍由 AGENT_SANDBOX_* 单一读取）=====
    # runner_http = 生产（只向 runner/sidecar 发 HTTP，不持有 docker.sock）；
    # host_cli = 开发机 / 宿主 runner 进程内执行。
    SANDBOX_EXECUTOR_MODE = os.environ.get(
        'AGENT_SANDBOX_EXECUTOR_MODE', 'runner_http').strip().lower()
    SANDBOX_RUNNER_URL = (os.environ.get('AGENT_SANDBOX_RUNNER_URL') or '').strip()
    SANDBOX_RUNNER_TOKEN = (
        os.environ.get('AGENT_SANDBOX_RUNNER_TOKEN') or '').strip()
    SANDBOX_DOCKER_BIN = os.environ.get(
        'AGENT_SANDBOX_DOCKER_BIN', 'docker').strip() or 'docker'
    # /work 临时目录根（空 = 系统临时目录）；容器内需挂载到该路径。
    SANDBOX_WORK_ROOT = (os.environ.get('AGENT_SANDBOX_WORK_ROOT') or '').strip()
    # 回灌模型的 stdout / stderr 摘要上限（字符）；原始输出仍由执行器按
    # output_limit_bytes（默认 1MB）截断。
    SANDBOX_OUTPUT_SUMMARY_CHARS = _get_int(
        'AGENT_SANDBOX_OUTPUT_SUMMARY_CHARS', 2000)

    # ===== Skill（§4；顶层只读目录由部署挂载，INT-2456）=====
    SKILLS_ROOT = os.environ.get(
        'AGENT_SKILLS_ROOT', os.path.join(_PROJECT_DIR, 'skills'))
    # 长期记忆文件树（§8.6）；部署为写卷，按 tenant/owner 隔离。
    MEMORY_ROOT = os.environ.get(
        'AGENT_MEMORY_ROOT', os.path.join(_PROJECT_DIR, 'memory'))
    # 本目录（含 model_catalog.json / agent_defaults.json），部署为只读挂载。
    CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
    # T2 可信运行时（§7 拍板#2）：runsc（gVisor）或 firecracker。
    # 缺失时 T2 请求报 T2_RUNTIME_UNAVAILABLE，不得静默降级 T1。
    T2_RUNTIME = os.environ.get('AGENT_T2_RUNTIME', 'runsc').strip() or 'runsc'
    SKILL_BODY_MAX_LINES = _get_int(
        'AGENT_SKILL_BODY_MAX_LINES', int(_SKILL_DEFAULTS.get('body_max_lines', 500)))
    # True：任何校验问题都让启动失败；False：ERROR 剔除该 Skill、WARNING 仅告警
    SKILL_VALIDATION_STRICT = _get_bool(
        'AGENT_SKILL_VALIDATION_STRICT',
        bool(_SKILL_DEFAULTS.get('validation_strict', False)))
    # L1 常驻预算 = 模型窗口 × system 区段占比（§8.3：15%）
    CONTEXT_WINDOW_TOKENS = _get_int(
        'AGENT_CONTEXT_WINDOW_TOKENS',
        int(_SKILL_DEFAULTS.get('context_window_tokens', 128000)))
    SYSTEM_SECTION_RATIO = _get_float(
        'AGENT_SYSTEM_SECTION_RATIO',
        float(_SKILL_DEFAULTS.get('system_section_ratio', 0.15)))

    @classmethod
    def skill_l1_budget_tokens(cls) -> int:
        return int(cls.CONTEXT_WINDOW_TOKENS * cls.SYSTEM_SECTION_RATIO)

    @classmethod
    def model_catalog_path(cls) -> str:
        """模型目录的实际路径（空配置 = config/model_catalog.json）。"""
        return cls.MODEL_CATALOG_PATH or os.path.join(
            cls.CONFIG_DIR, 'model_catalog.json')

    @classmethod
    def validate_mounts(cls) -> None:
        """启动前校验三个部署挂载点（方案 07 拍板#3，INT-2456）。

        - ``skills/`` 只读：缺失即启动失败（空目录会被解读成「没有 Skill」，
          属于静默故障）；
        - ``memory/`` 写卷：缺失或不可写即启动失败（长期记忆写丢不能等到运行期
          才发现）；
        - ``agent_service/config/``：模型目录文件必须存在（窗口/输出上限的唯一
          事实源）。

        只在真实进程启动路径（自建组合根）调用；测试注入组合根不校验，避免把
        宿主机目录布局带进单测。
        """
        problems = []
        skills = Path(cls.SKILLS_ROOT)
        if not skills.is_dir():
            problems.append(f'skills 目录不存在：{skills}（应只读挂载 ../skills）')
        elif not os.access(str(skills), os.R_OK):
            problems.append(f'skills 目录不可读：{skills}')
        catalog = Path(cls.model_catalog_path())
        if not catalog.is_file():
            problems.append(f'模型目录文件不存在：{catalog}')
        memory = Path(cls.MEMORY_ROOT)
        if not memory.is_dir():
            problems.append(
                f'memory 目录不存在：{memory}（应挂载可写卷，见 compose agent_memory）')
        else:
            probe = memory / '.write_probe'
            try:
                probe.write_text('ok', encoding='utf-8')
                probe.unlink()
            except OSError as exc:
                problems.append(f'memory 目录不可写：{memory}（{exc}）')
        if problems:
            raise RuntimeError(
                'agent_service 部署挂载校验失败：' + '；'.join(problems))

    @classmethod
    def context_section_ratios(cls) -> dict:
        """§8.3 区段占比（ContextBudgetPolicy 的唯一配置来源）。"""
        return {
            'system': cls.CONTEXT_RATIO_SYSTEM,
            'scratchpad': cls.CONTEXT_RATIO_SCRATCHPAD,
            'dialogue': cls.CONTEXT_RATIO_DIALOGUE,
            'tool_results': cls.CONTEXT_RATIO_TOOL_RESULTS,
            'reserve': cls.CONTEXT_RATIO_RESERVE,
        }

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
        if cls.SANDBOX_OUTPUT_SUMMARY_CHARS < 0:
            raise ValueError('AGENT_SANDBOX_OUTPUT_SUMMARY_CHARS 不能为负数')
        ratios = cls.context_section_ratios()
        if any(value < 0 for value in ratios.values()) \
                or abs(sum(ratios.values()) - 1.0) > 1e-6:
            raise ValueError(
                'AGENT_CONTEXT_RATIO_* 区段占比必须非负且合计为 1.0')
