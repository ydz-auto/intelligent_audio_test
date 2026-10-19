# -*- coding: utf-8 -*-
"""代理配置工具（INT-839 #2）。

api_adapter_service 收到 vendor_config 中的 proxy_type / proxy_url 后，
adapter 侧拼完整代理 URL ``{proxy_type}://{proxy_url}`` 下发各协议栈
（requests.proxies / websockets.connect(proxy=...)）。任一字段缺失或为空
表示不用代理，返回 None（与现状行为一致）。
"""
import re

# 受支持代理 scheme 白名单（requests 与 websockets 均支持；socks4 按
# INT-839 范围不做）。非白名单 scheme（如 ftp / htttp）不把完整 URL 交给
# 底层库——websockets 的 InvalidProxy 异常消息会原样带出明文 user:pass。
SUPPORTED_PROXY_SCHEMES = ('http', 'https', 'socks5', 'socks5h')

# URL 的 userinfo 段（scheme://user:pass@host → scheme://****@host）
_URL_USERINFO_RE = re.compile(r'(?i)(\b[a-z][a-z0-9+.-]*://)[^/@\s]+@')


def build_proxy_url(proxy_type, proxy_url):
    """拼完整代理 URL；proxy_type / proxy_url 任一缺失或为空返回 None。"""
    if not proxy_type or not proxy_url:
        return None
    return f'{proxy_type}://{proxy_url}'


def is_supported_proxy_scheme(proxy_url):
    """完整代理 URL 的 scheme 是否在受支持白名单内。

    非白名单 scheme 时，requests / websockets 抛出的异常消息可能带出
    完整 URL（含明文 user:pass），因此应在调用底层库前拦截。
    """
    if not proxy_url or '://' not in proxy_url:
        return False
    scheme = proxy_url.split('://', 1)[0].strip().lower()
    return scheme in SUPPORTED_PROXY_SCHEMES


def mask_proxy_userinfo(text):
    """掩码文本中 URL 的 userinfo 段：scheme://user:pass@ → scheme://****@。

    覆盖 websockets InvalidProxy 等异常消息把完整代理 URL 原样带出、进而
    泄漏明文 user:pass 的场景；幂等（已掩码文本不再变化），非 URL 原样返回。
    """
    if not isinstance(text, str) or not text:
        return text
    return _URL_USERINFO_RE.sub(r'\1****@', text)


def masked_exc_info(exc):
    """构造日志 exc_info 元组：保留原异常类型与调用链，异常消息脱敏。

    ``logger.error(..., exc_info=True)`` 时 traceback 末行打印异常原始
    消息，websockets InvalidProxy 会泄漏明文 user:pass。此函数以同类型
    异常副本承载脱敏消息，traceback 帧保持原样。
    """
    safe = mask_proxy_userinfo(str(exc))
    try:
        value = type(exc)(safe)
    except Exception:
        value = RuntimeError(safe)
    return (type(exc), value, getattr(exc, '__traceback__', None))
