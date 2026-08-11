"""DatabaseLogHandler 归档相关方法（Mixin）。

从原 log_handler.py 拆分而来，保持行为不变。

P0-3 DDD 改造：归档逻辑改为通过 gRPC 调用 task_service.ArchiveLogs，
不再直接 import task_service PO 或操作 DB session。
"""

import time
import json
from datetime import datetime, timezone, timedelta

from shared.utils.log_handler._constants import (
    LOG_ARCHIVE_THRESHOLD,
    LOG_HOT_DATA_DAYS,
    LOG_ARCHIVE_RETENTION_DAYS,
)


class _ArchiveMixin:
    """冷热数据分离、OSS 归档、过期归档清理。"""

    def _check_and_archive(self):
        """通过 gRPC 检查日志总量并触发归档"""
        try:
            from shared.clients.grpc_clients import get_log_count, archive_logs
            result = get_log_count()
            total_count = result.get('total', 0)

            if total_count > LOG_ARCHIVE_THRESHOLD:
                print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INFO - Log count {total_count} exceeds threshold {LOG_ARCHIVE_THRESHOLD}, starting archive...")
                self._archive_old_logs()

            # 清理过期归档文件（每次归档检查时都执行）
            self._clean_expired_archives()
        except Exception as e:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - ARCHIVE ERROR - {str(e)}")

    def _archive_old_logs(self):
        """通过 gRPC 归档冷数据日志到 OSS

        调用 task_service.ArchiveLogs 获取冷日志分组，写入 OSS 后由服务端删除。
        """
        from shared.infrastructure.storage import storage

        result = archive_logs(days=LOG_HOT_DATA_DAYS, dry_run=False)
        groups = result.get('groups', {})
        if not groups:
            return

        def _save_archive(stored_path, logs):
            """上传归档到存储（合并已存在文件，按时间排序）"""
            existing_logs = []
            if storage.exists(stored_path):
                try:
                    data = storage.load_bytes(stored_path)
                    existing_logs = json.loads(data)
                except Exception:
                    existing_logs = []
            existing_logs.extend(logs)
            existing_logs.sort(key=lambda x: x.get('time', '') or '')
            storage.save_bytes(
                json.dumps(existing_logs, ensure_ascii=False, indent=2).encode('utf-8'),
                'archives', stored_path, content_type='application/json'
            )

        archived_count = 0
        # groups key 格式: 'task_case/{task_id}/{case_id}/{date}' etc.
        for group_key, logs in groups.items():
            archived_count += len(logs)
            _save_archive(f'{group_key}.json', logs)

        remaining = result.get('remaining_count', 0)
        print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INFO - Archived {archived_count} logs to OSS via gRPC. Remaining: {remaining}")
        if remaining > LOG_ARCHIVE_THRESHOLD:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INFO - Still {remaining} logs, will continue archiving next cycle.")

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
                            oss._client.delete_object(Bucket=bucket, Key=obj['Key'])
                            deleted_count += 1
                        except Exception:
                            pass
        except Exception as e:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - WARN - Clean expired archives failed: {str(e)}")
            return

        if deleted_count > 0:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INFO - Cleaned {deleted_count} expired archive objects on OSS, older than {LOG_ARCHIVE_RETENTION_DAYS} days.")
