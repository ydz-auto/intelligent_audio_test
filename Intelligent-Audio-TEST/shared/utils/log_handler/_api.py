"""模块级对外 API 函数。

从原 log_handler.py 拆分而来，保持行为不变。
这些函数直接操作 _state 中的全局可变状态。
为保证拆分后跨模块仍共享同一份可变全局状态，
所有读写均通过 _state 模块对象属性访问（替代原单文件中的 global 语句）。
"""

import sys
import threading
import logging
from datetime import datetime, timezone, timedelta

from . import _state
from shared.utils.log_handler._constants import (
    CONSOLE_LOG_MAX_LENGTH,
)
from shared.utils.log_handler._handler import DatabaseLogHandler


def set_socketio(socketio):
    """设置全局 SocketIO/WS 管理器实例"""
    _state._cached_socketio = socketio
    if _state._global_db_handler:
        _state._global_db_handler.set_socketio(socketio)

def set_ws_broadcast_callback(callback):
    """设置 WebSocket 广播回调（FastAPI ConnectionManager.broadcast_log_sync）"""
    _state._ws_broadcast_callback = callback
    if _state._global_db_handler:
        _state._global_db_handler._ws_broadcast_callback = callback

def set_flask_app(app):
    """设置全局 App 实例（FastAPI 兼容，保留向后兼容）"""
    _state._cached_app = app
    if _state._global_db_handler:
        _state._global_db_handler.set_flask_app(app)

def get_db_handler():
    """获取或创建全局 DatabaseLogHandler 实例"""
    if _state._global_db_handler is None:
        _state._global_db_handler = DatabaseLogHandler()

        # 根据Flask应用的debug模式自动设置控制台日志
        console_log_enabled = _state.LOG_AND_EMIT_CONSOLE_LOG
        if console_log_enabled is None:
            if _state._cached_app and hasattr(_state._cached_app, 'debug'):
                console_log_enabled = _state._cached_app.debug
            else:
                console_log_enabled = False

        _state._global_db_handler.set_console_log(console_log_enabled)
        if _state._cached_socketio:
            _state._global_db_handler.set_socketio(_state._cached_socketio)
        if _state._cached_app:
            _state._global_db_handler.set_flask_app(_state._cached_app)

        # 调试信息：确认单例已创建（只在调试模式输出）
        if console_log_enabled:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - get_db_handler - INFO - DatabaseLogHandler singleton created.")
    return _state._global_db_handler

# 保留log_and_emit作为包装函数，支持外部直接调用
def log_not_emit(level, module, content, category='system', source='backend', task_id=None, device_id=None, api_id=None, test_case_id=None, algorithm_type=None, push_to_websocket=False, enable_console_log=None, **kwargs):

    """核心方法：保存日志到数据库不推送到 WebSocket"""
    log_and_emit(level, module, content, category=category, source=source, task_id=task_id, device_id=device_id, api_id=api_id, test_case_id=test_case_id, algorithm_type=algorithm_type, push_to_websocket=False, enable_console_log=enable_console_log, **kwargs)
    return

# 保留log_and_emit作为包装函数，支持外部直接调用
def log_and_emit(level, module, content, category='system', source='backend', task_id=None, device_id=None, api_id=None, test_case_id=None, algorithm_type=None, push_to_websocket=True, enable_console_log=None, **kwargs):
    """核心方法：保存日志到数据库并推送到 WebSocket"""

    # 从配置中获取控制台日志设置
    if enable_console_log is None:
        if _state._cached_app and hasattr(_state._cached_app, 'config') and isinstance(_state._cached_app.config, dict):
            enable_console_log = _state._cached_app.config.get('CONSOLE_LOG_ENABLED', True)
        else:
            enable_console_log = True

    # 在生产模式下，自动过滤DEBUG级别日志
    level_upper = level.upper()
    should_filter = False

    if level_upper == 'DEBUG' and not enable_console_log:
        should_filter = True

    if should_filter:
        return  # 直接返回，不记录DEBUG日志

    if enable_console_log:
        # 统一输出到 stdout 确保可见性
        print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_and_emit - {level_upper} - [{module}] {content[:CONSOLE_LOG_MAX_LENGTH]}{'...' if len(content) > CONSOLE_LOG_MAX_LENGTH else ''}")
        sys.stdout.flush()

    try:
        # 创建日志记录对象
        record = logging.LogRecord(
            name=module,
            level=getattr(logging, level.upper(), logging.INFO),
            pathname='',
            lineno=0,
            msg=content,
            args=(),
            exc_info=None
        )
        record.module = module
        record.category = category
        record.source = source
        record.task_id = task_id
        record.device_id = device_id
        record.api_id = api_id
        record.test_case_id = test_case_id
        record.algorithm_type = algorithm_type

        # 将推送标志存入 record
        record.push_to_websocket = push_to_websocket

        for key, value in kwargs.items():
            setattr(record, key, value)

        if not hasattr(record, 'thread_id'):
            record.thread_id = kwargs.get('thread_id') or str(threading.get_ident())

        # 标记来自 log_and_emit，避免在 handler.emit 中重复打印
        record.from_log_and_emit = True

        handler = get_db_handler()
        handler.emit(record)

    except Exception as e:
        # 如果获取不到 handler，尝试直接打印
        print(f"Error in log_and_emit: {str(e)}", file=sys.stderr)
