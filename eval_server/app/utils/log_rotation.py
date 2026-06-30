# -*- coding: utf-8 -*-
"""按时间和文件大小分卷的日志处理器"""

import os
import time
from logging.handlers import TimedRotatingFileHandler


class SizeTimeRotatingFileHandler(TimedRotatingFileHandler):
    """
    同时按时间和文件大小轮转的日志处理器。

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
        """检查是否需要轮转：时间到了 OR 文件太大"""
        if super().shouldRollover(record):
            return True
        if self.maxBytes > 0 and self.stream:
            self.stream.seek(0, 2)
            if self.stream.tell() >= self.maxBytes:
                return True
        return False

    def doRollover(self):
        """轮转日志文件，Windows 下文件被占用时跳过而非崩溃"""
        try:
            super().doRollover()
        except (PermissionError, OSError):
            # Windows 下文件可能被其他进程占用，跳过本次轮转
            # 重置 rolloverAt 避免每条日志都重试
            self.rolloverAt = time.time() + self.interval
