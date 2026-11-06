# -*- coding: utf-8 -*-
"""日志端口 ABC（Domain Port）。

domain 层通过此接口记录日志，不直接依赖 shared.utils.log_handler。
infrastructure 层在启动时注入具体实现（log_and_emit / log_not_emit）。

用法（domain 层）：
    from shared.domain.ports.logging_port import log_not_emit, log_and_emit

    log_not_emit('DEBUG', 'module', 'message')
"""
from abc import ABC, abstractmethod


class LoggingPort(ABC):
    """日志端口接口。"""

    @abstractmethod
    def log(self, level, module, content, **kwargs):
        ...


class _LoggingProxy:
    """延迟代理：首次调用时注入 infrastructure 实现。

    domain 层 import 此对象的 log_not_emit / log_and_emit 属性，
    在 infrastructure 层调用 set_impl() 之前调用时会安全降级为 no-op。
    """
    _impl = None

    @classmethod
    def set_impl(cls, impl):
        """由 infrastructure 层在启动时调用，注入具体实现。"""
        cls._impl = impl

    @classmethod
    def log_not_emit(cls, level, module, content, **kwargs):
        if cls._impl is not None:
            return cls._impl.log_not_emit(level, module, content, **kwargs)

    @classmethod
    def log_and_emit(cls, level, module, content, **kwargs):
        if cls._impl is not None:
            return cls._impl.log_and_emit(level, module, content, **kwargs)


# domain 层直接 import 这两个符号
log_not_emit = _LoggingProxy.log_not_emit
log_and_emit = _LoggingProxy.log_and_emit
