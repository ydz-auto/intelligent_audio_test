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
from shared.infrastructure.user_context import get_current_user_id


class _EmitMixin:
    """日志三分流（INT-81 / INT-1793 契约 Q1，三分支互斥、每个分支 return）：

    - 业务日志（有 task_id）→ 业务日志文件（logs/business/...，去库化），
      可经 LOG_BUSINESS_DB_ENABLED 回退开关恢复入库；需实时查看的推 WebSocket
    - 审计事件（显式携带 `audit_event`）→ 审计文件（logs/audit/...），
      经 task_service 的 BatchCreateLogs 单写者落盘（H4）；
      可经 LOG_AUDIT_DB_ENABLED 故障回退双写入库
    - 其余（同 category 的运维日志、预览日志、审计开关关闭）→ 只写本地服务文件

    「一条事件恰好一行」靠分流顺序保证：审计身份只看 `audit_event` 实参
    （H1），不看 category —— category='device' 同时承载真审计事件与设备运维
    日志，按 category 搬文件会把运维日志灌进审计语料。
    """

    def emit(self, record):
        """
        分流处理日志（三分支互斥）：
        - 有 task_id → 业务日志文件（+ WebSocket）；
          LOG_BUSINESS_DB_ENABLED=True 时兼容性双写入库队列
        - audit_event → 审计文件（BatchCreateLogs 单写者落盘）；
          LOG_AUDIT_DB_ENABLED=True 时故障回退双写入库
        - 其余 → 只写本地服务文件（删除原 S2 入库路径）
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

            # === 分流判断（INT-1793 契约 Q1：三分支互斥，每个分支 return）===
            task_id = getattr(record, 'task_id', None)
            test_case_id = getattr(record, 'test_case_id', None)
            category = str(getattr(record, 'category', '') or '').lower()
            # H1：审计身份只看显式 audit_event 实参，不看 category
            audit_event = getattr(record, 'audit_event', None)

            # === 分支 1：业务日志（INT-81）：有 task_id 落业务文件，不写 logs 表 ===
            # 分流顺序约束（INT-81 审计问题 4 固化）：带 task_id 的设备/音频交互
            # 日志（category='device'/'audio'）是业务日志，必须先于审计判断命中
            if task_id is not None:
                self._enqueue_business_log(record, task_id, test_case_id,
                                           category, log_message)
                if self._settings.business_db_enabled:
                    self._enqueue_db_log(record, task_id, test_case_id,
                                         category, log_message)
                return

            # === 分支 2：审计事件 → 审计文件（task_service 单写者落盘，H4）===
            if audit_event and self._settings.audit_enabled:
                self._enqueue_audit_log(record, audit_event, category, log_message)
                if self._settings.audit_db_enabled:
                    # 故障回退：同一事件再入 DB 一次（读侧不感知）
                    self._enqueue_db_log(record, None, test_case_id, category, log_message)
                return

            # === 分支 3：其余（含审计开关关闭、D2 预览日志、同 category 运维日志）
            # → 只写服务文件；原「无 task_id 审计类入 DB 队列」的 S2 路径已删除 ===
            if self._file_handler:
                try:
                    self._file_handler.emit(record)
                except Exception:
                    # 文件写入失败不影响主流程
                    pass
            return

        except Exception as e:
            # emit 自身异常总是打印，避免静默失败；
            # stderr 可能是坏管道（INT-102），打印失败静默，不影响调用方
            safe_console_print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_handler - ERROR - emit failed: {str(e)}", file=sys.stderr)

    def _enqueue_db_log(self, record, task_id, test_case_id, category, log_message):
        """入库路径（仅回滚开关可达）：业务回滚双写 / 审计故障回退双写。

        与历史入库行为一致：TTL 去重（审计类别除外）+ 截断 + 入 DB 队列。
        条目 sink='db' 告知 task_service 走原 batch_create 实现。
        """
        is_audit_log = category in AUDIT_LOG_CATEGORIES
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
            'kind': 'db',
            'sink': 'db',
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
            'user_id': get_current_user_id(),
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
            'user_id': get_current_user_id(),
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

    def _enqueue_audit_log(self, record, audit_event, category, log_message):
        """审计事件入队列：worker 合并进 BatchCreateLogs 批次（sink='audit_file'）。

        审计事件只落审计 JSONL（不写服务文件、不推 WebSocket）；实际写盘方是
        task_service（H4 单写者），本条只做载荷组装并随条目透传产生进程名。
        内容不截断（审计语料完整），操作人字段由写盘侧从 content JSON 提取（H2）。
        """
        from shared.logging.config import resolve_service_name

        entry = {
            'kind': 'audit',
            'sink': 'audit_file',
            'event': audit_event,
            'service': resolve_service_name(),
            'time': datetime.now(timezone(timedelta(hours=8))),
            'level': record.levelname.upper(),
            'category': category,
            'module': record.module if hasattr(record, 'module') else 'unknown',
            'source': getattr(record, 'source', 'backend').lower(),
            'content': log_message,
            'task_id': None,
            'device_id': getattr(record, 'device_id', None),
            'api_id': getattr(record, 'api_id', None),
            'test_case_id': getattr(record, 'test_case_id', None),
            'thread_id': getattr(record, 'thread_id', None) or str(threading.get_ident()),
            'algorithm_type': getattr(record, 'algorithm_type', None),
            'user_id': get_current_user_id(),
            'push_to_websocket': False,
        }
        try:
            self.queue.put_nowait(entry)
        except queue.Full:
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(entry)
            except (queue.Empty, queue.Full):
                self._dropped_log_count = getattr(self, '_dropped_log_count', 0) + 1
