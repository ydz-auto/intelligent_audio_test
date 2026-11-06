"""日志处理器相关常量。

从原 log_handler.py 拆分而来，保持行为不变。
"""

# 归档阈值不再写死在本模块（INT-1962）：阈值为数值配置，运行期一律经
# get_log_archive_threshold() 读 shared.infrastructure.config（env
# LOG_ARCHIVE_THRESHOLD 可覆盖，<= 0 = 禁用归档）。此处只做转出，
# 让日志层的所有开关从同一个模块取。
from shared.infrastructure.config import (  # noqa: F401  (转出给 log_handler 包)
    get_log_archive_threshold,
)

LOG_HOT_DATA_DAYS = 7
LOG_ARCHIVE_RETENTION_DAYS = 90
CONSOLE_LOG_MAX_LENGTH = 20000
# 入库日志 content 最大长度：超长截断并追加标记，避免大日志长驻队列/DB 导致内存膨胀
LOG_CONTENT_MAX_LENGTH = 4096
