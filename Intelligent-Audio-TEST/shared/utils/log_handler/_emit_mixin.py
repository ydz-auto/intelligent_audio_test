"""DatabaseLogHandler emit 方法（Mixin）。

从原 log_handler.py 拆分而来，保持行为不变。
"""

import re
import sys
import hashlib
import threading
import queue
from datetime import datetime, timezone, timedelta

from shared.models.common_enums import AUDIT_LOG_CATEGORIES
from shared.utils.secret_mask import mask_text
from shared.utils.log_handler._console import safe_console_print
from shared.utils.log_handler._constants import (
    CONSOLE_LOG_MAX_LENGTH,
    LOG_CONTENT_MAX_LENGTH,
)


class _EmitMixin:
    """日志三分流（INT-81）：

    - 业务日志（有 task_id）→ 业务日志文件（logs/business/...，去库化），
      可经 LOG_BUSINESS_DB_ENABLED 回退开关恢复入库；需实时查看的推 WebSocket
    - 审计类日志（auth/benchmark/device 审计）→ 本地服务文件 + DB 队列
    - 其余系统日志（无任务上下文）→ 只写本地服务文件
    """

    def emit(self, record):
        """
        分流处理日志：
        - 有 task_id → 业务日志文件（+ WebSocket）；
          LOG_BUSINESS_DB_ENABLED=True 时兼容性双写入库队列
        - 无 task_id 且审计类 → 本地服务文件 + DB 队列
        - 其余 → 只写本地服务文件
        """
        try:
            # 跳过内部模块日志
            if hasattr(record, 'module') and record.module in ['log_controller', 'log_handler', 'database']:
                return

            log_message = self.format(record)

            # 去掉日志内容中的时间戳前缀 [2026-02-10T20:13:25.243757+08:00]
            log_message = re.sub(r'^\[\d{4}-\d{2}-\d{2}T[\d\.:+\-]+\]', '', log_message).strip()

            # 统一脱敏（INT-70 §8.1）：密钥与敏感头不出现在任何落盘/推送内容，
            # 覆盖业务文件、WebSocket 推送、DB 入库与控制台全部出口
            log_message = mask_text(log_message)

            # 如果是标准的 logging 调用（不是通过 log_and_emit），也打印到控制台
            if not getattr(record, 'from_log_and_emit', False):
                self._console_log(record.levelname.upper(), f"[{record.module}] {log_message[:CONSOLE_LOG_MAX_LENGTH]}{'...' if len(log_message) > CONSOLE_LOG_MAX_LENGTH else ''}")

            # 跳过 WebSocket 相关日志
            if 'WebSocket' in log_message or 'socketio' in log_message or 'emitting event' in log_message:
                return

            # === 分流判断 ===
            task_id = getattr(record, 'task_id', None)
            test_case_id = getattr(record, 'test_case_id', None)
            category = str(getattr(record, 'category', '') or '').lower()
            # 审计类日志（auth/benchmark）无 task_id/test_case_id，但必须落库
            # （INT-30 P1 回归修复：原分流把无任务上下文的审计事件降级为只写
            # 本地文件，logs 表永远收不到审计行）
            is_audit_log = category in AUDIT_LOG_CATEGORIES
            is_task_related = task_id is not None or test_case_id is not None

            # === 业务日志（INT-81）：有 task_id 落业务文件，停止写 logs 表 ===
            # 分流顺序约束（INT-81 审计问题 4 固化，不得改为「审计类别优先」）：
            # - 审计事件写入器（write_auth_audit / write_benchmark_audit /
            #   write_device_audit）按约定永不携带 task_id/test_case_id，
            #   走下方「无任务上下文」分支保证落库；
            # - AUDIT_LOG_CATEGORIES 中的 'device' 与业务日志类型 DEVICE 共用
            #   同一 category 名：任务执行期的设备交互/音频链路日志
            #   （category='device'/'audio' 且带 task_id）是业务日志，
            #   必须走业务文件路径（去库化），若按审计类别优先改道会把整个
            #   设备/音频业务日志流灌回 logs 表，违反本卡验收标准 3；
            # - 回滚开关 LOG_BUSINESS_DB_ENABLED=True 时带 task_id 的审计类别
            #   日志经 _enqueue_db_log 入库（审计不参与 TTL 去重），双保险。
            if task_id is not None:
                self._enqueue_business_log(record, task_id, test_case_id,
                                           category, log_message)
                if self._settings.business_db_enabled:
                    self._enqueue_db_log(record, task_id, test_case_id,
                                         category, log_message, is_audit_log)
                return

            # 非任务日志：默认只写文件不入库不推 WS；审计类双写文件 + 入库队列
            if not is_task_related:
                if self._file_handler:
                    try:
                        self._file_handler.emit(record)
                    except Exception:
                        # 文件写入失败不影响主流程
                        pass
                if not is_audit_log:
                    return

            # === 以下为入库路径（无 task_id 的用例日志 或 审计日志）===

            # 准备异步写入的数据
            # 超长日志截断：超过 LOG_CONTENT_MAX_LENGTH 字符时截断并追加标记，避免大日志长驻队列/DB 导致内存膨胀
            _content = log_message
            if len(_content) > LOG_CONTENT_MAX_LENGTH:
                _content = _content[:LOG_CONTENT_MAX_LENGTH] + '... [truncated]'
            log_data = {
                'time': datetime.now(timezone(timedelta(hours=8))),
                'level': record.levelname.upper(),
                'module': record.module if hasattr(record, 'module') else 'unknown',
                'category': category or 'system',
                'source': getattr(record, 'source', 'backend').lower(),
                'content': _content,
                'task_id': task_id,
                'device_id': getattr(record, 'device_id', None),
                'api_id': getattr(record, 'api_id', None),
                'test_case_id': test_case_id,
                'thread_id': getattr(record, 'thread_id', None) or str(threading.get_ident()),
                'algorithm_type': getattr(record, 'algorithm_type', None),
                'push_to_websocket': getattr(record, 'push_to_websocket', True)
            }

            # 放入队列：非阻塞，满时丢弃最旧一条再入队最新日志（保证最新日志不丢），并打印 stderr 便于发现丢日志
            try:
                self.queue.put_nowait(log_data)
            except queue.Full:
                try:
                    # 队列满：丢弃最旧一条（FIFO 队头），腾出空间入队最新日志
                    self.queue.get_nowait()
                    self.queue.put_nowait(log_data)
                except (queue.Empty, queue.Full):
                    # 并发竞争下其他线程已取空/再次塞满：直接丢弃新日志并计数
                    self._dropped_log_count = getattr(self, '_dropped_log_count', 0) + 1
                print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_handler - WARN - Log queue full (maxsize={self.queue.maxsize}), dropped oldest log to make room for latest: [{log_data.get('level')}] {log_data.get('module')} - {log_data.get('content')[:200]}", file=sys.stderr)
            except Exception as qe:
                print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_handler - ERROR - put queue failed: {qe}", file=sys.stderr)

        except Exception as e:
            # emit 自身异常总是打印，避免静默失败；
            # stderr 可能是坏管道（INT-102），打印失败静默，不影响调用方
            safe_console_print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_handler - ERROR - emit failed: {str(e)}", file=sys.stderr)

    def _enqueue_db_log(self, record, task_id, test_case_id, category, log_message, is_audit_log):
        """业务日志兼容性入库路径（LOG_BUSINESS_DB_ENABLED=True 回滚开关）。

        与历史入库行为一致：TTL 去重（审计除外）+ 截断 + 入 DB 队列。
        """
        if not is_audit_log:
            ctx_key = f"{record.levelno}-{record.module}-{task_id}-{test_case_id}-{category}-{log_message}"
            log_fingerprint = hashlib.md5(ctx_key.encode('utf-8')).hexdigest()
            current_time = datetime.now().timestamp()

            if log_fingerprint in self.recent_logs:
                if current_time - self.recent_logs[log_fingerprint] < self.log_ttl:
                    return

            self.recent_logs[log_fingerprint] = current_time

            # 清理过期指纹
            if len(self.recent_logs) > self.max_recent_logs:
                self.recent_logs = {fp: ts for fp, ts in self.recent_logs.items() if current_time - ts < self.log_ttl}

        _content = log_message
        if len(_content) > LOG_CONTENT_MAX_LENGTH:
            _content = _content[:LOG_CONTENT_MAX_LENGTH] + '... [truncated]'
        log_data = {
            'time': datetime.now(timezone(timedelta(hours=8))),
            'level': record.levelname.upper(),
            'module': record.module if hasattr(record, 'module') else 'unknown',
            'category': category or 'system',
            'source': getattr(record, 'source', 'backend').lower(),
            'content': _content,
            'task_id': task_id,
            'device_id': getattr(record, 'device_id', None),
            'api_id': getattr(record, 'api_id', None),
            'test_case_id': test_case_id,
            'thread_id': getattr(record, 'thread_id', None) or str(threading.get_ident()),
            'algorithm_type': getattr(record, 'algorithm_type', None),
            'push_to_websocket': getattr(record, 'push_to_websocket', True)
        }
        try:
            self.queue.put_nowait(log_data)
        except queue.Full:
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(log_data)
            except (queue.Empty, queue.Full):
                self._dropped_log_count = getattr(self, '_dropped_log_count', 0) + 1

    def _enqueue_business_log(self, record, task_id, test_case_id, category, log_message):
        """业务日志入文件队列：worker 线程落业务文件并按需推 WebSocket。

        文件内容不截断（去库化的意义在于保留完整日志）；WebSocket 推送
        载荷沿用 LOG_CONTENT_MAX_LENGTH 截断。轮次/评估ID 上下文来源：
        显式 record 属性优先，回退线程上下文（E2E 轮次循环 / 评估 Worker 设置）。
        """
        from shared.logging.context import get_current_evaluation_id, get_current_round
        from shared.logging.enums import log_type_for_category

        # prod 环境不落 DEBUG 级业务日志（dev/prod 环境区分，配置 LOG_ENVIRONMENT）
        if self._settings.is_prod and record.levelname.upper() == 'DEBUG':
            return

        _ws_content = log_message
        if len(_ws_content) > LOG_CONTENT_MAX_LENGTH:
            _ws_content = _ws_content[:LOG_CONTENT_MAX_LENGTH] + '... [truncated]'
        entry = {
            'kind': 'business',
            'time': datetime.now(timezone(timedelta(hours=8))),
            'level': record.levelname.upper(),
            'category': category or 'execution',
            'module': record.module if hasattr(record, 'module') else 'unknown',
            'source': getattr(record, 'source', 'backend').lower(),
            'content': log_message,
            'ws_content': _ws_content,
            'task_id': task_id,
            'device_id': getattr(record, 'device_id', None),
            'api_id': getattr(record, 'api_id', None),
            'test_case_id': test_case_id,
            'thread_id': getattr(record, 'thread_id', None) or str(threading.get_ident()),
            'algorithm_type': getattr(record, 'algorithm_type', None),
            'round': getattr(record, 'round', None) or get_current_round(),
            'evaluation_id': getattr(record, 'evaluation_id', None) or get_current_evaluation_id(),
            'log_type': log_type_for_category(category).value,
            'push_to_websocket': getattr(record, 'push_to_websocket', True),
        }
        try:
            self.queue.put_nowait(entry)
        except queue.Full:
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(entry)
            except (queue.Empty, queue.Full):
                self._dropped_log_count = getattr(self, '_dropped_log_count', 0) + 1
