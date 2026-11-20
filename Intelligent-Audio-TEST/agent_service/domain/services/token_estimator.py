# -*- coding: utf-8 -*-
"""Token 估算（落地方案 §8.3 预算模型的轻量近似）。

仓库未引入 tokenizer 依赖：这里按字符类别估算，偏保守（宁可高估）：
- CJK 及非 ASCII 字符：1 字符 ≈ 1 token；
- ASCII：4 字符 ≈ 1 token（向上取整）。

用途仅限「Skill L1 常驻是否吃掉 system 区段预算」这类量级判断；
真实计费以模型返回的 usage 为准（orchestrator 已按 usage 落库）。
m0-04 落地压缩预算模型后，如引入正式 tokenizer，应在此单点替换。
"""
from typing import Any, Iterable, Optional

_ASCII_CHARS_PER_TOKEN = 4
# 每条消息的角色 / 分隔符开销（OpenAI 兼容口径的经验值，仅用于预算量级判断）
MESSAGE_OVERHEAD_TOKENS = 4


def estimate_tokens(text: Optional[str]) -> int:
    """估算一段文本的 token 数。"""
    if not text:
        return 0
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    wide_chars = len(text) - ascii_chars
    return wide_chars + (ascii_chars + _ASCII_CHARS_PER_TOKEN - 1) // _ASCII_CHARS_PER_TOKEN


def estimate_tokens_of(blocks: Iterable[Optional[str]]) -> int:
    """估算多段文本（按行拼接后的）token 数。"""
    return estimate_tokens('\n'.join(b for b in blocks if b))


def estimate_message_tokens(content: Optional[str],
                            tool_payload: Optional[Any] = None) -> int:
    """估算一条模型消息的 token 数（正文 + 工具调用结构 + 角色开销）。"""
    total = MESSAGE_OVERHEAD_TOKENS + estimate_tokens(content)
    if tool_payload:
        import json
        total += estimate_tokens(json.dumps(
            tool_payload, ensure_ascii=False, default=str))
    return total


__all__ = [
    'MESSAGE_OVERHEAD_TOKENS', 'estimate_message_tokens', 'estimate_tokens',
    'estimate_tokens_of',
]
