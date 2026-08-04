"""SizeTimeRotatingFileHandler：按时间+大小轮转的文件日志处理器。

从原 log_handler.py 拆分而来，保持行为不变。
"""

import os
import time
import logging.handlers


class SizeTimeRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """同时按时间和文件大小轮转的日志处理器。

    - 每天午夜（或指定间隔）轮转
    - 文件超过 maxBytes 时也轮转
    - 保留最多 backupCount 个历史文件
    - Windows 下文件被占用时轮转失败不中断日志
    """

    def __init__(self, filename, maxBytes=10 * 1024 * 1024, backupCount=30,
                 when='midnight', interval=1, encoding='utf-8'):
        self.maxBytes = maxBytes
        os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)
        super().__init__(
            filename, when=when, interval=interval,
            backupCount=backupCount, encoding=encoding,
        )

    def shouldRollover(self, record):
        if super().shouldRollover(record):
            return True
        if self.maxBytes > 0 and self.stream:
            self.stream.seek(0, 2)
            if self.stream.tell() >= self.maxBytes:
                return True
        return False

    def doRollover(self):
        try:
            super().doRollover()
        except (PermissionError, OSError):
            time.sleep(0.1)
            try:
                super().doRollover()
            except (PermissionError, OSError):
                pass
