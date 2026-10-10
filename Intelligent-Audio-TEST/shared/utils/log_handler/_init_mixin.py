"""DatabaseLogHandler 初始化与设置相关方法（Mixin）。

从原 log_handler.py 拆分而来，保持行为不变。
"""

import threading
import queue
from datetime import datetime, timezone, timedelta

from shared.utils.log_handler._console import safe_console_print


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

        self._last_db_warning_time = 0
        self._last_ws_warning_time = 0
        self._warning_throttle = 5

        self.queue = queue.Queue(maxsize=50000)

        self._batch_size = 100
        self._batch_timeout = 1.0
        self._last_archive_check = 0
        self._archive_check_interval = 300
        self._archive_thread = None  # 归档巡检后台线程（进行中不重叠）

        # INT-81 日志体系：业务日志写入器（惰性单例）、保留清扫状态、配置快照
        self._business_writer = None
        self._business_seq = 0
        self._last_sweep_check = 0
        self._sweep_check_interval = 600
        self._sweep_thread = None
        from shared.logging.config import get_log_settings
        self._settings = get_log_settings()

        # 非任务/用例日志的文件处理器
        self._file_handler = self._init_file_handler()

        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()

    def _init_file_handler(self):
        """初始化服务运行日志文件处理器（INT-81：统一由 shared/logging 基座提供）

        写入 logs/{service_name}/app-{hostname}-{pid}.log（文件名含 hostname+pid
        进程标识：同宿主多进程靠 PID 区分，容器多副本靠 Docker 注入的短容器
        ID 区分，共享日志卷互不冲突），按天 + 按大小（LOG_SERVICE_MAX_MB，默认 50MB）
        双条件轮转，保留 LOG_SERVICE_RETENTION_DAYS 天（默认 30，由后台清扫器执行）。
        Windows 下文件被占用时轮转失败不中断日志。
        """
        try:
            from shared.logging import setup_service_file_logging
            return setup_service_file_logging()
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
            # stdout 可能是坏管道/受限编码（INT-102），写失败静默不炸业务路径
            safe_console_print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - DatabaseLogHandler - {level} - {message}")
