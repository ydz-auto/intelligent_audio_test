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

# proxy_url 值内 user:pass@ 段掩码（INT-839）：保留 host:port，掩码认证段。
# 形如 "proxy_url": "user:pass@host:8080" / proxy_url=user:pass@host:8080 /
# proxy_url: user:pass@host:8080 —— 复用 authorization/proxy_authorization
# 的 KV 掩码思路，但只掩 user:pass 前缀，host:port 保留便于排查。
# 两点边界（INT-846 审计 P2/P3）：
# - 容错误带 scheme 前缀（http:// 等），仍掩 userinfo（scheme 保留可见）；
# - userinfo 按末个 @ 切分（执行侧 split_proxy_url 亦按 urlparse 末个 @
#   解析），密码含字面 @ 时不再只掩到首个 @ 而泄露后续段。
_PROXY_USERINFO_PATTERN = re.compile(
    r'(?i)(?P<prefix>proxy[-_]?url["\']?\s*[:=]\s*["\']?)'
    r'(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*://)?'
    r'(?P<userinfo>[^\r\n]*)@'
    r'(?P<hostport>[^\s@/;,"\'\\:]+(?::[0-9]{1,5})?)'
)


def _mask_proxy_userinfo(match: 're.Match') -> str:
    return '%s%s****@%s' % (
        match.group('prefix'),
        match.group('scheme') or '',
        match.group('hostport'),
    )


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
    text = _PROXY_USERINFO_PATTERN.sub(_mask_proxy_userinfo, text)
    text = _KV_PATTERN.sub(_mask_kv, text)
    text = _BEARER_PATTERN.sub(
        lambda m: '%s%s' % (m.group(1), _MASK), text)
    text = _OPENAI_KEY_PATTERN.sub(_MASK, text)
    return text


def mask_mapping(obj: Any) -> Any:
    """结构化 payload 递归脱敏：dict 键名命中敏感键 → 值全掩码。

    proxy_url 键（INT-839）例外：仅掩码值内 user:pass 认证段，保留 host:port
    （与 mask_text 的 _PROXY_USERINFO_PATTERN 口径一致）。dict/list 原地
    语义之外不修改入参（返回新结构），其余类型原样返回。
    """
    if isinstance(obj, dict):
        masked = {}
        for key, value in obj.items():
            if isinstance(key, str) and _is_sensitive_key(key):
                masked[key] = _MASK if value else value
            elif isinstance(key, str) and _is_proxy_url_key(key):
                masked[key] = _mask_proxy_url_value(value)
            else:
                masked[key] = mask_mapping(value)
        return masked
    if isinstance(obj, (list, tuple)):
        masked = [mask_mapping(item) for item in obj]
        return masked if isinstance(obj, list) else type(obj)(masked)
    return obj


def _is_proxy_url_key(key: str) -> bool:
    return key.strip().strip('"\'').lower().replace('-', '_') == 'proxy_url'


def _mask_proxy_url_value(value: Any) -> Any:
    """掩码 proxy_url 值内 user:pass 段，保留 host:port；非字符串递归脱敏。

    INT-846 审计 P2/P3：剥 scheme 前缀（scheme 保留可见）、按末个 @ 切分，
    与执行侧 split_proxy_url（urlparse 末个 @）口径一致。
    """
    if not isinstance(value, str):
        return mask_mapping(value)
    scheme = ''
    rest = value
    # 仅剥合法 scheme 前缀（[scheme]://，scheme 为字母开头）；密码含 `://`
    # 字面时不误判为 scheme
    if re.match(r'[A-Za-z][A-Za-z0-9+.-]*://', rest):
        scheme, _, rest = rest.partition('://')
        scheme = scheme + '://'
    head, sep, tail = rest.rpartition('@')
    if not sep:
        return value
    return '%s****@%s' % (scheme, tail)


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
