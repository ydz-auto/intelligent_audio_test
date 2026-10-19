"""日志查询 Service。

P0-3 DDD 改造：所有 Log 读/聚合统计查询通过 gRPC 调用 task_service，
不再直连 task_service DB。
"""
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi.responses import FileResponse

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from shared.infrastructure.config import BaseConfig
from shared.utils.log_handler import log_not_emit
from shared.utils.query_utils import now_cst
from shared.infrastructure.storage import storage
from api_gateway.schemas.log import (
    LogItem, LogListData, LogRefreshData, LogRefreshRequest,
    LogExportRequest, LogListQuery, LogStatsQuery, LogArchiveQuery, LogExportQuery,
)


def _parse_query_params(model_cls):
    """从 request.args 提取查询参数并通过 APIModel 校验"""
    params = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
    return model_cls.model_validate(params)


def _to_iso_utc(value):
    """datetime → ISO-8601 UTC 字符串（'Z' 后缀）；非 datetime / None 原样返回。

    INT-786：归档清单 archivedAt 对齐前端 LogArchiveItem（ISO 字符串）。
    本地模拟器可能返回 naive datetime（无 tzinfo），统一按 UTC 处理。
    """
    if value is None or isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace('+00:00', 'Z')


def _to_log_item(log: dict) -> LogItem:
    """dict（DB 行或业务文件条目）→ LogItem。

    INT-838：读侧响应补带操作人 user_id——DB 行取 created_by_user_id
    （_log_po_to_dict 输出），业务文件条目取 user_id（JSONL 行新字段）。
    """
    return LogItem(
        id=log.get('id'),
        time=log.get('time') or '',
        level=log.get('level') or '',
        category=log.get('category') or '',
        module=log.get('module') or '',
        source=log.get('source') or '',
        content=log.get('content') or '',
        mark=log.get('mark'),
        device_id=log.get('device_id'),
        task_id=log.get('task_id'),
        api_id=log.get('api_id'),
        test_case_id=log.get('test_case_id'),
        thread_id=log.get('thread_id'),
        algorithm_type=log.get('algorithm_type'),
        user_id=log.get('user_id', log.get('created_by_user_id')),
    )


# LOG_DB_MERGE_MAX_ROWS = 0（不限）时传给 gRPC per_page 的占位值（int32 上限）
_DB_PAGE_UNBOUNDED = 2 ** 31 - 1


