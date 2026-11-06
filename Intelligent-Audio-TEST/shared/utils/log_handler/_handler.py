"""DatabaseLogHandler：组合各 Mixin 的最终类。

从原 log_handler.py 拆分而来，保持行为不变。
继承顺序保证 __init__ / emit 等方法解析正确。
"""

import logging

from shared.utils.log_handler._init_mixin import _InitMixin
from shared.utils.log_handler._worker_mixin import _WorkerMixin
from shared.utils.log_handler._websocket_mixin import _WebSocketMixin
from shared.utils.log_handler._archive_mixin import _ArchiveMixin
from shared.utils.log_handler._emit_mixin import _EmitMixin


class DatabaseLogHandler(
    _InitMixin,
    _WorkerMixin,
    _WebSocketMixin,
    _ArchiveMixin,
    _EmitMixin,
    logging.Handler,
):
    """
    异步数据库日志处理器，使用队列和后台线程写入数据库并推送 WebSocket
    支持批量写入、冷热数据分离、自动归档

    分流策略：
    - 有 task_id 或 test_case_id 的日志 → 入 DB + 推 WebSocket（任务/用例日志，前端需要实时查看）
    - 无 task_id/test_case_id 的日志 → 只写本地文件（系统/模块日志，不入库不推 WS）
    """
    pass
