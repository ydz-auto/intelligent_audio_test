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

            # INT-1812（契约 §Q2）：全局页（无 task_id）走「审计文件 + logs 表
            # 历史行」合并视图。审计事件已去库化落文件（logs/audit/{日期}/...），
            # DB 只剩改造前的历史行，两侧合并后内存分页；无时间筛选时默认近
            # LOG_AUDIT_QUERY_DEFAULT_DAYS(30) 天（唯一可见语义变化）。
            return LogQueryService._get_global_logs_merged(query)
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

    # ------------------------------------------------------------------
    # 全局维度日志（INT-1812，契约 §Q2）：审计文件 + DB 历史行合并
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_filter(value):
        """module/category/algorithm_type 的 'all' 归一为不过滤（INT-132 口径）。

        文件侧与 DB 侧、列表与统计共用同一份归一结果，缓存键因此可共享。
        """
        return None if not value or value == 'all' else value

    @staticmethod
    def _resolve_window(start_time, end_time):
        """默认时间窗（契约 §Q2）：既无 start_time 也无 end_time → 近 30 天。

        这是相对「DB 全表」唯一的可见语义变化：不传时间时「共 N 条」是
        「近 LOG_AUDIT_QUERY_DEFAULT_DAYS 天 N 条」。任一侧给了时间则原样使用。
        """
        if start_time or end_time:
            return start_time, end_time
        from shared.logging import AuditLogReader
        return AuditLogReader.default_window_start(), end_time

    @staticmethod
    def _audit_file_filters(*, level=None, category=None, module=None, keyword=None,
                            content_include=None, content_exclude=None,
                            algorithm_type=None, test_case_id=None, thread_id=None,
                            device_id=None, api_id=None, task_id=None, user_id=None,
                            mark=None, start_time=None, end_time=None) -> dict:
        """列表 / 统计 / 导出共用的审计文件过滤参数（键名与读取器同名）。"""
        return {
            'level': level,
            'category': LogQueryService._normalize_filter(category),
            'module': LogQueryService._normalize_filter(module),
            'keyword': keyword,
            'content_include': content_include,
            'content_exclude': content_exclude,
            'algorithm_type': LogQueryService._normalize_filter(algorithm_type),
            'test_case_id': test_case_id,
            'thread_id': thread_id,
            'device_id': device_id,
            'api_id': api_id,
            'task_id': task_id,
            'user_id': user_id,
            'mark': mark,
            'start_time': start_time,
            'end_time': end_time,
        }

    @staticmethod
    def _query_db_history(*, level=None, module=None, category=None, mark=None,
                          device_id=None, api_id=None, test_case_id=None,
                          thread_id=None, keyword=None, content_include=None,
                          content_exclude=None, algorithm_type=None, user_id=None,
                          start_time=None, end_time=None,
                          need_rows=0):
        """拉取 logs 表历史行（改造前的审计/任务日志，只读不迁移）。

        合并视图两侧各自有序，并集的前 `page*per_page` 条必然落在两侧各自的
        前 `page*per_page` 条里，因此 DB 侧只取这么多行（上限受
        LOG_DB_MERGE_MAX_ROWS 约束，0 = 不限），`total` 仍取 DB 的真实计数。

        DB 侧排序沿用 task_service ListLogs 现有口径（id 倒序，与改造前全局页
        分页同序，故相对基线不丢行）；主库实测 304,948 行里 time 与 id 逆序仅
        82 处、均为相邻 id 的 ±8h 时区标注差异。文件侧按 (time desc, cursor
        desc) 全量物化，与 DB 前缀合并后统一排序分页。
        返回 (条目列表, DB 侧命中总数)。
        """
        from api_gateway.infrastructure.grpc_proxies import task_data_service
        page_size = LogQueryService._db_merge_page_size()
        limit = page_size if page_size > 0 else _DB_PAGE_UNBOUNDED
        if need_rows and need_rows < limit:
            limit = max(1, need_rows)
        resp = task_data_service.list_logs(
            task_id=0,
            level=level or None,
            page=1,
            per_page=limit,
            start_date=start_time,
            end_date=end_time,
            module=module,
            category=category,
            mark=mark,
            device_id=device_id,
            api_id=api_id,
            test_case_id=test_case_id,
            thread_id=thread_id,
            keyword=keyword,
            content_include=content_include,
            content_exclude=content_exclude,
            algorithm_type=algorithm_type,
            user_id=user_id,
        )
        items = [_to_log_item(log) for log in (resp.get('items') or [])]
        return items, int(resp.get('total', 0) or 0)

    @staticmethod
    def _merge_sort_key(item):
        """合并视图排序键（时间倒序、游标/id 次之）。

        文件侧时间格式为 `YYYY-MM-DD HH:MM:SS.ffffff`（写入侧固定 strftime），
        legacy DB 行是 `datetime.isoformat()`（'T' 分隔）——直接按字符串比较
        会让同日 DB 行整体排到文件行之前（'T' > ' '），因此统一解析成 epoch
        再比。不可解析的时间视为最旧，保证不因脏值错序。
        """
        moment = None
        text = item.time or ''
        if text:
            try:
                moment = datetime.fromisoformat(text)
            except (ValueError, TypeError):
                moment = None
        if moment is None:
            return (float('-inf'), item.id or 0)
        if moment.tzinfo is not None:
            moment = moment.replace(tzinfo=None)
        return (moment.timestamp(), item.id or 0)

    @staticmethod
    def _get_global_logs_merged(query):
        from shared.logging import AuditLogReader

        start_time, end_time = LogQueryService._resolve_window(
            query.start_time, query.end_time)
        filters = LogQueryService._audit_file_filters(
            level=query.level,
            category=query.category,
            module=query.module,
            keyword=query.keyword,
            content_include=query.content_include,
            content_exclude=query.content_exclude,
            algorithm_type=query.algorithm_type,
            test_case_id=query.test_case_id,
            thread_id=query.thread_id,
            device_id=query.device_id,
            api_id=query.api_id,
            user_id=query.user_id,
            mark=query.mark,
            start_time=start_time,
            end_time=end_time,
        )
        file_result = AuditLogReader().read_page(page=1, per_page=0, **filters)
        file_items = [_to_log_item(entry) for entry in file_result['items']]

        per_page = max(1, int(query.per_page or 20))
        page = max(1, int(query.page or 1))
        db_items, db_total = LogQueryService._query_db_history(
            level=query.level,
            module=filters['module'],
            category=filters['category'],
            mark=query.mark,
            device_id=query.device_id,
            api_id=query.api_id,
            test_case_id=query.test_case_id,
            thread_id=query.thread_id,
            keyword=query.keyword,
            content_include=query.content_include,
            content_exclude=query.content_exclude,
            algorithm_type=filters['algorithm_type'],
            user_id=query.user_id,
            start_time=start_time,
            end_time=end_time,
            need_rows=page * per_page,
        )

        merged = sorted(
            file_items + db_items,
            key=LogQueryService._merge_sort_key,
            reverse=True,
        )
        # DB 侧 total 取自 SQL count（精确）；文件侧触顶
        # （LOG_AUDIT_MAX_SCAN_ENTRIES）时合并 total 为下界且保留最新
        total = db_total + file_result['total']
        start = (page - 1) * per_page
        return success_response(
            LogListData(
                items=merged[start:start + per_page],
                total=total,
                page=page,
                per_page=per_page,
                pages=(total + per_page - 1) // per_page if per_page else 1,
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

            # INT-1812：全局统计与全局列表同源同筛选（默认近 30 天窗口）
            start_time, end_time = (query.start_time, query.end_time)
            if not query.task_id:
                start_time, end_time = LogQueryService._resolve_window(
                    query.start_time, query.end_time)

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
                start_time=start_time,
                end_time=end_time,
                algorithm_type=query.algorithm_type if query.algorithm_type != 'all' else None,
                user_id=query.user_id,
            )

            # INT-81：任务维度统计叠加业务日志文件行（DB 侧只含审计/历史行）。
            # INT-806：「仅自己」时文件侧业务执行日志非用户操作 → 排除，统计口径
            # 与列表一致（徽章数不虚高）。
            if query.task_id:
                if not query.user_id:
                    stats_dict = LogQueryService._merge_file_stats(query, stats_dict)
            else:
                # INT-1812（契约 §Q2）：全局统计叠加审计文件行，与列表共享
                # 同一次文件扫描（同参 TTL 缓存），徽章数与列表 total 同口径。
                stats_dict = LogQueryService._merge_audit_stats(
                    query, stats_dict, start_time, end_time)

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

    @staticmethod
    def _merge_audit_stats(query, stats_dict, start_time, end_time):
        """按级别统计审计文件行，叠加到 DB 统计结果上（INT-1812 契约 §Q2）。

        过滤参数与全局列表完全一致 → 读取器同参 TTL 缓存命中，列表与统计
        共享同一次文件扫描（照 INT-100 口径）；触顶时各项同为下界。
        """
        from shared.logging import AuditLogReader

        reader = AuditLogReader()
        filters = LogQueryService._audit_file_filters(
            level=query.level,
            category=query.category,
            module=query.module,
            keyword=query.keyword,
            content_include=query.content_include,
            content_exclude=query.content_exclude,
            algorithm_type=query.algorithm_type,
            device_id=query.device_id,
            user_id=query.user_id,
            mark=query.mark,
            start_time=start_time,
            end_time=end_time,
        )
        file_stats = AuditLogReader.count_by_level(
            reader.read_entries(**filters))
        merged = dict(stats_dict or {})
        for key, value in file_stats.items():
            merged[key] = merged.get(key, 0) + value
        return merged

    # 刷新日志 (手动同步新日志)
    @staticmethod
    def refresh_logs():
        """增量刷新（INT-1812 契约 §Q4：游标 = 审计文件 cursor）。

        字段名一个不改（items/count/new_count/last_id/db_max_id/reset_required），
        `db_max_id` 语义改为 server_max_cursor（审计语料最大游标，无数据 0）。
        四类情形：last_id=0 只建基准；旧 id 空间（<CURSOR_FLOOR）或超出
        server_max → 空 + reset_required；正常 → 升序最多 100 条。
        """
        req = LogRefreshRequest.model_validate(request.get_json() or {})
        from shared.logging import CURSOR_FLOOR, AuditLogReader

        reader = AuditLogReader()
        server_max_cursor = reader.max_cursor()

        entries = []
        reset_required = False
        next_last_id = req.last_id
        if req.last_id == 0:
            # 尚未建立基准：只回基准游标，不返回条目、不带 reset_required
            next_last_id = server_max_cursor
        elif req.last_id < CURSOR_FLOOR or req.last_id > server_max_cursor:
            # DB 旧 id / 负数 / 超出 server_max（库被清、时钟回拨）：要求重置基准
            next_last_id = server_max_cursor
            reset_required = True
        else:
            entries = reader.read_after_cursor(req.last_id, limit=100)
            if entries:
                next_last_id = entries[-1]['id']

        data_list = [_to_log_item(entry) for entry in entries]

        payload = LogRefreshData(
            items=data_list,
            count=len(data_list),
            new_count=len(data_list),
            last_id=next_last_id,
        )
        payload_dict = payload.model_dump(exclude_none=True)
        payload_dict['db_max_id'] = server_max_cursor
        if reset_required:
            payload_dict['reset_required'] = True
        return success_response(payload_dict)

    # 导出日志
    @staticmethod
    def export_logs():
        import os
        from shared.logging import CURSOR_FLOOR, AuditLogReader
        # INT-274：导出条件走 POST body（doc/接口文档 6. 导出日志：log_ids + format），
        # 修复 GET 空 body 下 format 落默认 excel、log_ids 落 None 的静默失真；
        # level/module 从 body 或 query（GET 兼容）均可读取，body 优先。
        req = LogExportRequest.model_validate(request.get_json() or {})
        query = _parse_query_params(LogExportQuery)
        level = req.level or query.level
        module = req.module or query.module

        # INT-1812（契约 §Q2/§3.3）：导出与列表同源同筛选（审计文件 + legacy
        # DB 行），不分页、受扫描上界约束。log_ids 里的文件游标按日期目录反查，
        # legacy id（<CURSOR_FLOOR）仍走 DB 导出。
        reader = AuditLogReader()
        log_items = []
        if req.log_ids:
            file_cursors = [int(i) for i in req.log_ids
                            if int(i) >= CURSOR_FLOOR]
            legacy_ids = [int(i) for i in req.log_ids
                          if int(i) < CURSOR_FLOOR]
            if file_cursors:
                log_items.extend(
                    _to_log_item(entry)
                    for entry in reader.read_by_cursors(file_cursors))
            if legacy_ids:
                from api_gateway.infrastructure.grpc_proxies import task_data_service
                resp = task_data_service.get_logs_for_export(
                    log_ids=legacy_ids, level=level, module=module)
                log_items.extend(
                    _to_log_item(log) for log in (resp.get('items') or []))
        else:
            # 与全局列表**同一取数路径**：文件侧同过滤参数、DB 侧同 list_logs
            # （level 大小写不敏感、module 'all' 归一、默认 30 天窗口、扫描上界
            # 一致），因此「同筛选下导出条数与列表一致」由构造保证。
            start_time, end_time = LogQueryService._resolve_window(None, None)
            filters = LogQueryService._audit_file_filters(
                level=level, module=module,
                start_time=start_time, end_time=end_time)
            log_items.extend(
                _to_log_item(entry)
                for entry in reader.read_entries(**filters))
            db_items, _db_total = LogQueryService._query_db_history(
                level=level,
                module=filters['module'],
                start_time=start_time,
                end_time=end_time,
                need_rows=0,
            )
            log_items.extend(db_items)

        log_items.sort(key=LogQueryService._merge_sort_key, reverse=True)

        export_data = []
        for item in log_items:
            export_data.append({
                "ID": item.id,
                "Time": item.time or '',
                "Level": item.level or '',
                "Module": item.module or '',
                "Content": item.content or '',
                "Mark": item.mark or "",
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
