# -*- coding: utf-8 -*-
"""Agent 专用 REST 目标构造器（INT-2459 引入，INT-2467 泛化为读写共用）。

有些内部 Agent 能力在网关有真实路由、但没有登记进外部 MCP 1:1 清单
（``mcp_registry`` 冻结在 207 项，§6.2）。这类端点以「Agent 专用 REST 目标」
声明：字段形状与 MCP 注册项一致（``name`` / ``description`` / ``inputSchema``
/ ``permissions`` / ``method`` / ``path`` / ``path_params`` /
``query_params``），因此 ``mcp_registry.build_path`` / ``build_body`` 共享构造器
可直接消费，不需要第二套请求拼装。

本模块只负责「把一条声明变成 MCP 同形字典」，不做校验、不碰业务；
SPL 物理域 / 数字域的读写目标（``device_tools``）与设备写目标共用同一份。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

# 带请求体语义的方法：其余方法（GET/DELETE）未声明为查询参数的字段不进 body。
_WRITE_METHODS = ('POST', 'PUT', 'PATCH')


def rest_target(name: str, description: str, permissions: Sequence[str],
                method: str, path: str, *, path_params: Sequence[str] = (),
                query_params: Sequence[str] = (),
                schema: Optional[Dict[str, Any]] = None) -> dict:
    """构造一个 Agent 专用 REST 目标（与 MCP 注册项同形）。

    ``schema`` 是扁平参数表：``required=True`` 的字段会汇总成 ``required``；
    POST/PUT/PATCH 未列入 ``path_params`` / ``query_params`` 的字段按共享
    ``build_body`` 规则进入 JSON body，GET/DELETE 进入查询串。
    """
    properties = dict(schema or {})
    input_schema: Dict[str, Any] = {
        'type': 'object', 'properties': properties,
        'additionalProperties': True,
    }
    required = [key for key, value in properties.items()
                if isinstance(value, dict) and value.get('required')]
    if required:
        input_schema['required'] = required
    return {
        'name': name,
        'description': description,
        'inputSchema': input_schema,
        'permissions': list(permissions),
        'method': method.upper(),
        'path': path,
        'path_params': list(path_params),
        'query_params': list(query_params),
    }


def is_write_method(method: str) -> bool:
    """方法是否带请求体语义（写侧声明用）。"""
    return str(method or '').upper() in _WRITE_METHODS


__all__ = ['is_write_method', 'rest_target']
