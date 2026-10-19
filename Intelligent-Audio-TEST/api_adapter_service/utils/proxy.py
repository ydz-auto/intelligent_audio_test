# -*- coding: utf-8 -*-
"""代理配置工具（INT-839 #2）。

api_adapter_service 收到 vendor_config 中的 proxy_type / proxy_url 后，
adapter 侧拼完整代理 URL ``{proxy_type}://{proxy_url}`` 下发各协议栈
（requests.proxies / websockets.connect(proxy=...)）。任一字段缺失或为空
表示不用代理，返回 None（与现状行为一致）。
"""


def build_proxy_url(proxy_type, proxy_url):
    """拼完整代理 URL；proxy_type / proxy_url 任一缺失或为空返回 None。"""
    if not proxy_type or not proxy_url:
        return None
    return f'{proxy_type}://{proxy_url}'
