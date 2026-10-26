"""DatabaseLogHandler 归档相关方法（Mixin）。

从原 log_handler.py 拆分而来，保持行为不变。

P0-3 DDD 改造：归档逻辑改为通过 gRPC 调用 task_service.ArchiveLogs，
不再直接 import task_service PO 或操作 DB session。
"""

import time
from datetime import datetime, timezone, timedelta

from shared.utils.log_handler._constants import (
    get_log_archive_threshold,
    LOG_HOT_DATA_DAYS,
    LOG_ARCHIVE_RETENTION_DAYS,
)


class _ArchiveMixin:
    """冷热数据分离、OSS 归档、过期归档清理。"""

    def _check_and_archive(self):
        """通过 gRPC 检查日志总量并触发归档"""
        # INT-1962：阈值取自配置（env LOG_ARCHIVE_THRESHOLD，缺省 300000）。
        # <= 0 表示运维已关停归档：直接返回，不查计数、不上传、不删行，
        # 也不打印任何日志噪音——关掉就该安静。
        threshold = get_log_archive_threshold()
        if threshold <= 0:
            return

        # INT-1902：归档与过期清理各自 try/except —— 任一环节失败不得阻断另一环节
        try:
            from shared.clients.grpc_clients import get_log_count
            result = get_log_count()
            total_count = result.get('total', 0)

            if total_count > threshold:
                print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INFO - Log count {total_count} exceeds threshold {threshold}, starting archive...")
                self._archive_old_logs()
        except Exception as e:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - ARCHIVE ERROR - {str(e)}")

        # 清理过期归档文件（每次归档检查时都执行，与归档解耦）
        try:
            self._clean_expired_archives()
        except Exception as e:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - ARCHIVE CLEANUP ERROR - {str(e)}")

    def _archive_old_logs(self):
        """通过 gRPC 分批归档冷数据日志到 OSS

        INT-1963：一批 = 服务端「取一批冷日志 → 写归档存储 → 成功才按 id
        删该批」，响应只含计数。本方法按 ``has_more`` 推进下一批：
        任一批失败即停（异常向上抛，外层打 ARCHIVE ERROR），已上传成功的
        批次不受影响、服务端一行都没多删，下一轮巡检从剩余冷日志继续。
        单轮批数受 ``LOG_ARCHIVE_MAX_BATCHES_PER_RUN`` 限制，避免一次巡检
        无界占用；超出的批次留给下一轮。
        """
        # INT-1902：archive_logs 必须在调用方作用域内导入——此前只在
        # _check_and_archive 里局部导入，本方法内 NameError 令归档每轮静默失败。
        # shared.clients.grpc_clients 与日志层存在反向依赖，不能提到模块级。
        from shared.clients.grpc_clients import archive_logs
        from shared.infrastructure.config import BaseConfig

        try:
            max_batches = max(1, int(
                getattr(BaseConfig, 'LOG_ARCHIVE_MAX_BATCHES_PER_RUN', 50) or 50))
        except (TypeError, ValueError):
            max_batches = 50

        archived_count = 0
        deleted_count = 0
        remaining = 0
        batches = 0

        def _stamp():
            return datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')

        while True:
            result = archive_logs(days=LOG_HOT_DATA_DAYS, dry_run=False)
            batches += 1
            batch_rows = int(result.get('archived_count', 0) or 0)
            archived_count += batch_rows
            deleted_count += int(result.get('deleted_count', 0) or 0)
            remaining = int(result.get('remaining_count', 0) or 0)
            if batch_rows:
                # 单批响应字节数（验收口径：远低于 GRPC_MAX_MESSAGE_MB）
                print(f"[{_stamp()}] - log_worker - INFO - Archive batch {batches}: "
                      f"rows={batch_rows}, deleted={result.get('deleted_count', 0)}, "
                      f"response_bytes={result.get('response_bytes', 0)}, "
                      f"has_more={result.get('has_more', False)}")
            if not result.get('has_more'):
                break
            if batches >= max_batches:
                print(f"[{_stamp()}] - log_worker - INFO - Archive reached {max_batches} batches "
                      f"this run, will continue archiving next cycle.")
                break

        if archived_count == 0:
            return

        print(f"[{_stamp()}] - log_worker - INFO - Archived {archived_count} logs to OSS via gRPC "
              f"(deleted {deleted_count}). Remaining: {remaining}")
        if remaining > get_log_archive_threshold():
            print(f"[{_stamp()}] - log_worker - INFO - Still {remaining} logs, will continue archiving next cycle.")

    def _clean_expired_archives(self):
        """清理 OSS 上过期的归档对象（LastModified 超过 LOG_ARCHIVE_RETENTION_DAYS 天）"""
        from shared.clients.oss_client import oss

        # OSS 不可用时跳过清理（本地存储无 TTL 语义）
        if not oss.is_available():
            return

        bucket = oss._bucket('archives')
        cutoff_time = time.time() - LOG_ARCHIVE_RETENTION_DAYS * 86400
        deleted_count = 0

        # 分页列出全部对象（list_objects_v2 单次最多 1000 条）
        # 注意：_client 可能未初始化，使用 _ensure_init() 确保可用
        oss._ensure_init()
        paginator = oss._client.get_paginator('list_objects_v2')
        try:
            for page in paginator.paginate(Bucket=bucket):
                for obj in page.get('Contents', []):
                    last_modified = obj['LastModified'].timestamp()
                    if last_modified < cutoff_time:
                        try:
                            # INT-1348：删除走管理类短超时客户端，OSS 不可达/响应
                            # 慢时快速失败，不让归档清理悬挂
                            oss._admin_client.delete_object(Bucket=bucket, Key=obj['Key'])
                            deleted_count += 1
                        except Exception:
                            pass
        except Exception as e:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - WARN - Clean expired archives failed: {str(e)}")
            return

        if deleted_count > 0:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INFO - Cleaned {deleted_count} expired archive objects on OSS, older than {LOG_ARCHIVE_RETENTION_DAYS} days.")
