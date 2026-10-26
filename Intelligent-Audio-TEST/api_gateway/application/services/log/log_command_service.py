"""日志命令 Service。

P0-3 DDD 改造：所有 Log 写操作（标记/清除/归档）通过 gRPC 调用 task_service，
不再直连 task_service DB。
"""
from datetime import datetime, timedelta

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from shared.infrastructure.config import BaseConfig
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
            # INT-1812（契约 §Q3）：审计文件日志只读、不可标记——游标（>=CURSOR_FLOOR）
            # 不属于 logs 表 id 空间，不送 DB 更新；全部为文件游标时返回 200 + updated=0
            # 与专用文案（不 400/500、不空态回退，前端只读状态码未受影响）。
            from shared.logging import CURSOR_FLOOR
            file_cursors = [int(i) for i in req.log_ids if int(i) >= CURSOR_FLOOR]
            legacy_ids = [int(i) for i in req.log_ids if int(i) < CURSOR_FLOOR]

            updated = 0
            if legacy_ids:
                # P0-3: 通过 gRPC 批量更新日志标记（仅 legacy DB 行）
                from api_gateway.infrastructure.grpc_proxies import task_data_service
                result = task_data_service.update_logs_mark(
                    log_ids=legacy_ids, mark=req.mark)
                updated = result.get('updated', 0)

            # INT-1903：契约 §Q2 承诺 `updated` = 实际更新行数（文件游标 → 0），
            # 三条分支都要带在 data 里（此前两处传 None，响应体里连 data 都没有）。
            if updated == 0 and file_cursors and not legacy_ids:
                return success_response(
                    {"updated": updated}, "所选为文件日志，不支持标记（仅历史库行可标记）")
            return success_response(
                {"updated": updated}, f"已为 {updated} 条日志添加标记: {req.mark}")
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

            if req.dry_run:
                result = task_data_service.archive_logs(days=req.days, dry_run=True)
                return success_response({
                    "message": f"将归档 {result.get('cold_logs_count', 0)} 条日志（{req.days}天前的数据）",
                    "cold_logs_count": result.get('cold_logs_count', 0),
                    "cutoff_date": result.get('cutoff_date', '')
                })

            # INT-1963：task_service 每次只推进一批（取批 → 写归档 → 成功才删该批），
            # 响应只含计数；这里按 has_more 循环推进，单轮批数受
            # LOG_ARCHIVE_MAX_BATCHES_PER_RUN 限制，剩余冷日志由 log_worker 巡检继续。
            try:
                max_batches = max(1, int(
                    getattr(BaseConfig, 'LOG_ARCHIVE_MAX_BATCHES_PER_RUN', 50) or 50))
            except (TypeError, ValueError):
                max_batches = 50

            archived_count = 0
            deleted_count = 0
            remaining_count = 0
            batches = 0
            capped = False
            while True:
                result = task_data_service.archive_logs(days=req.days, dry_run=False)
                batches += 1
                batch_archived = int(result.get('archived_count', 0) or 0)
                archived_count += batch_archived
                deleted_count += int(result.get('deleted_count', 0) or 0)
                remaining_count = int(result.get('remaining_count', 0) or 0)
                # 无进展立即停（防空转）；has_more=False 表示冷日志已归档完
                if batch_archived == 0 or not result.get('has_more'):
                    break
                if batches >= max_batches:
                    capped = True
                    break

            if archived_count == 0:
                return success_response(LogArchiveResult(
                    archived_count=0,
                    deleted_count=0,
                    archive_file=None,
                    remaining_count=remaining_count
                ), "没有需要归档的日志")

            message = f"成功归档 {archived_count} 条日志（{batches} 批）"
            if capped:
                message += "，剩余冷日志将随后台巡检继续归档"
            return success_response(LogArchiveResult(
                archived_count=archived_count,
                deleted_count=deleted_count,
                archive_file=None,
                remaining_count=remaining_count
            ), message)

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
