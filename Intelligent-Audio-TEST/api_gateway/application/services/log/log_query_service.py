"""日志查询 Service。

P0-3 DDD 改造：所有 Log 读/聚合统计查询通过 gRPC 调用 task_service，
不再直连 task_service DB。
"""
import csv
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi.responses import FileResponse

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
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


# 导出产物的列顺序（csv / xlsx 表头与 json 键，两前端导出弹窗口径不变）
_EXPORT_COLUMNS = ['ID', 'Time', 'Level', 'Module', 'Content', 'Mark']


def _to_export_row(log: dict) -> tuple:
    """导出行（紧凑元组，与 _EXPORT_COLUMNS 一一对应）。

    INT-1812 返工：导出可能命中 30 万级行，用元组而不是 LogItem / 字典列表，
    避免把整个结果集物化成 pydantic 模型（实测 30 万行 LogItem 峰值 +1GB）。
    """
    return (
        log.get('id'),
        log.get('time') or '',
        log.get('level') or '',
        log.get('module') or '',
        log.get('content') or '',
        log.get('mark') or '',
    )


def _parse_log_time(text):
    """日志时间文本 → epoch 秒；不可解析返回 -inf（视为最旧）。

    文件侧时间格式为 `YYYY-MM-DD HH:MM:SS.ffffff`（写入侧固定 strftime），
    legacy DB 行是 `datetime.isoformat()`（'T' 分隔）——直接按字符串比较会让
    同日 DB 行整体排到文件行之前（'T' > ' '），因此统一解析成 epoch 再比。
    """
    if not text:
        return float('-inf')
    try:
        moment = datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return float('-inf')
    if moment.tzinfo is not None:
        moment = moment.replace(tzinfo=None)
    return moment.timestamp()


