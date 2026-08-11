"""grpc_proxies 包共享助手：_grpc_call 通用调用包装、_CompletedFuture 已完成 future 代理、_logger。"""
import logging
from typing import Any, Callable

_logger = logging.getLogger(__name__)


def _grpc_call(
    call_func: Callable[[], Any],
    default_return: Any = None,
    error_msg_prefix: str = "操作失败",
    log_error: bool = True,
) -> Any:
    """通用的 gRPC 调用包装，统一异常处理。

    Args:
        call_func: 执行 gRPC 调用的无参函数
        default_return: 异常时的默认返回值；若为 callable，则以异常对象为参数调用
        error_msg_prefix: 错误消息前缀，用于日志
        log_error: 是否记录异常日志
    """
    try:
        return call_func()
    except Exception as e:
        if log_error:
            _logger.error(f"{error_msg_prefix}: {e}", exc_info=True)
        if callable(default_return):
            return default_return(e)
        return default_return


class _CompletedFuture:
    """已完成的 future 代理：兼容原 audio_service.play_audio 返回 future 的用法"""

    def __init__(self, success, error=None):
        self._success = success
        self._error = error

    def result(self, timeout=None):
        if not self._success:
            raise Exception(self._error or "audio play failed")
        return self._success