class LogQueryService:
    """日志查询读侧 Service（CQRS Query Side）。

    承载 LogController 中所有只读查询方法，保持原有逻辑不变。
    """

    @staticmethod
    def _authorize_log_user(user_id):
        """INT-806 鉴权绑定：非空 user_id 与当前认证用户不一致 → 403 响应。

        current_operator_id() 返回 int，AUTH_MODE=off 无 token 时为 0（非真实
        用户）→ 一律放行，仅按「operator_id != 0 且 user_id != operator_id」
        判定；返回 None 表示通过。
        """
        if not user_id:
            return None
        from api_gateway.application.services.auth.management_common import current_operator_id
        from api_gateway.utils.error_codes import ErrorCode
        operator_id = current_operator_id()
        if operator_id != 0 and user_id != operator_id:
            return error_response('无权限查看他人日志',
                                  code=ErrorCode.FORBIDDEN, http_code=403)
        return None

    # 获取日志列表 (支持分页和高级过滤)
    @staticmethod
    def get_logs():
        try:
            query = _parse_query_params(LogListQuery)

            auth_err = LogQueryService._authorize_log_user(query.user_id)
            if auth_err:
                return auth_err

            # INT-81：带任务条件的查询走「业务日志文件 + DB 历史行」合并视图。
            # 业务日志已去库化落文件（logs/business/{task}/...），历史 logs 表
            # 数据保留只读，两侧按时间倒序合并后内存分页。
            if query.task_id:
                return LogQueryService._get_task_logs_merged(query)

            # INT-100：全部过滤条件（task_id/level 多级别/日期/module/category/
            # mark/device/api/case/thread/keyword/content/algorithm_type）下推
            # task_service DB 过滤，服务端分页，不再客户端二次过滤
            from api_gateway.infrastructure.grpc_proxies import task_data_service
            resp = task_data_service.list_logs(
                task_id=query.task_id,
                level=query.level or None,
                page=query.page,
                per_page=query.per_page,
                start_date=query.start_time,
                end_date=query.end_time,
                module=query.module,
                category=query.category,
                mark=query.mark,
                device_id=query.device_id,
                api_id=query.api_id,
                test_case_id=query.test_case_id,
                thread_id=query.thread_id,
                keyword=query.keyword,
                content_include=query.content_include,
                content_exclude=query.content_exclude,
                algorithm_type=query.algorithm_type,
                user_id=query.user_id,
            )
            logs = resp.get('items') or []
            total = resp.get('total', 0)

            data = [_to_log_item(log) for log in logs]

            # INT-297：分页信封统一为 {items, page, pages, per_page, total}
            return success_response(
                LogListData(
                    items=data,
                    total=total,
                    page=resp.get('page', query.page),
                    per_page=resp.get('per_page', query.per_page),
                    pages=resp.get('pages') or (
                        (total + query.per_page - 1) // query.per_page if query.per_page else 1),
                )
            )
        except Exception as e:
            log_not_emit('ERROR', 'log_controller', f'Error in get_logs: {str(e)}', category='system')
            import traceback
            traceback.print_exc()
            return error_response(f"获取日志失败: {str(e)}", code=500)

    # ------------------------------------------------------------------
    # 任务维度日志（INT-81）：业务文件 + DB 历史行合并
    # ------------------------------------------------------------------

    @staticmethod
    def _db_merge_page_size() -> int:
        """任务维度合并视图 DB 侧单次拉取行数上限（0 = 不限）。

        INT-100：替代硬编码 per_page=100000 全量拉取，大任务 DB 行拉取量
        有界且可配置；与文件侧 LOG_BUSINESS_MAX_SCAN_ENTRIES 同为下界语义
        兜底（超限时 total 为下界，保留最新行）。
        """
        try:
            return max(0, int(BaseConfig.LOG_DB_MERGE_MAX_ROWS))
        except (TypeError, ValueError):
            return 100_000

    @staticmethod
    def _get_task_logs_merged(query):
        # INT-132：module 'all' 在应用层归一为不过滤后统一下发文件侧与 DB
        # 侧，两侧语义一致且与 stats 调用点缓存键统一
        module_filter = query.module if query.module and query.module != 'all' else None

        from shared.logging import BusinessLogReader

        reader = BusinessLogReader()
        # INT-806：「仅自己」只显示用户操作产生的日志；文件侧业务执行日志无
        # 操作人属性、非用户操作 → 排除（短路不读文件，DB 侧按 user_id 过滤）
        if query.user_id:
            file_entries = []
        else:
            file_entries = reader.read_entries(
                task_id=query.task_id,
                device_id=query.device_id,
                api_id=query.api_id,
                evaluation_id=query.evaluation_id,
                round_value=query.round,
                level=query.level,
                category=query.category if query.category and query.category != 'all' else None,
                module=module_filter,
                keyword=query.keyword,
                content_include=query.content_include,
                content_exclude=query.content_exclude,
                algorithm_type=query.algorithm_type,
                test_case_id=query.test_case_id,
                start_time=query.start_time,
                end_time=query.end_time,
            )
        file_items = [_to_log_item(entry) for entry in file_entries]

        # DB 历史行（审计事件与改造前任务日志，保留只读不迁移）。
        # INT-100：level 多级别/日期/其余条件全部下推 task_service 过滤，
        # 拉取行数受 LOG_DB_MERGE_MAX_ROWS 上限约束，不再全量物化。
        from api_gateway.infrastructure.grpc_proxies import task_data_service
        page_size = LogQueryService._db_merge_page_size()
        resp = task_data_service.list_logs(
            task_id=query.task_id,
            level=query.level or None,
            page=1,
            per_page=page_size if page_size > 0 else _DB_PAGE_UNBOUNDED,
            start_date=query.start_time,
            end_date=query.end_time,
            module=module_filter,
            category=query.category,
            mark=query.mark,
            device_id=query.device_id,
            api_id=query.api_id,
            test_case_id=query.test_case_id,
            thread_id=query.thread_id,
            keyword=query.keyword,
            content_include=query.content_include,
            content_exclude=query.content_exclude,
            algorithm_type=query.algorithm_type,
            user_id=query.user_id,
        )
        db_items = [_to_log_item(log) for log in (resp.get('items') or [])]

        merged = sorted(
            file_items + db_items,
            key=lambda item: item.time or '',
            reverse=True,
        )
        total = len(merged)
        start = (query.page - 1) * query.per_page
        page_items = merged[start:start + query.per_page]

        return success_response(
            LogListData(
                items=page_items,
                total=total,
                page=query.page,
                per_page=query.per_page,
                pages=(total + query.per_page - 1) // query.per_page if query.per_page else 1,
            )
        )

    # 获取日志统计
    @staticmethod
    def get_stats():
        try:
            query = _parse_query_params(LogStatsQuery)

            auth_err = LogQueryService._authorize_log_user(query.user_id)
            if auth_err:
                return auth_err

            # P0-3: 通过 gRPC 聚合查询日志统计
            from api_gateway.infrastructure.grpc_proxies import task_data_service
            from api_gateway.schemas.log import LogStatsData
            stats_dict = task_data_service.get_log_stats(
                level=query.level,
                module=query.module if query.module != 'all' else None,
                category=query.category if query.category != 'all' else None,
                mark=query.mark,
                device_id=query.device_id,
                task_id=query.task_id,
                keyword=query.keyword,
                content_include=query.content_include,
                content_exclude=query.content_exclude,
                start_time=query.start_time,
                end_time=query.end_time,
                algorithm_type=query.algorithm_type if query.algorithm_type != 'all' else None,
                user_id=query.user_id,
            )

            # INT-81：任务维度统计叠加业务日志文件行（DB 侧只含审计/历史行）。
            # INT-806：「仅自己」时文件侧业务执行日志非用户操作 → 排除，统计口径
            # 与列表一致（徽章数不虚高）。
            if query.task_id and not query.user_id:
                stats_dict = LogQueryService._merge_file_stats(query, stats_dict)

            log_stats = LogStatsData(
                total=stats_dict.get('total', 0),
                debug=stats_dict.get('debug', 0),
                info=stats_dict.get('info', 0),
                warning=stats_dict.get('warning', 0),
                error=stats_dict.get('error', 0),
                critical=stats_dict.get('critical', 0)
            )

            return success_response(log_stats)
        except Exception as e:
            log_not_emit('ERROR', 'log_controller', f'Error in get_stats: {str(e)}', category='system')
            import traceback
            traceback.print_exc()
            return error_response(f"获取日志统计失败: {str(e)}", code=500)

    @staticmethod
    def _merge_file_stats(query, stats_dict):
        """按级别统计业务日志文件行，叠加到 DB 统计结果上。"""
        from shared.logging import BusinessLogReader

        reader = BusinessLogReader()
        entries = reader.read_entries(
            task_id=query.task_id,
            device_id=query.device_id,
            evaluation_id=query.evaluation_id,
            round_value=query.round,
            level=query.level,
            category=query.category if query.category and query.category != 'all' else None,
            module=query.module if query.module != 'all' else None,
            keyword=query.keyword,
            content_include=query.content_include,
            content_exclude=query.content_exclude,
            algorithm_type=query.algorithm_type if query.algorithm_type != 'all' else None,
            start_time=query.start_time,
            end_time=query.end_time,
        )
        merged = dict(stats_dict or {})
        for entry in entries:
            level_key = (entry.get('level') or 'info').lower()
            merged[level_key] = merged.get(level_key, 0) + 1
            merged['total'] = merged.get('total', 0) + 1
        return merged

    # 刷新日志 (手动同步新日志)
    @staticmethod
    def refresh_logs():
        req = LogRefreshRequest.model_validate(request.get_json() or {})
        # P0-3: 通过 gRPC 增量查询日志
        from api_gateway.infrastructure.grpc_proxies import task_data_service
        resp = task_data_service.list_logs_after_id(last_id=req.last_id, limit=100)
        new_logs = resp.get('items', [])
        db_max_id = resp.get('max_id', 0)

        data_list = []
        for log in new_logs:
            data_list.append(
                LogItem(
                    id=log.get('id'),
                    time=log.get('time') or '',
                    level=log.get('level') or '',
                    category=log.get('category') or '',
                    module=log.get('module') or '',
                    source=log.get('source') or '',
                    content=log.get('content') or '',
                    mark=log.get('mark'),
                    device_id=log.get('device_id'),
                    task_id=log.get('task_id'),
                    api_id=log.get('api_id'),
                    test_case_id=log.get('test_case_id'),
                    thread_id=log.get('thread_id'),
                    algorithm_type=log.get('algorithm_type'),
                    user_id=log.get('created_by_user_id'),
                )
            )

        # 将 db_max_id / reset_required 放入 data，前端据此判断是否需要重置增量基准
        payload = LogRefreshData(
            items=data_list,
            count=len(data_list),
            new_count=len(data_list),
            last_id=data_list[-1].id if data_list else req.last_id,
        )
        payload_dict = payload.model_dump(exclude_none=True)
        payload_dict['db_max_id'] = db_max_id
        if req.last_id > db_max_id:
            payload_dict['reset_required'] = True
        return success_response(payload_dict)

    # 导出日志
    @staticmethod
    def export_logs():
        import os
        req = LogExportRequest.model_validate(request.get_json() or {})
        query = _parse_query_params(LogExportQuery)

        # P0-3: 通过 gRPC 查询日志（按 id 列表或条件）
        from api_gateway.infrastructure.grpc_proxies import task_data_service
        resp = task_data_service.get_logs_for_export(
            log_ids=req.log_ids if req.log_ids else None,
            level=query.level,
            module=query.module,
        )
        logs = resp.get('items', [])

        export_data = []
        for log in logs:
            export_data.append({
                "ID": log.get('id'),
                "Time": log.get('time') or '',
                "Level": log.get('level') or '',
                "Module": log.get('module') or '',
                "Content": log.get('content') or '',
                "Mark": log.get('mark') or ""
            })

        df = pd.DataFrame(export_data)
        export_dir = os.path.join(os.getcwd(), 'exports')
        if not os.path.exists(export_dir):
            os.makedirs(export_dir)

        filename = f"logs_export_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        file_path = ""

        if req.format == 'csv':
            file_path = os.path.join(export_dir, f"{filename}.csv")
            df.to_csv(file_path, index=False)
        elif req.format == 'json':
            file_path = os.path.join(export_dir, f"{filename}.json")
            df.to_json(file_path, orient='records', indent=4)
        elif req.format == 'txt':
            file_path = os.path.join(export_dir, f"{filename}.txt")
            with open(file_path, 'w', encoding='utf-8') as f:
                for item in export_data:
                    f.write(f"[{item['Time']}] {item['Level']} {item['Module']}: {item['Content']}\n")
        else: # Default Excel
            file_path = os.path.join(export_dir, f"{filename}.xlsx")
            df.to_excel(file_path, index=False)

        return FileResponse(file_path, headers={"Content-Disposition": "attachment"})

    # 获取归档状态
    @staticmethod
    def get_archive_status():
        try:
            # OSS: 列出 archives bucket 下各前缀的文件数
            task_keys = storage.list_objects('archives', prefix='tasks/')
            case_keys = storage.list_objects('archives', prefix='cases/')
            other_keys = storage.list_objects('archives', prefix='other/')

            task_count = len([k for k in task_keys if k.endswith('.json')])
            case_count = len([k for k in case_keys if k.endswith('.json')])
            other_count = len([k for k in other_keys if k.endswith('.json')])

            # P0-3: 通过 gRPC 查询日志总数
            from api_gateway.infrastructure.grpc_proxies import task_data_service
            cutoff_date = now_cst() - timedelta(days=7)
            result = task_data_service.get_log_count(start_date=cutoff_date.isoformat())
            total_logs = result.get('total', 0)
            hot_logs = result.get('hot', 0)
            cold_logs = result.get('cold', 0)

            return success_response({
                "totalLogs": total_logs,
                "hotLogs": hot_logs,
                "coldLogs": cold_logs,
                "archiveDir": "oss://archives",
                "taskArchives": task_count,
                "caseArchives": case_count,
                "otherArchives": other_count
            })
        except Exception as e:
            return error_response(f"获取归档状态失败: {str(e)}", code=500)

    # 获取归档日志
    @staticmethod
    def get_archived_logs():
        query = _parse_query_params(LogArchiveQuery)

        # INT-786：无 task_id / test_case_id → 全局归档文件清单（manifest），可分页
        if not query.task_id and not query.test_case_id:
            return LogQueryService._get_archive_manifest(query)

        try:
            logs = []

            def load_oss_json_files(prefix):
                """从存储 archives 类目读取指定前缀下所有 JSON 文件"""
                result = []
                keys = storage.list_objects('archives', prefix=prefix)
                for key in keys:
                    if not key.endswith('.json'):
                        continue
                    try:
                        data = storage.load_bytes(f'archives/{key}')
                        result.extend(json.loads(data))
                    except Exception:
                        continue
                return result

            if query.task_id:
                if query.test_case_id:
                    # tasks/{task_id}/{case_id}/*.json
                    prefix = f'tasks/{query.task_id}/{query.test_case_id}/'
                    logs.extend(load_oss_json_files(prefix))
                else:
                    # tasks/{task_id}/*.json + tasks/{task_id}/*/*.json
                    prefix = f'tasks/{query.task_id}/'
                    keys = storage.list_objects('archives', prefix=prefix)
                    for key in keys:
                        if not key.endswith('.json'):
                            continue
                        try:
                            data = storage.load_bytes(f'archives/{key}')
                            logs.extend(json.loads(data))
                        except Exception:
                            continue

            if query.test_case_id and not query.task_id:
                prefix = f'cases/{query.test_case_id}/'
                logs.extend(load_oss_json_files(prefix))

            logs.sort(key=lambda x: x.get('time', '') or '', reverse=True)

            items = []
            for log in logs:
                items.append(LogItem(
                    id=log.get('id', 0),
                    time=log.get('time', ''),
                    level=log.get('level', ''),
                    category=log.get('category', ''),
                    module=log.get('module', ''),
                    source=log.get('source', ''),
                    content=log.get('content', ''),
                    mark=log.get('mark'),
                    device_id=log.get('device_id'),
                    task_id=log.get('task_id'),
                    api_id=log.get('api_id'),
                    test_case_id=log.get('test_case_id'),
                    thread_id=log.get('thread_id'),
                    algorithm_type=log.get('algorithm_type'),
                    user_id=log.get('created_by_user_id'),
                ))

            return success_response({
                "items": items,
                "total": len(items),
                "source": "archive"
            })
        except Exception as e:
            return error_response(f"获取归档日志失败: {str(e)}", code=500)

    # 全局归档文件清单（无 task_id / test_case_id，INT-786）
    @staticmethod
    def _get_archive_manifest(query):
        """返回 archives 类目下全部 .json 归档文件的全局清单（可分页）。

        INT-780 契约裁定：
        1. filename = 归档逻辑 key 完整路径（如 tasks/123/2026-10-18.json），行 key 唯一；
        2. 响应 {items:[{filename, sizeBytes, archivedAt}], total}（camelCase raw dict）；
        4. sizeBytes 取对象 Size，archivedAt 取 LastModified（UTC ISO 'Z' 后缀）。
        """
        try:
            objects = storage.list_objects_with_meta('archives')
            files = [o for o in objects if o.get('key', '').endswith('.json')]
            files.sort(key=lambda o: o.get('key', ''), reverse=True)

            total = len(files)
            page = query.page or 1
            per_page = query.per_page or 50
            start = (page - 1) * per_page
            end = start + per_page

            items = [
                {
                    "filename": o['key'],
                    "sizeBytes": o.get('sizeBytes', 0),
                    "archivedAt": _to_iso_utc(o.get('lastModified')),
                }
                for o in files[start:end]
            ]
            return success_response({
                "items": items,
                "total": total,
            })
        except Exception as e:
            return error_response(f"获取归档文件清单失败: {str(e)}", code=500)

    # 下载归档文件
    @staticmethod
    def download_archive(filename):
        try:
            # OSS: 在 archives bucket 中搜索匹配的文件
            all_keys = storage.list_objects('archives')
            matching_keys = [k for k in all_keys if k.endswith(f'/{filename}') or k == filename]

            if not matching_keys:
                return error_response("归档文件不存在", code=404)

            # 下载到临时文件再返回。用 load_bytes 写入已打开的句柄后立即关闭，
            # 避免 NamedTemporaryFile 句柄未关闭时再落盘同一路径触发
            # Windows WinError 32（文件占用）（INT-554）。
            import tempfile
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
            try:
                tmp.write(storage.load_bytes(f'archives/{matching_keys[0]}'))
            finally:
                tmp.close()
            return FileResponse(tmp.name, headers={"Content-Disposition": f"attachment; filename={filename}"})
        except Exception as e:
            return error_response(f"下载失败: {str(e)}", code=500)