class _ExportTooManyRows(Exception):
    """导出命中行数超过 LOG_DB_EXPORT_MAX_ROWS：显式报错，不静默截断成部分数据。"""

    def __init__(self, hit, limit):
        super().__init__(
            f'导出命中 {hit} 行，超过上限 {limit} 行，请缩小时间范围或增加筛选条件')
        self.hit = hit
        self.limit = limit


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
        # INT-1812 返工：改按块循环拉取，单次响应不再越过 gRPC 64MB 上限。
        db_items, _db_total = LogQueryService._query_db_history(
            task_id=query.task_id,
            level=query.level,
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
            start_time=query.start_time,
            end_time=query.end_time,
            need_rows=LogQueryService._db_merge_page_size(),
        )

        # INT-1946：与全局视图同用 `_merge_sort_key`（time desc, id desc）。
        # 原按 time 字符串排序：DB 行是 isoformat（'T' 分隔）、文件行是空格
        # 分隔，同日行会整体错序；且 DB 侧前缀口径与合并侧不同序会导致
        # LOG_DB_MERGE_MAX_ROWS 触顶时保留的不是「最近时间」的行。
        merged = sorted(
            file_items + db_items,
            key=LogQueryService._merge_sort_key,
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
    def _db_fetch_chunk_rows() -> int:
        """单块 ListLogs 拉取行数（INT-1812 返工）。

        ListLogs 响应是单条 JSON 字符串（实测 2~3.5KB/行），一次要 10 万行约
        160MB 必撞 gRPC 单条消息上限（客户端 GRPC_MAX_MESSAGE_MB=64MB、服务端
        send 64MB），代理再把 RESOURCE_EXHAUSTED 吞成空结果 → 导出丢光 DB 行、
        深分页 total 塌成文件侧。块大小默认 5000 行（约 12~18MB，留 3 倍余量）。
        """
        try:
            return max(1, int(BaseConfig.LOG_DB_FETCH_CHUNK_ROWS))
        except (TypeError, ValueError):
            return 5000

    @staticmethod
    def _db_export_max_rows() -> int:
        """导出 DB 侧命中行数上限（0 = 不限）。"""
        try:
            return max(0, int(BaseConfig.LOG_DB_EXPORT_MAX_ROWS))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _fetch_db_rows(*, task_id=0, level=None, module=None, category=None,
                       mark=None, device_id=None, api_id=None, test_case_id=None,
                       thread_id=None, keyword=None, content_include=None,
                       content_exclude=None, algorithm_type=None, user_id=None,
                       start_time=None, end_time=None, need_rows=0,
                       convert=None, max_total=0):
        """按块循环拉取 logs 表历史行（只读），返回 (行, DB 侧命中总数)。

        need_rows > 0：最多取 min(need_rows, LOG_DB_MERGE_MAX_ROWS) 行——合并
        视图两侧各自有序，并集前 N 条必然落在两侧各自的前 N 条里，故 DB 侧只
        取并集前缀；配置为 0（不限）时取 need_rows。need_rows = 0：全部命中行
        （导出，与列表 total 同口径）。

        前缀语义的前提是 DB 侧与合并侧同全序：task_service ListLogs 现按
        (time desc, id desc) 返回（INT-1946 前只按 id 倒序，与合并侧 time 倒序
        不同序，前缀取不到「id 大而 time 早」的行 → 每页尾部重复、页间漏行）。

        分块：每块 ≤ LOG_DB_FETCH_CHUNK_ROWS 行，page/per_page 按已取行数对齐，
        单块响应不会越过 gRPC 单条消息上限。

        total 取自首个响应（SQL count，精确），任何一块失败都直接抛出——读侧
        不得把失败吞成空结果，否则「拿不到数据」会被伪装成「共 0 条」。
        convert：逐行转换钩子（导出用紧凑行，避免 30 万级 LogItem 物化）。
        max_total > 0 且命中总数超过它 → 抛 _ExportTooManyRows（显式报错）。
        """
        from api_gateway.infrastructure.grpc_proxies import task_data_service

        cap = LogQueryService._db_merge_page_size()
        if need_rows and need_rows > 0:
            target = min(need_rows, cap) if cap > 0 else need_rows
        else:
            target = None                      # 不限（导出 / 配置为 0）

        chunk = LogQueryService._db_fetch_chunk_rows()
        # 每页行数按目标取小：小块目标（如首页 page*per_page=20）仍是一次小请求，
        # 只有真正要大量行时才按块循环；页号与已取行数对齐，不重不漏。
        per_page = chunk if target is None else min(chunk, target)
        rows = []
        total = None
        while target is None or len(rows) < target:
            page = len(rows) // per_page + 1
            resp = task_data_service.list_logs(
                task_id=task_id,
                level=level or None,
                page=page,
                per_page=per_page,
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
                reraise=True,
            )
            raw_items = resp.get('items') or []
            if total is None:
                total = int(resp.get('total', 0) or 0)
                if max_total and total > max_total:
                    raise _ExportTooManyRows(total, max_total)
            items = raw_items if target is None else raw_items[:target - len(rows)]
            rows.extend([convert(item) for item in items] if convert else items)
            # 本块不足一整页 = 已到末尾；取满命中总数同样结束
            if len(raw_items) < per_page or len(rows) >= total:
                break
        return rows, int(total or 0)

    @staticmethod
    def _query_db_history(*, task_id=0, level=None, module=None, category=None,
                          mark=None, device_id=None, api_id=None, test_case_id=None,
                          thread_id=None, keyword=None, content_include=None,
                          content_exclude=None, algorithm_type=None, user_id=None,
                          start_time=None, end_time=None, need_rows=0):
        """拉取 logs 表历史行并转成 LogItem（改造前的审计/任务日志，只读不迁移）。

        DB 侧排序 = task_service ListLogs 口径 (time desc, id desc)，与合并侧
        `_merge_sort_key` 同全序（INT-1946 前是仅 id 倒序，两者不同序会让合并
        视图的前缀取行漏行、页间重复）；文件侧按 (time desc, cursor desc) 全量
        物化，与 DB 前缀合并后统一排序分页。
        返回 (LogItem 列表, DB 侧命中总数)。
        """
        return LogQueryService._fetch_db_rows(
            task_id=task_id, level=level, module=module, category=category,
            mark=mark, device_id=device_id, api_id=api_id,
            test_case_id=test_case_id, thread_id=thread_id, keyword=keyword,
            content_include=content_include, content_exclude=content_exclude,
            algorithm_type=algorithm_type, user_id=user_id,
            start_time=start_time, end_time=end_time, need_rows=need_rows,
            convert=_to_log_item,
        )

    @staticmethod
    def _merge_sort_key(item):
        """合并视图排序键（时间倒序、游标/id 次之；时间解析见 _parse_log_time）。"""
        return (_parse_log_time(item.time), item.id or 0)

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
        file_total = file_result['total']
        # INT-1812 返工 2：合并视图 DB 侧最多物化前 LOG_DB_MERGE_MAX_ROWS 行
        # （cap，0 = 不限）。DB 命中数超过 cap 时，合并结果最多只有
        # cap + 文件命中数 行——total/pages 必须对**所有页**统一收敛到这个
        # 下界（契约 §Q2「触顶时 total 为下界」），否则首页承诺的页数永远翻
        # 不到、越过前缀的深页返回空表（「共 6,108 页、只有前 5,000 页有数据」）。
        cap = LogQueryService._db_merge_page_size()

        def _view_total(raw_db_total):
            if cap > 0 and raw_db_total > cap:
                return cap + file_total
            return raw_db_total + file_total

        db_kwargs = dict(
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
        )

        # 页号已越过可物化的合并前缀：一个必然为空的越界页不必把 10 万行前缀
        # 全拉一遍，只需一次小请求拿 DB 精确 total 来收敛下界。
        if cap > 0 and (page - 1) * per_page >= cap + file_total:
            _rows, raw_db_total = LogQueryService._query_db_history(
                need_rows=1, **db_kwargs)
            out_total = _view_total(raw_db_total)
            return success_response(
                LogListData(
                    items=[],
                    total=out_total,
                    page=page,
                    per_page=per_page,
                    pages=(out_total + per_page - 1) // per_page if per_page else 1,
                )
            )

        db_items, raw_db_total = LogQueryService._query_db_history(
            need_rows=page * per_page, **db_kwargs)
        total = _view_total(raw_db_total)

        merged = sorted(
            file_items + db_items,
            key=LogQueryService._merge_sort_key,
            reverse=True,
        )
        # 文件侧触顶（LOG_AUDIT_MAX_SCAN_ENTRIES）时 file_total 同样是已物化
        # 行数：total 与 merged 长度一致，[1, pages] 内每页都有数据。
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
        # INT-1812 返工：DB 侧改为分块拉全量（此前一次要 10 万行越 gRPC 单条
        # 消息上限、异常被吞成空结果 → 导出静默只剩文件行）；整条链路失败一律
        # 显式报错，绝不产出部分数据当成功。
        try:
            rows = LogQueryService._collect_export_rows(req.log_ids, level, module)
            rows.sort(key=lambda row: (_parse_log_time(row[1]), row[0] or 0),
                      reverse=True)
            file_path = LogQueryService._write_export_file(rows, req.format)
        except _ExportTooManyRows as exc:
            return error_response(str(exc), code=ErrorCode.INVALID_PARAMS, http_code=400)
        except Exception as exc:
            log_not_emit('ERROR', 'log_controller', f'Error in export_logs: {str(exc)}',
                         category='system')
            return error_response(f"导出日志失败: {str(exc)}", code=500, http_code=500)

        return FileResponse(file_path, headers={"Content-Disposition": "attachment"})

    @staticmethod
    def _collect_export_rows(log_ids, level, module):
        """导出取数：与全局列表同源同筛选，返回紧凑行列表（不分页）。"""
        from shared.logging import CURSOR_FLOOR, AuditLogReader

        reader = AuditLogReader()
        rows = []
        if log_ids:
            file_cursors = [int(i) for i in log_ids if int(i) >= CURSOR_FLOOR]
            legacy_ids = [int(i) for i in log_ids if int(i) < CURSOR_FLOOR]
            if file_cursors:
                rows.extend(_to_export_row(entry)
                            for entry in reader.read_by_cursors(file_cursors))
            if legacy_ids:
                from api_gateway.infrastructure.grpc_proxies import task_data_service
                resp = task_data_service.get_logs_for_export(
                    log_ids=legacy_ids, level=level, module=module, reraise=True)
                rows.extend(_to_export_row(log) for log in (resp.get('items') or []))
            return rows

        # 与全局列表**同一取数路径**：文件侧同过滤参数、DB 侧同 list_logs
        # （level 大小写不敏感、module 'all' 归一、默认 30 天窗口、扫描上界
        # 一致），因此「同筛选下导出条数与列表一致」由构造保证。
        start_time, end_time = LogQueryService._resolve_window(None, None)
        filters = LogQueryService._audit_file_filters(
            level=level, module=module,
            start_time=start_time, end_time=end_time)
        rows.extend(_to_export_row(entry) for entry in reader.read_entries(**filters))
        # 分块拉取是 offset 分页：导出期间新写入的行会把后续块整体下移，造成
        # 重复/漏行。日志按当前时间落库，用导出起点的上界把 DB 结果集钉住，
        # 使各块看到同一批行（导出条数 = 首个响应里的精确 count）。
        snapshot_end = end_time or now_cst().strftime('%Y-%m-%d %H:%M:%S')
        db_rows, _db_total = LogQueryService._fetch_db_rows(
            level=level,
            module=filters['module'],
            start_time=start_time,
            end_time=snapshot_end,
            need_rows=0,
            convert=_to_export_row,
            max_total=LogQueryService._db_export_max_rows(),
        )
        rows.extend(db_rows)
        return rows

    @staticmethod
    def _write_export_file(rows, fmt):
        """把导出行写成文件并返回路径（csv/json/txt 流式，xlsx 走 pandas）。"""
        import os

        export_dir = os.path.join(os.getcwd(), 'exports')
        if not os.path.exists(export_dir):
            os.makedirs(export_dir)

        filename = f"logs_export_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        if fmt == 'csv':
            file_path = os.path.join(export_dir, f"{filename}.csv")
            with open(file_path, 'w', encoding='utf-8', newline='') as handle:
                writer = csv.writer(handle)
                writer.writerow(_EXPORT_COLUMNS)
                writer.writerows(rows)
        elif fmt == 'json':
            file_path = os.path.join(export_dir, f"{filename}.json")
            LogQueryService._write_rows_json(file_path, rows)
        elif fmt == 'txt':
            file_path = os.path.join(export_dir, f"{filename}.txt")
            with open(file_path, 'w', encoding='utf-8') as handle:
                for row in rows:
                    handle.write(f"[{row[1]}] {row[2]} {row[3]}: {row[4]}\n")
        else:  # 默认 Excel
            file_path = os.path.join(export_dir, f"{filename}.xlsx")
            # xlsx 仍走 pandas/openpyxl：流式 write_only 不接受日志内容里的控制
            # 字符（ANSI 转义等）会整单失败；30 万行 xlsx 实测约 50s
            df = pd.DataFrame([dict(zip(_EXPORT_COLUMNS, row)) for row in rows])
            df.to_excel(file_path, index=False)
        return file_path

    @staticmethod
    def _write_rows_json(file_path, rows):
        """records 数组（键序同 _EXPORT_COLUMNS，与 df.to_json(indent=4) 同形）。"""
        with open(file_path, 'w', encoding='utf-8') as handle:
            handle.write('[')
            for index, row in enumerate(rows):
                if index:
                    handle.write(',')
                handle.write('\n    ')
                handle.write(json.dumps(dict(zip(_EXPORT_COLUMNS, row)),
                                        ensure_ascii=False))
            handle.write('\n]' if rows else ']')

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
