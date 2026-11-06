# -*- coding: utf-8 -*-
"""LoggingPort 基础设施适配器。

在应用启动时调用 inject()，将 shared.utils.log_handler 的具体实现
注入到 shared.domain.ports.logging_port._LoggingProxy。
"""
from shared.domain.ports.logging_port import _LoggingProxy


class _LogHandlerAdapter:
    """适配 shared.utils.log_handler 到 LoggingPort 接口。"""

    @staticmethod
    def log_not_emit(level, module, content, **kwargs):
        from shared.utils.log_handler import log_not_emit as _impl
        _impl(level, module, content, **kwargs)

    @staticmethod
    def log_and_emit(level, module, content, **kwargs):
        from shared.utils.log_handler import log_and_emit as _impl
        _impl(level, module, content, **kwargs)


def inject():
    """注入日志实现到 domain port 代理。应在 app 启动时调用。"""
    _LoggingProxy.set_impl(_LogHandlerAdapter())
