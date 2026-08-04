"""模块级可变全局状态。

从原 log_handler.py 拆分而来，保持行为不变。
所有可变全局集中在此处，便于 set_* / get_db_handler 等函数读写。
"""

LOG_AND_EMIT_CONSOLE_LOG = None

_cached_socketio = None
_cached_app = None
_global_db_handler = None
_ws_broadcast_callback = None  # FastAPI WebSocket 广播回调
