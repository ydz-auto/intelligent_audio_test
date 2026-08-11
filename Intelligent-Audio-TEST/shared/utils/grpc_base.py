# -*- coding: utf-8 -*-
"""gRPC servicer 基类与装饰器

提供统一响应构建工厂和异常处理装饰器，消除各服务 servicers.py 中
90+ 个 RPC 方法重复的 try/except + _failure(str(e)) 模板，
以及 10 处 _success/_ok/_resp 响应构建函数重复。

使用方式::

    from shared.utils.grpc_base import grpc_rpc_handler, build_response

    class MyServicer(MyServiceServicer, LazyHandlerMixin):
        @grpc_rpc_handler
        def DoSomething(self, request, context=None):
            data = _loads(request.data, {})
            result = self.handler.handle(data)
            return build_response(MyResponse, data=result)

    # 或使用简写装饰器自动包装响应::

    @grpc_rpc_handler(response_cls=MyResponse)
    def DoSomething(self, request, context=None):
        ...
        return {"id": 1}  # 自动 build_response
"""
from __future__ import annotations

import functools
import logging
from typing import Any, Optional, Type

from shared.utils.grpc_json import dumps as _dumps, loads as _loads

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 响应构建工厂
# ------------------------------------------------------------------

def build_response(response_cls, success: bool = True, message: str = 'ok',
                   data: Any = None):
    """通用 gRPC 响应构建工厂。

    消除各服务 servicers.py 中 ``_success`` / ``_ok`` / ``_resp``
    / ``_failure`` 共 10 处重复定义。

    Args:
        response_cls: proto 生成的响应消息类（如 AlgorithmResponse）
        success: 是否成功
        message: 消息文本
        data: 任意可 JSON 序列化的数据，自动 dumps

    Returns:
        response_cls 实例
    """
    return response_cls(
        success=success,
        message=message,
        data=_dumps(data) if data is not None else '',
    )


# ------------------------------------------------------------------
# @grpc_rpc_handler 装饰器
# ------------------------------------------------------------------

def grpc_rpc_handler(response_cls: Type = None, log_error: bool = True):
    """装饰器：统一 gRPC RPC 方法的异常处理和响应构建。

    消除 90+ 个 RPC 方法中重复的::

        try:
            ...
            return _success(...)
        except Exception as e:
            logger.exception("Xxx failed")
            return _failure(str(e))

    被装饰方法只需写业务逻辑，有两种返回方式：

    1. 方法直接返回 dict → 装饰器自动 build_response(response_cls, data=result)
    2. 方法直接返回 response_cls 实例 → 装饰器原样返回

    异常时自动记录日志并返回失败响应。

    Args:
        response_cls: proto 响应类。若方法返回非 proto 实例时使用。
        log_error: 是否在异常时记录日志（默认 True）。

    用法::

        class MyServicer(...):
            @grpc_rpc_handler(response_cls=MyResponse)
            def DoSomething(self, request, context=None):
                data = _loads(request.data, {})
                result = self.handler.handle(data)
                return result  # dict → 自动包装为 MyResponse
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, request, context=None):
            try:
                result = func(self, request, context)
                # 如果方法已返回 proto 实例，原样返回
                if response_cls and isinstance(result, response_cls):
                    return result
                # 方法返回 dict/None 等，用 response_cls 包装
                if response_cls:
                    return build_response(response_cls, data=result)
                # 未指定 response_cls，原样返回（需方法自己构建响应）
                return result
            except Exception as e:
                func_name = getattr(func, '__name__', 'rpc_method')
                if log_error:
                    logger.exception("%s failed", func_name)
                if response_cls:
                    return build_response(
                        response_cls, success=False, message=str(e)
                    )
                raise

        return wrapper

    return decorator


# ------------------------------------------------------------------
# LazyHandlerMixin
# ------------------------------------------------------------------

class LazyHandlerMixin:
    """handler 懒加载 Mixin。

    消除各 servicer 类中 20+ 处重复的懒加载 property::

        @property
        def command_handler(self):
            if self._command_handler is None:
                from xxx import XxxHandler
                self._command_handler = XxxHandler()
            return self._command_handler

    使用方式：在 __init__ 中调用 ``_register_handler`` 注册，
    之后通过 ``self._get_handler('command')`` 访问。

    用法::

        class MyServicer(LazyHandlerMixin, MyServiceServicer):
            def __init__(self):
                self._register_handler('command', 'my_service.handlers', 'MyCommandHandler')
                self._register_handler('query', 'my_service.handlers', 'MyQueryHandler')
    """

    def _init_handlers(self):
        """初始化 handler 注册表（在 __init__ 中调用）。"""
        if not hasattr(self, '_handler_registry'):
            self._handler_registry = {}
        if not hasattr(self, '_handler_instances'):
            self._handler_instances = {}

    def _register_handler(self, name: str, module_path: str, class_name: str):
        """注册一个 handler。

        Args:
            name: handler 名称（如 'command' / 'query'）
            module_path: 模块路径（如 'my_service.application.handlers')
            class_name: 类名（如 'MyCommandHandler'）
        """
        self._init_handlers()
        self._handler_registry[name] = (module_path, class_name)

    def _get_handler(self, name: str):
        """获取 handler 实例（懒加载）。

        Args:
            name: 注册时的名称

        Returns:
            handler 实例
        """
        if name not in self._handler_instances:
            if name not in self._handler_registry:
                raise AttributeError(f"Handler '{name}' not registered")
            module_path, class_name = self._handler_registry[name]
            import importlib
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            self._handler_instances[name] = cls()
        return self._handler_instances[name]


# ------------------------------------------------------------------
# 请求解析辅助
# ------------------------------------------------------------------

def parse_request_data(request) -> dict:
    """统一解析 gRPC 请求中的 data 字段。

    消除 30+ 处 ``_loads(request.data, {})`` 和
    ``_loads(getattr(request, 'data', ''), {})`` 三种写法混用。

    Args:
        request: gRPC 请求对象或 dict

    Returns:
        解析后的 dict，空数据返回 {}
    """
    if isinstance(request, dict):
        return request
    raw = getattr(request, 'data', '')
    return _loads(raw, {}) or {}
