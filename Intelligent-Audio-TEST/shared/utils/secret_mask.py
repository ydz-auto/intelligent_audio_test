# -*- coding: utf-8 -*-
"""敏感信息统一脱敏工具（INT-70，API测试功能设计文档 §8.1）。

密钥与敏感头不出现在任何日志/事件 payload：log_handler 在 emit 与
log_and_emit 入口统一调用 mask_text；结构化 payload 可用 mask_mapping
递归脱敏。脱敏后键名原样保留、值全掩码（零明文），便于按键名排查问题。
"""
import re
from typing import Any

_MASK = '****'

# 敏感键名交替式（大小写不敏感；-/_ 分隔等价；token/password 等
# 复合词已含词边界，纯数字值视为用量统计不脱敏）
_KEY_ALTERNATION = (
    r'api[-_]?key'
    r'|apikey'
    r'|access[-_]?key'
    r'|app[-_]?key'
    r'|secret(?:[-_]?(?:key|number))?'
    r'|api[-_]?secret'
    r'|client[-_]?secret'
    r'|authorization'
    r'|proxy[-_]?authorization'
    r'|auth[-_]?token'
    r'|access[-_]?token'
    r'|refresh[-_]?token'
    r'|id[-_]?token'
    r'|session[-_]?key'
    r'|private[-_]?key'
    r'|x[-_]api[-_]?key'
    r'|token'
    r'|password'
    r'|passwd'
    r'|pwd'
    r'|cookie'
)

# 键值对形态：JSON（"key": "value"）、kv（key=value）、key: value；
# Bearer <token> 整体作为 authorization 的值一并掩码
_KV_PATTERN = re.compile(
    r'(?i)(?P<key>["\']?\b(?:' + _KEY_ALTERNATION + r')\b["\']?)'
    r'(?P<sep>\s*[:=]\s*)'
    r'(?P<value>'
    r'"(?P<dq>(?:[^"\\]|\\.)*)"'
    r"|'(?P<sq>[^']*)'"
    r'|(?:[Bb]earer\s+\S+'
    r'|[^\s,;&\'"\\]+)'
    r')'
)

# 游离 Bearer token（无键名上下文）
_BEARER_PATTERN = re.compile(r'(?i)\b(bearer\s+)([A-Za-z0-9._~+/=-]{8,})')

# OpenAI 风格裸密钥（sk- 前缀长 token，直接粘贴进文本的场景）
_OPENAI_KEY_PATTERN = re.compile(r'\b(sk-[A-Za-z0-9_-]{16,})\b')


def mask_value(value) -> str:
    """单值全掩码（零明文：不保留任何前后缀片段）。"""
    if value is None or value == '':
        return ''
    return _MASK


def _mask_kv(match: 're.Match') -> str:
    value = match.group('value')
    if match.group('dq') is not None:
        inner = match.group('dq')
        masked = '' if inner.isdigit() else mask_value(inner)
        return '%s%s"%s"' % (match.group('key'), match.group('sep'), masked)
    if match.group('sq') is not None:
        inner = match.group('sq')
        masked = '' if inner.isdigit() else mask_value(inner)
        return "%s%s'%s'" % (match.group('key'), match.group('sep'), masked)
    if value.isdigit():
        return match.group(0)
    return '%s%s%s' % (match.group('key'), match.group('sep'), mask_value(value))


def mask_text(text: Any) -> Any:
    """自由文本脱敏：掩码键值对、Bearer token 与裸 sk- 密钥。

    非字符串原样返回；空串/None 原样返回。幂等（已掩码文本不再匹配）。
    """
    if not isinstance(text, str) or not text:
        return text
    text = _KV_PATTERN.sub(_mask_kv, text)
    text = _BEARER_PATTERN.sub(
        lambda m: '%s%s' % (m.group(1), _MASK), text)
    text = _OPENAI_KEY_PATTERN.sub(_MASK, text)
    return text


def mask_mapping(obj: Any) -> Any:
    """结构化 payload 递归脱敏：dict 键名命中敏感键 → 值全掩码。

    dict/list 原地语义之外不修改入参（返回新结构），其余类型原样返回。
    """
    if isinstance(obj, dict):
        masked = {}
        for key, value in obj.items():
            if isinstance(key, str) and _is_sensitive_key(key):
                masked[key] = _MASK if value else value
            else:
                masked[key] = mask_mapping(value)
        return masked
    if isinstance(obj, (list, tuple)):
        masked = [mask_mapping(item) for item in obj]
        return masked if isinstance(obj, list) else type(obj)(masked)
    return obj


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().strip('"\'').lower().replace('-', '_')
    if normalized in {
        'api_key', 'apikey', 'access_key', 'app_key', 'appkey',
        'secret', 'secret_key', 'api_secret', 'client_secret',
        'authorization', 'proxy_authorization', 'auth_token',
        'access_token', 'refresh_token', 'id_token',
        'session_key', 'private_key', 'x_api_key',
        'token', 'password', 'passwd', 'pwd', 'cookie',
    }:
        return True
    return normalized.endswith('_api_key') or normalized.endswith('_secret_key')
