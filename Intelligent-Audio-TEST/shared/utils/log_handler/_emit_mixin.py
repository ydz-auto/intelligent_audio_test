"""DatabaseLogHandler emit 方法（Mixin）。

从原 log_handler.py 拆分而来，保持行为不变。
"""

import re
import sys
import hashlib
import threading
import queue
from datetime import datetime, timezone, timedelta

from shared.utils.log_handler._constants import (
    CONSOLE_LOG_MAX_LENGTH,
)


class _EmitMixin:
    """日志分流：任务/用例日志走 DB+WS，其余写本地文件。"""

    def emit(self, record):
        """
        分流处理日志：
        - 有 task_id 或 test_case_id → 入 DB 队列 + 推 WebSocket（任务/用例日志）
        - 无 task_id/test_case_id → 只写本地文件（系统/模块日志，不入库不推 WS）
        """
        try:
            # 跳过内部模块日志
            if hasattr(record, 'module') and record.module in ['log_controller', 'log_handler', 'database']:
                return

            log_message = self.format(record)

            # 去掉日志内容中的时间戳前缀 [2026-02-10T20:13:25.243757+08:00]
            log_message = re.sub(r'^\[\d{4}-\d{2}-\d{2}T[\d\.:+\-]+\]', '', log_message).strip()

            # 如果是标准的 logging 调用（不是通过 log_and_emit），也打印到控制台
            if not getattr(record, 'from_log_and_emit', False):
                self._console_log(record.levelname.upper(), f"[{record.module}] {log_message[:CONSOLE_LOG_MAX_LENGTH]}{'...' if len(log_message) > CONSOLE_LOG_MAX_LENGTH else ''}")

            # 跳过 WebSocket 相关日志
            if 'WebSocket' in log_message or 'socketio' in log_message or 'emitting event' in log_message:
                return

            # === 分流判断：是否为任务/用例相关日志 ===
            task_id = getattr(record, 'task_id', None)
            test_case_id = getattr(record, 'test_case_id', None)
            is_task_related = task_id is not None or test_case_id is not None

            # 非任务/用例日志：只写文件，不入库不推 WS
            if not is_task_related:
                if self._file_handler:
                    try:
                        self._file_handler.emit(record)
                    except Exception:
                        # 文件写入失败不影响主流程
                        pass
                return

            # === 以下为任务/用例日志：走 DB + WS 路径 ===

            # 去重检查：指纹带上 task_id/test_case_id/category，避免同结构不同用例日志被误吞
            ctx_key = f"{record.levelno}-{record.module}-{task_id}-{test_case_id}-{getattr(record, 'category', '')}-{log_message}"
            log_fingerprint = hashlib.md5(ctx_key.encode('utf-8')).hexdigest()
            current_time = datetime.now().timestamp()

            if log_fingerprint in self.recent_logs:
                if current_time - self.recent_logs[log_fingerprint] < self.log_ttl:
                    return

            self.recent_logs[log_fingerprint] = current_time

            # 清理过期指纹
            if len(self.recent_logs) > self.max_recent_logs:
                self.recent_logs = {fp: ts for fp, ts in self.recent_logs.items() if current_time - ts < self.log_ttl}

            # 准备异步写入的数据
            log_data = {
                'time': datetime.now(timezone(timedelta(hours=8))),
                'level': record.levelname.upper(),
                'module': record.module if hasattr(record, 'module') else 'unknown',
                'category': getattr(record, 'category', 'system').lower(),
                'source': getattr(record, 'source', 'backend').lower(),
                'content': log_message,
                'task_id': task_id,
                'device_id': getattr(record, 'device_id', None),
                'api_id': getattr(record, 'api_id', None),
                'test_case_id': test_case_id,
                'thread_id': getattr(record, 'thread_id', None) or str(threading.get_ident()),
                'algorithm_type': getattr(record, 'algorithm_type', None),
                'push_to_websocket': getattr(record, 'push_to_websocket', True)
            }

            # 放入队列：非阻塞，满时打印 stderr（不被 console_log 开关屏蔽），便于发现丢日志
            try:
                self.queue.put_nowait(log_data)
            except queue.Full:
                print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_handler - WARN - Log queue full (maxsize={self.queue.maxsize}), dropping log: [{log_data.get('level')}] {log_data.get('module')} - {log_data.get('content')[:200]}", file=sys.stderr)
            except Exception as qe:
                print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_handler - ERROR - put queue failed: {qe}", file=sys.stderr)

        except Exception as e:
            # emit 自身异常总是打印，避免静默失败
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_handler - ERROR - emit failed: {str(e)}", file=sys.stderr)
