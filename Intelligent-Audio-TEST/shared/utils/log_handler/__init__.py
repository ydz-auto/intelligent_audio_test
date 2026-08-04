"""log_handler 包：将原 log_handler.py 拆分为多个子模块。

拆分后的结构：
    _constants.py       常量
    _state.py           模块级可变全局状态
    _file_handler.py    SizeTimeRotatingFileHandler
    _init_mixin.py      DatabaseLogHandler 初始化 / 设置方法
    _worker_mixin.py    后台工作线程 / 批次写入
    _websocket_mixin.py WebSocket 推送 / Redis PubSub 转发
    _archive_mixin.py   冷热数据分离 / OSS 归档
    _emit_mixin.py      emit 分流入口
    _handler.py         DatabaseLogHandler 最终组合类
    _api.py             模块级对外 API 函数

为保证向后兼容，本 __init__.py 重新导出原文件所有公开符号，
并通过模块级 __getattr__ 透明转发可变全局状态（如 _cached_socketio、
_cached_app、_global_db_handler、_ws_broadcast_callback、LOG_AND_EMIT_CONSOLE_LOG）。
这意味着旧代码中 `from shared.utils.log_handler import _cached_socketio`
仍然会返回当前最新的值（动态读取，不会因快照失效）。
"""

# 状态模块本身（供内部模块通过 _state._xxx 访问 / 修改同一份全局状态）
# 必须最先导入：后续的 _worker_mixin / _websocket_mixin / _api 会执行
# `from shared.utils.log_handler import _state`，需要该属性已挂在包上。
from . import _state

# 常量
from shared.utils.log_handler._constants import (
    LOG_ARCHIVE_THRESHOLD,
    LOG_HOT_DATA_DAYS,
    LOG_ARCHIVE_RETENTION_DAYS,
    CONSOLE_LOG_MAX_LENGTH,
)

# 文件处理器类
from shared.utils.log_handler._file_handler import SizeTimeRotatingFileHandler

# 最终组合类
from shared.utils.log_handler._handler import DatabaseLogHandler

# 模块级对外 API 函数
from shared.utils.log_handler._api import (
    set_socketio,
    set_ws_broadcast_callback,
    set_flask_app,
    get_db_handler,
    log_not_emit,
    log_and_emit,
)

# 不可变全局的公开符号，__all__ 列出用于 `from log_handler import *`
__all__ = [
    # 常量
    'LOG_ARCHIVE_THRESHOLD',
    'LOG_HOT_DATA_DAYS',
    'LOG_ARCHIVE_RETENTION_DAYS',
    'CONSOLE_LOG_MAX_LENGTH',
    # 类
    'SizeTimeRotatingFileHandler',
    'DatabaseLogHandler',
    # 函数
    'set_socketio',
    'set_ws_broadcast_callback',
    'set_flask_app',
    'get_db_handler',
    'log_not_emit',
    'log_and_emit',
    # 可变全局（通过 __getattr__ 动态转发，但 __all__ 中保留以便静态导出工具识别）
    'LOG_AND_EMIT_CONSOLE_LOG',
    '_cached_socketio',
    '_cached_app',
    '_global_db_handler',
    '_ws_broadcast_callback',
]


# 可变全局状态动态转发：每次从包对象上读取这些名字时，
# 都从 _state 模块读取最新值；赋值时写回 _state 模块。
# 这保证旧代码 `from shared.utils.log_handler import _cached_socketio`
# 在使用时拿到的是导入时刻的绑定值（Python 语义本身如此），
# 但 `shared.utils.log_handler._cached_socketio` 这种属性访问仍能拿到最新值。
# 对于 event_manager._common.get_socketio() 的实现（持有导入时的引用），
# 它返回的是该引用；只要 set_socketio 修改的是 _state._cached_socketio，
# 而本 __init__ 又把 _cached_socketio 动态映射到 _state._cached_socketio，
# 新的 `import ...; mod._cached_socketio` 访问就能看到新值。
_DYNAMIC_STATE_NAMES = (
    'LOG_AND_EMIT_CONSOLE_LOG',
    '_cached_socketio',
    '_cached_app',
    '_global_db_handler',
    '_ws_broadcast_callback',
)


def __getattr__(name):
    if name in _DYNAMIC_STATE_NAMES:
        return getattr(_state, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
