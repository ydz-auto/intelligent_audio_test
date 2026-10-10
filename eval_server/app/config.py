# -*- coding: utf-8 -*-
"""eval_server 配置加载。

结构配置（并发/品牌/LLM 默认等）在 config.yaml；
密钥与部署级覆盖在 .env（LLM_JUDGE_API_KEY / LOG_DIR / STATIC_BASE_PATH 等）。
加载顺序：config.yaml 提供默认值 → .env 覆盖。
最终以 config 单例暴露，全项目统一用 config.XXX 访问。
"""
import os
from pathlib import Path

import yaml

# ── 1) 加载 .env（密钥 + 部署级覆盖） ──
_env_path = Path(__file__).resolve().parent.parent / '.env'
if _env_path.exists():
    with open(_env_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

# ── 2) 加载 config.yaml（结构配置） ──
_yaml_path = Path(__file__).resolve().parent.parent / 'config.yaml'
with open(_yaml_path, encoding='utf-8') as f:
    _yaml = yaml.safe_load(f) or {}

_lj = dict(_yaml.get('llm_judge') or {})


def _env(name: str, default: str = '') -> str:
    """.env 覆盖 yaml 默认值；未设置时返回 default。"""
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    return int(v) if v is not None else default


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return v == '1' if v is not None else default


class Config:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    # 项目根目录（与 Intelligent-Audio-TEST 保持一致）
    PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..', '..'))

    # 静态资源根目录（与主项目共享，静态资源已迁至 D:\00_static\static）
    STATIC_BASE_PATH = _env('STATIC_BASE_PATH', _yaml.get('static_base_path', r'D:\00_static\static'))

    # 文件存储路径（存放到 static 目录下，便于统一访问与归档）
    DATA_DIR = os.path.join(STATIC_BASE_PATH, 'eval_server')
    TASKS_DIR = os.path.join(DATA_DIR, 'tasks')          # 按日分文件夹
    ENDPOINTS_FILE = os.path.join(DATA_DIR, 'endpoints.json')

    # LLM 调用审计日志（每次 call_llm 一条 JSONL；与 LOG_DIR 完全分开，永不轮转）
    LLM_CALL_LOG_DIR = os.path.join(DATA_DIR, 'llm_call_logs')
    LLM_CALL_LOG_ENABLED = _env_bool('LLM_CALL_LOG_ENABLED', bool(_yaml.get('llm_call_log_enabled', True)))

    # 上传文件临时目录
    UPLOAD_DIR = os.path.join(DATA_DIR, 'uploads')

    # OSS/MinIO 配置（可选能力）
    _oss = _yaml.get('oss') or {}
    OSS_ENDPOINT = _env('OSS_ENDPOINT', _oss.get('endpoint', ''))
    OSS_ACCESS_KEY = _env('OSS_ACCESS_KEY', _oss.get('access_key', ''))
    OSS_SECRET_KEY = _env('OSS_SECRET_KEY', _oss.get('secret_key', ''))
    OSS_BUCKET_NAME = _env('OSS_BUCKET_NAME', _oss.get('bucket_name', ''))
    OSS_KEY_PREFIX = _env('OSS_KEY_PREFIX', _oss.get('key_prefix', ''))
    OSS_REGION = _env('OSS_REGION', _oss.get('region', 'us-east-1'))

    # 日志配置（归档到 static 目录下；.env LOG_DIR 可覆盖）
    LOG_DIR = _env('LOG_DIR', os.path.join(STATIC_BASE_PATH, 'logs', 'eval_server'))
    LOG_FILE = os.path.join(LOG_DIR, 'eval_server.log')
    LOG_MAX_BYTES = _env_int('LOG_MAX_BYTES', int(_yaml.get('log_max_bytes', 10 * 1024 * 1024)))
    LOG_BACKUP_COUNT = _env_int('LOG_BACKUP_COUNT', int(_yaml.get('log_backup_count', 30)))

    # Flask settings
    DEBUG = bool(_yaml.get('debug', False))
    PORT = int(_yaml.get('port', 8888))
    HOST = _yaml.get('host', '0.0.0.0')

    # Local concurrency control
    LOCAL_MAX_CONCURRENCY = _env_int('LOCAL_MAX_CONCURRENCY', int(_yaml.get('local_max_concurrency', 100)))

    # WSGI 服务器线程数（None = 自动计算 LOCAL_MAX_CONCURRENCY * 2 + 4，上限 64）
    _wsgi = _yaml.get('wsgi_threads')
    WSGI_THREADS = _env_int('WSGI_THREADS', int(_wsgi)) if _wsgi is not None else None

    # 各维度并发上限（env_judge/reject_judge 传音频给 LLM 限 5；其余放开到 100）
    CONCURRENCY_LIMITS = dict(_yaml.get('concurrency_limits') or {})
    DEFAULT_MAX_CONCURRENCY = int(_yaml.get('default_max_concurrency', 100))

    # LLM 调用共享并发（按「中转站 × 品牌」两级分池）
    LLM_TEXT_MAX_CONCURRENCY = _env_int('LLM_TEXT_MAX_CONCURRENCY', int(_yaml.get('llm_text_max_concurrency', 100)))
    LLM_AUDIO_MAX_CONCURRENCY = _env_int('LLM_AUDIO_MAX_CONCURRENCY', int(_yaml.get('llm_audio_max_concurrency', 5)))

    # 模型品牌识别规则（模型名小写 substring 匹配）
    LLM_BRAND_KEYWORDS = {k: list(v) for k, v in (_yaml.get('llm_brand_keywords') or {}).items()}

    # LLM Judge 配置（OpenAI 兼容代理）；api_key 等密钥由 .env 覆盖，不进 config.yaml
    LLM_JUDGE = {
        'api_key': _env('LLM_JUDGE_API_KEY', _lj.get('api_key', '')),
        'api_base_url': _env('LLM_JUDGE_API_BASE', _lj.get('api_base_url', 'https://az.gptplus5.com/v1')),
        'default_model': _env('LLM_JUDGE_DEFAULT_MODEL', _lj.get('default_model', 'gpt-4o-mini')),
        'dimension_models': {
            dim: _env(f'LLM_JUDGE_MODEL_{dim.upper()}', (_lj.get('dimension_models') or {}).get(dim, ''))
            for dim in ('llm_judge', 'high_freq_llm_judge', 'false_takeover', 'reply_quality')
        },
        'max_tokens': _env_int('LLM_JUDGE_MAX_TOKENS', int(_lj.get('max_tokens', 4096))),
        'temperature': float(_env('LLM_JUDGE_TEMPERATURE', str(_lj.get('temperature', 0.1)))),
        'timeout': _env_int('LLM_JUDGE_TIMEOUT', int(_lj.get('timeout', 120))),
        'prompt_template': _lj.get('prompt_template', ''),
    }


config = Config()
