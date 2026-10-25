"""grpc_proxies 包共享助手：_grpc_call 通用调用包装、_CompletedFuture 已完成 future 代理、_logger。"""
import logging
from typing import Any, Callable

_logger = logging.getLogger(__name__)


def _attach_code(result: dict, resp) -> dict:
    """把 TaskConfigResponse.code 提升到代理返回字典（INT-1759）

    业务码以 proto 字段为准（网关据此映射 HTTP 状态）；0 = servicer 未填，
    回退读 data JSON 的 code（INT-566 fold 旧口径，兼容未重发布的 servicer）。
    """
    code = int(getattr(resp, 'code', 0) or 0)
    if not code:
        data = result.get('data')
        if isinstance(data, dict) and isinstance(data.get('code'), int):
            code = data['code']
    if code:
        result['code'] = code
    return result


def _grpc_call(
    call_func: Callable[[], Any],
    default_return: Any = None,
    error_msg_prefix: str = "操作失败",
    log_error: bool = True,
    reraise: bool = False,
) -> Any:
    """通用的 gRPC 调用包装，统一异常处理。

    Args:
        call_func: 执行 gRPC 调用的无参函数
        default_return: 异常时的默认返回值；若为 callable，则以异常对象为参数调用
        error_msg_prefix: 错误消息前缀，用于日志
        log_error: 是否记录异常日志
        reraise: True 时记录日志后重新抛出异常（写操作失败必须让调用方感知，
            不得吞成默认值造成假成功）
    """
    try:
        return call_func()
    except Exception as e:
        if log_error:
            _logger.error(f"{error_msg_prefix}: {e}", exc_info=True)
        if reraise:
            raise
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
