import json
from datetime import datetime, timedelta

from sqlalchemy import func, or_

from api_gateway.infrastructure.request_adapter import request
from shared.models.models import Log
from shared.models.database import db
from shared.utils.response import success_response, error_response
from shared.utils.query_utils import now_cst
from shared.infrastructure.storage import storage
from api_gateway.schemas.log import (
    LogMarkRequest, LogClearRequest, LogArchiveRequest, LogArchiveResult,
)


class LogCommandService:
    """日志写操作 Service（CQRS Command Side）。

    承载 LogController 中所有写操作方法（标记/清除/归档/删除归档），保持原有逻辑不变。
    """

    # 标记日志
    @staticmethod
    def mark_logs():
        req = LogMarkRequest.model_validate(request.get_json())
        if not req.log_ids:
            return error_response("缺少必要参数: log_ids")

        try:
            Log.query.filter(Log.id.in_(req.log_ids)).update({"mark": req.mark}, synchronize_session=False)
            db.session.commit()
            return success_response(None, f"已为 {len(req.log_ids)} 条日志添加标记: {req.mark}")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 清除日志
    @staticmethod
    def clear_logs():
        req = LogClearRequest.model_validate(request.get_json() or {})

        try:
            query = Log.query
            if req.before_datetime:
                query = query.filter(Log.time < datetime.fromisoformat(req.before_datetime))

            if req.keep_marked:
                query = query.filter(or_(Log.mark.is_(None), Log.mark == ''))

            count = query.delete(synchronize_session=False)
            db.session.commit()
            return success_response({"deletedCount": count}, f"已成功清除 {count} 条历史日志")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 归档日志
    @staticmethod
    def archive_logs():
        req = LogArchiveRequest.model_validate(request.get_json() or {})

        try:
            cutoff_date = now_cst() - timedelta(days=req.days)

            cold_logs_query = Log.query.filter(Log.time < cutoff_date)
            cold_count = cold_logs_query.count()

            if req.dry_run:
                return success_response({
                    "message": f"将归档 {cold_count} 条日志（{req.days}天前的数据）",
                    "cold_logs_count": cold_count,
                    "cutoff_date": cutoff_date.isoformat()
                })

            if cold_count == 0:
                return success_response(LogArchiveResult(
                    archived_count=0,
                    deleted_count=0,
                    archive_file=None,
                    remaining_count=db.session.query(func.count(Log.id)).scalar() or 0
                ), "没有需要归档的日志")

            # OSS: 归档到 archives bucket
            # 结构: tasks/{task_id}/{case_id}/{date}.json
            #       tasks/{task_id}/{date}.json
            #       cases/{case_id}/{date}.json
            #       other/{date}.json

            cold_logs = cold_logs_query.order_by(Log.time.asc()).all()

            task_case_logs = {}
            task_only_logs = {}
            case_only_logs = {}
            other_logs = {}

            for log in cold_logs:
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

                log_date = (log.time or log.created_at or datetime.now()).strftime('%Y-%m-%d')

                if log.task_id and log.test_case_id:
                    key = (log.task_id, log.test_case_id, log_date)
                    if key not in task_case_logs:
                        task_case_logs[key] = []
                    task_case_logs[key].append(log_data)
                elif log.task_id:
                    key = (log.task_id, log_date)
                    if key not in task_only_logs:
                        task_only_logs[key] = []
                    task_only_logs[key].append(log_data)
                elif log.test_case_id:
                    key = (log.test_case_id, log_date)
                    if key not in case_only_logs:
                        case_only_logs[key] = []
                    case_only_logs[key].append(log_data)
                else:
                    if log_date not in other_logs:
                        other_logs[log_date] = []
                    other_logs[log_date].append(log_data)

            archived_count = 0

            def save_archive(stored_path, logs):
                """上传归档到存储（合并已存在的）"""
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

            for (task_id, case_id, log_date), logs in task_case_logs.items():
                stored_path = f'archives/tasks/{task_id}/{case_id}/{log_date}.json'
                save_archive(stored_path, logs)
                archived_count += len(logs)

            for (task_id, log_date), logs in task_only_logs.items():
                stored_path = f'archives/tasks/{task_id}/{log_date}.json'
                save_archive(stored_path, logs)
                archived_count += len(logs)

            for (case_id, log_date), logs in case_only_logs.items():
                stored_path = f'archives/cases/{case_id}/{log_date}.json'
                save_archive(stored_path, logs)
                archived_count += len(logs)

            for log_date, logs in other_logs.items():
                stored_path = f'archives/other/{log_date}.json'
                save_archive(stored_path, logs)
                archived_count += len(logs)

            log_ids = [log.id for log in cold_logs]
            Log.query.filter(Log.id.in_(log_ids)).delete(synchronize_session=False)
            db.session.commit()

            remaining_count = db.session.query(func.count(Log.id)).scalar() or 0

            return success_response(LogArchiveResult(
                archived_count=archived_count,
                deleted_count=len(log_ids),
                archive_file=None,
                remaining_count=remaining_count
            ), f"成功归档 {archived_count} 条日志 (任务用例: {len(task_case_logs)}, 任务: {len(task_only_logs)}, 用例: {len(case_only_logs)}, 其他: {len(other_logs)})")

        except Exception as e:
            db.session.rollback()
            return error_response(f"归档失败: {str(e)}", code=500)

    # 删除归档文件
    @staticmethod
    def delete_archive(filename):
        try:
            # OSS: 在 archives bucket 中搜索并删除
            all_keys = storage.list_objects('archives')
            matching_keys = [k for k in all_keys if k.endswith(f'/{filename}') or k == filename]

            if not matching_keys:
                return error_response("归档文件不存在", code=404)

            storage.delete(f'archives/{matching_keys[0]}')
            return success_response(None, f"已删除归档文件: {filename}")
        except Exception as e:
            return error_response(f"删除失败: {str(e)}", code=500)
