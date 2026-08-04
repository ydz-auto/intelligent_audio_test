"""DatabaseLogHandler 初始化与设置相关方法（Mixin）。

从原 log_handler.py 拆分而来，保持行为不变。
"""

import os
import sys
import logging
import threading
import queue
from datetime import datetime, timezone, timedelta

from shared.utils.log_handler._file_handler import SizeTimeRotatingFileHandler


class _InitMixin:
    """初始化、文件处理器与基础设置方法。"""

    def __init__(self):
        super().__init__()
        self.recent_logs = {}
        self.max_recent_logs = 200
        self.log_ttl = 10
        self.enable_console_log = False
        self.socketio_instance = None
        self.flask_app = None
        self._ws_broadcast_callback = None  # FastAPI WebSocket 广播回调
        self._redis_pubsub = None  # Redis PubSub 实例（子服务进程用）

        self._last_db_warning_time = 0
        self._last_ws_warning_time = 0
        self._warning_throttle = 5

        self.queue = queue.Queue(maxsize=50000)

        self._batch_size = 100
        self._batch_timeout = 1.0
        self._last_archive_check = 0
        self._archive_check_interval = 300

        # 非任务/用例日志的文件处理器
        self._file_handler = self._init_file_handler()

        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()

    def _init_file_handler(self):
        """初始化 SizeTimeRotatingFileHandler，用于写入非任务/用例相关的系统日志

        同时按时间（每天午夜）和大小（10MB）轮转，保留 30 个历史文件。
        Windows 下文件被占用时轮转失败不中断日志。
        """
        try:
            log_dir = os.path.join(os.getcwd(), 'logs')
            os.makedirs(log_dir, exist_ok=True)
            file_formatter = logging.Formatter(
                '[%(asctime)s] %(levelname)-8s %(module)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler = SizeTimeRotatingFileHandler(
                os.path.join(log_dir, 'app.log'),
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=30,
                when='midnight',
                interval=1,
                encoding='utf-8'
            )
            handler.setFormatter(file_formatter)
            return handler
        except Exception as e:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_handler - WARN - File handler init failed: {e}")
            return None

    def set_socketio(self, socketio):
        """显式设置 SocketIO 实例"""
        self.socketio_instance = socketio

    def set_flask_app(self, app):
        """显式设置 Flask App 实例"""
        self.flask_app = app

    def set_console_log(self, enable):
        self.enable_console_log = enable

    def _console_log(self, level, message):
        if self.enable_console_log:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - DatabaseLogHandler - {level} - {message}")
            sys.stdout.flush()
