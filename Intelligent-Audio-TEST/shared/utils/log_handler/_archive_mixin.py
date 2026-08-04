"""DatabaseLogHandler 归档相关方法（Mixin）。

从原 log_handler.py 拆分而来，保持行为不变。
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

    def _check_and_archive(self, Log, SessionLocal):
        if not Log or not SessionLocal:
            return

        try:
            session = SessionLocal()
            try:
                total_count = session.query(Log).count()

                if total_count > LOG_ARCHIVE_THRESHOLD:
                    print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INFO - Log count {total_count} exceeds threshold {LOG_ARCHIVE_THRESHOLD}, starting archive...")
                    self._archive_old_logs(Log, SessionLocal, session, total_count)

                # 清理过期归档文件（每次归档检查时都执行）
                self._clean_expired_archives()
            finally:
                session.close()
        except Exception as e:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - ARCHIVE ERROR - {str(e)}")

    def _archive_old_logs(self, Log, SessionLocal, session, total_count):
        """
        将冷数据日志归档到 OSS（archives bucket），key 结构与 LogCommandService.archive_logs 一致：
            tasks/{task_id}/{case_id}/{date}.json
            tasks/{task_id}/{date}.json
            cases/{case_id}/{date}.json
            other/{date}.json
        归档完成后从数据库删除对应日志。
        """
        from shared.infrastructure.storage import storage

        cutoff_date = datetime.now(timezone(timedelta(hours=8))) - timedelta(days=LOG_HOT_DATA_DAYS)
        old_logs = session.query(Log).filter(Log.time < cutoff_date).order_by(Log.time.asc()).limit(100000).all()

        if not old_logs:
            # 没有冷数据，但总量仍超阈值：直接删除最旧的（无归档价值）
            delete_count = total_count - LOG_ARCHIVE_THRESHOLD
            if delete_count > 0:
                oldest_logs = session.query(Log).order_by(Log.time.asc()).limit(delete_count).all()
                log_ids = [log.id for log in oldest_logs]
                session.query(Log).filter(Log.id.in_(log_ids)).delete(synchronize_session=False)
                session.commit()
                print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INFO - Deleted {len(log_ids)} oldest logs (no archive needed).")
            return

        # 分组（与 LogCommandService.archive_logs 对齐）：
        #   task_case_logs[(task_id, case_id, date)] = [log_data, ...]
        #   task_only_logs[(task_id, date)] = [log_data, ...]
        #   case_only_logs[(case_id, date)] = [log_data, ...]
        #   other_logs[date] = [log_data, ...]
        task_case_logs = {}
        task_only_logs = {}
        case_only_logs = {}
        other_logs = {}

        for log in old_logs:
            log_data = {
                'id': log.id,
                'time': log.time.isoformat() if log.time else None,
                'level': log.level,
                'category': log.category,
                'module': log.module,
                'source': log.source,
                'content': log.content,
                'mark': log.mark,
                'device_id': log.device_id,
                'task_id': log.task_id,
                'test_case_id': log.test_case_id,
                'api_id': log.api_id,
                'thread_id': log.thread_id,
                'algorithm_type': log.algorithm_type,
                'created_at': log.created_at.isoformat() if log.created_at else None
            }
            log_date = (log.time or log.created_at or datetime.now(timezone(timedelta(hours=8)))).strftime('%Y-%m-%d')

            if log.task_id and log.test_case_id:
                key = (log.task_id, log.test_case_id, log_date)
                task_case_logs.setdefault(key, []).append(log_data)
            elif log.task_id:
                key = (log.task_id, log_date)
                task_only_logs.setdefault(key, []).append(log_data)
            elif log.test_case_id:
                key = (log.test_case_id, log_date)
                case_only_logs.setdefault(key, []).append(log_data)
            else:
                other_logs.setdefault(log_date, []).append(log_data)

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
        for (task_id, case_id, log_date), logs in task_case_logs.items():
            _save_archive(f'tasks/{task_id}/{case_id}/{log_date}.json', logs)
            archived_count += len(logs)
        for (task_id, log_date), logs in task_only_logs.items():
            _save_archive(f'tasks/{task_id}/{log_date}.json', logs)
            archived_count += len(logs)
        for (case_id, log_date), logs in case_only_logs.items():
            _save_archive(f'cases/{case_id}/{log_date}.json', logs)
            archived_count += len(logs)
        for log_date, logs in other_logs.items():
            _save_archive(f'other/{log_date}.json', logs)
            archived_count += len(logs)

        log_ids_to_delete = [log.id for log in old_logs]
        session.query(Log).filter(Log.id.in_(log_ids_to_delete)).delete(synchronize_session=False)
        session.commit()

        print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INFO - Archived {archived_count} logs to OSS (task+case: {len(task_case_logs)}, task: {len(task_only_logs)}, case: {len(case_only_logs)}, other: {len(other_logs)})")

        remaining_count = session.query(Log).count()
        if remaining_count > LOG_ARCHIVE_THRESHOLD:
            print(f"[{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}] - log_worker - INFO - Still {remaining_count} logs, will continue archiving next cycle.")

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
