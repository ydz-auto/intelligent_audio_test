# -*- coding: utf-8 -*-
"""上游错误响应体脱敏（§6.4-5 / §10 密钥不出域）。

上游（尤其用户自建的 OpenAI 兼容网关）可能在错误响应里回显认证信息。
``run.error`` / error 事件 / 审计会带上错误正文，因此写库前先剥掉形如
``Bearer <token>``、``sk-...``、``"api_key": "..."`` 的片段再截断。

只做「抹掉敏感串」这一件事，不改变状态码与错误码，便于前端按码引导。
"""
import re
from typing import Pattern, Sequence, Tuple

DEFAULT_LIMIT = 500
MASK = '***'

_PATTERNS: Sequence[Tuple[Pattern, str]] = (
    # Authorization: Bearer <token> / 裸 Bearer <token>
    (re.compile(r'(?i)\b(bearer)\s+[A-Za-z0-9._\-+/=]{6,}'), r'\1 ' + MASK),
    # "api_key": "sk-..." / x-api-key: ... / access_token=...
    (re.compile(
        r'(?i)(["\']?\b(?:api[_-]?key|authorization|x-api-key'
        r'|access[_-]?token|secret[_-]?key|token|secret)\b["\']?'
        r'\s*[:=]\s*["\']?)[^\s"\',;}]{6,}'), r'\1' + MASK),
    # 裸 Key（sk- / sk-ant- 前缀，至少 8 位，避免误伤普通单词）
    (re.compile(r'\bsk-(?:ant-)?[A-Za-z0-9_\-*]{8,}'), 'sk-' + MASK),
)


def sanitize_upstream_body(body: str, *, limit: int = DEFAULT_LIMIT) -> str:
    """返回脱敏并截断后的错误正文（不抛异常，入参可为 None）。"""
    text = str(body or '')
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    if limit > 0:
        text = text[:limit]
    return text


__all__ = ['DEFAULT_LIMIT', 'MASK', 'sanitize_upstream_body']
