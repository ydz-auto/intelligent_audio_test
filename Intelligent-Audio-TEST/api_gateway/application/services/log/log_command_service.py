"""日志命令 Service。

P0-3 DDD 改造：所有 Log 写操作（标记/清除/归档）通过 gRPC 调用 task_service，
不再直连 task_service DB。
"""
import json
from datetime import datetime, timedelta

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
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
            # P0-3: 通过 gRPC 批量更新日志标记
            from api_gateway.infrastructure.grpc_proxies import task_data_service
            result = task_data_service.update_logs_mark(log_ids=req.log_ids, mark=req.mark)
            return success_response(None, f"已为 {result.get('updated', 0)} 条日志添加标记: {req.mark}")
        except Exception as e:
            return error_response(str(e))

    # 清除日志
    @staticmethod
    def clear_logs():
        req = LogClearRequest.model_validate(request.get_json() or {})

        try:
            # P0-3: 通过 gRPC 批量清除日志
            from api_gateway.infrastructure.grpc_proxies import task_data_service
            result = task_data_service.clear_logs(
                before_datetime=req.before_datetime,
                keep_marked=req.keep_marked,
            )
            count = result.get('deleted', 0)
            return success_response({"deletedCount": count}, f"已成功清除 {count} 条历史日志")
        except Exception as e:
            return error_response(str(e))

    # 归档日志
    @staticmethod
    def archive_logs():
        req = LogArchiveRequest.model_validate(request.get_json() or {})

        try:
            # P0-3: 通过 gRPC 归档日志
            from api_gateway.infrastructure.grpc_proxies import task_data_service
            result = task_data_service.archive_logs(days=req.days, dry_run=req.dry_run)

            if req.dry_run:
                return success_response({
                    "message": f"将归档 {result.get('cold_logs_count', 0)} 条日志（{req.days}天前的数据）",
                    "cold_logs_count": result.get('cold_logs_count', 0),
                    "cutoff_date": result.get('cutoff_date', '')
                })

            archived_count = result.get('archived_count', 0)
            if archived_count == 0:
                return success_response(LogArchiveResult(
                    archived_count=0,
                    deleted_count=0,
                    archive_file=None,
                    remaining_count=result.get('remaining_count', 0)
                ), "没有需要归档的日志")

            # 将 gRPC 返回的分组写入 OSS
            groups = result.get('groups', {})

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

            # groups key 格式: 'task_case/{task_id}/{case_id}/{date}' etc.
            group_counts = {'task_case': 0, 'task': 0, 'case': 0, 'other': 0}
            for group_key, logs in groups.items():
                stored_path = f'archives/{group_key}.json'
                save_archive(stored_path, logs)
                prefix = group_key.split('/')[0]
                group_counts[prefix] = group_counts.get(prefix, 0) + 1

            return success_response(LogArchiveResult(
                archived_count=archived_count,
                deleted_count=result.get('deleted_count', 0),
                archive_file=None,
                remaining_count=result.get('remaining_count', 0)
            ), f"成功归档 {archived_count} 条日志 (任务用例: {group_counts.get('task_case', 0)}, 任务: {group_counts.get('task', 0)}, 用例: {group_counts.get('case', 0)}, 其他: {group_counts.get('other', 0)})")

        except Exception as e:
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
