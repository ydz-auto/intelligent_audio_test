# -*- coding: utf-8 -*-
"""被测 API 网络代理工具（INT-839）— apis.proxy_type / proxy_url → 传输层参数。

数据模型（apis 表两列，INT-839 契约）：
- proxy_type：http / https / socks5 / socks5h；NULL 或空 = 不用代理
- proxy_url：`[user:pass@]host:port`，不含 scheme；配置代理时认证段必填

本模块提供三类转换，执行链路（api_client / realtime_ws_client / 健康检查）
与 vendor_config 契约共用：
- build_proxy_url          拼完整代理 URL `{proxy_type}://{proxy_url}`（requests / #2 契约）
- split_proxy_url          `[user:pass@]host:port` → (host, port, user, password)
- websocket_proxy_kwargs   websocket-client 代理参数
  （http_proxy_host / http_proxy_port / http_proxy_auth / proxy_type）
- validate_proxy           CRUD 校验口径（后端侧唯一落位）
"""
from urllib.parse import urlparse, unquote
from typing import Optional, Tuple

# 合法代理类型（socks4 不在范围，INT-839 不做）
PROXY_TYPES = ('http', 'https', 'socks5', 'socks5h')

# websocket-client proxy_type 映射：https 代理端点默认走 http CONNECT 隧道语义
# （websocket-client 1.9.2 proxy_info 支持 http/socks4/socks4a/socks5/socks5h）
_WS_PROXY_TYPE_MAP = {
    'http': 'http',
    'https': 'http',
    'socks5': 'socks5',
    'socks5h': 'socks5h',
}

# proxy_url 未显式带端口时的缺省端口（按代理类型）
_DEFAULT_PORTS = {
    'http': 80,
    'https': 443,
    'socks5': 1080,
    'socks5h': 1080,
}


def build_proxy_url(proxy_type: Optional[str],
                    proxy_url: Optional[str]) -> Optional[str]:
    """拼完整代理 URL `{proxy_type}://{proxy_url}`；任一为空返回 None。

    requests.proxies / vendor_config 契约（#2 adapter 侧拼 URL）共用。
    防御：proxy_url 误带 `scheme://` 前缀时剥去（规范不含 scheme），
    避免拼出双重 scheme（INT-846 审计 P2 修复）。
    """
    proxy_type = (proxy_type or '').strip()
    proxy_url = (proxy_url or '').strip()
    if not proxy_type or not proxy_url:
        return None
    if '://' in proxy_url:
        proxy_url = proxy_url.split('://', 1)[1]
    return f'{proxy_type}://{proxy_url}'


def split_proxy_url(proxy_url: Optional[str]) -> Tuple[
        Optional[str], Optional[int], Optional[str], Optional[str]]:
    """分解 `[user:pass@]host:port` → (host, port, user, password)。

    - host 必填；port 缺省 None（调用方按代理类型补缺省端口）
    - user / password 经 URL unquote（`%40` → `@` 等）；未配置为 None
    - 容错：proxy_url 误带 `scheme://` 前缀时剥去（规范不含 scheme）
    """
    raw = (proxy_url or '').strip()
    if not raw:
        return None, None, None, None
    # 剥 scheme 前缀（防御：规范要求不含 scheme，带则忽略）
    if '://' in raw:
        raw = raw.split('://', 1)[1]
    parsed = urlparse('//' + raw)
    host = parsed.hostname or None
    port = parsed.port  # urlparse 已校验非法端口抛 ValueError
    user = unquote(parsed.username) if parsed.username else None
    password = unquote(parsed.password) if parsed.password else None
    return host, port, user, password


def websocket_proxy_kwargs(proxy_type: Optional[str],
                           proxy_url: Optional[str]) -> dict:
    """websocket-client 代理参数分解：返回 kwargs dict（无代理时为空 dict）。

    `_call_websocket` 与 `realtime_ws_client.connect()` 同套参数：
    http_proxy_host / http_proxy_port / http_proxy_auth=(user, pass) /
    proxy_type（http→http，https→http CONNECT 隧道，socks5→socks5，socks5h→socks5h）。
    """
    if not proxy_type or not proxy_url:
        return {}
    host, port, user, password = split_proxy_url(proxy_url)
    if not host:
        return {}
    kwargs = {
        'http_proxy_host': host,
        'http_proxy_port': port if port is not None
        else _DEFAULT_PORTS.get((proxy_type or '').strip(), 80),
        'proxy_type': _WS_PROXY_TYPE_MAP.get(
            (proxy_type or '').strip(), 'http'),
    }
    if user and password is not None:
        kwargs['http_proxy_auth'] = (user, password)
    return kwargs


def validate_proxy(proxy_type: Optional[str],
                   proxy_url: Optional[str]) -> Optional[str]:
    """CRUD 校验：返回错误信息字符串；合法返回 None。

    口径（INT-839 契约）：
    - proxy_type 为空 → proxy_url 必须为空
    - proxy_type 非空 → 必须是 http/https/socks5/socks5h，
      proxy_url 必填且带 `user:pass@` 认证段
    """
    proxy_type = (proxy_type or '').strip() or None
    proxy_url = (proxy_url or '').strip() or None

    if proxy_type is None:
        if proxy_url:
            return 'proxy_type 为空时 proxy_url 必须为空'
        return None

    if proxy_type not in PROXY_TYPES:
        return (f'非法的代理类型 (proxy_type): {proxy_type}，'
                f'仅支持: {", ".join(PROXY_TYPES)}')

    if not proxy_url:
        return '配置代理时 proxy_url 必填（格式: user:pass@host:port）'

    if '://' in proxy_url:
        # INT-846 审计 P2：契约规定 proxy_url 不含 scheme，带 scheme 前缀
        # 会在执行侧拼出双重 scheme、脱敏失效 → 源头拒绝入库
        return ('无效的代理地址 (proxy_url): 不应包含 scheme 前缀 '
                '（去掉 http:// 等），格式: user:pass@host:port')

    try:
        host, port, user, password = split_proxy_url(proxy_url)
    except ValueError:
        return ('无效的代理地址 (proxy_url): 端口必须为数字，'
                '格式: user:pass@host:port')
    if not host:
        return '无效的代理地址 (proxy_url)，必须为 user:pass@host:port 格式'
    if not user or not password:
        return '代理地址 (proxy_url) 必须带 user:pass@ 认证段'
    return None
