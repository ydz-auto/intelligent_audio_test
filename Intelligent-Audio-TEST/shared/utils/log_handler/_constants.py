"""日志处理器相关常量。

从原 log_handler.py 拆分而来，保持行为不变。
"""

LOG_ARCHIVE_THRESHOLD = 300000
LOG_HOT_DATA_DAYS = 7
LOG_ARCHIVE_RETENTION_DAYS = 90
CONSOLE_LOG_MAX_LENGTH = 20000
# 入库日志 content 最大长度：超长截断并追加标记，避免大日志长驻队列/DB 导致内存膨胀
LOG_CONTENT_MAX_LENGTH = 4096
