# -*- coding: utf-8 -*-
"""审计日志文件读取器（INT-1793 契约 §Q2 读侧，INT-1812 卡片 2）。

审计事件由 task_service 单写者落盘（`audit_writer`）：
    logs/audit/{YYYY-MM-DD}/{category}.{service}.{hostname}-{pid}[-NNN].jsonl

本读取器与 `BusinessLogReader` 同款（逐行解析、过滤、扫描上限、TTL 缓存、
字段兜底），差异只有契约 §Q2 要求的三处：

1. **按日期目录枚举**：审计语料以事件日期为第一段，时间窗筛选只需枚举对应
   日期目录（日期剪枝）；无时间筛选时按 `LOG_AUDIT_QUERY_DEFAULT_DAYS`（30）
   取最近窗口，避免随保留期线性增长的无界扫描。
2. **无 task_id 根键**：审计语料按「日期 + category」组织，检索入口不是任务。
3. **条目 `id` = `cursor`**：游标 = 事件时间 epoch 微秒（写侧 H3 保证进程内
   严格递增），不是内容哈希——两个前端都拿列表 `id` 当增量游标。legacy
   `logs` 表自增 id（实测 max 6.9e6）用 `CURSOR_FLOOR`（10^12）隔开。

扫描上限 `LOG_AUDIT_MAX_SCAN_ENTRIES`（100000，0 = 不限）：文件按「新日期 →
旧日期、新分片 → 旧分片、文件内后写 → 先写」枚举，达上限即停止并保留**最新**
部分，`total` 为下界语义（`read_page` 的 `truncated`）。

同参数短 TTL 结果缓存（`LOG_AUDIT_SCAN_CACHE_TTL_SECONDS`，默认 3s，0 = 关闭，
照 INT-100 口径）：窗口内相同过滤参数的查询共享一次文件扫描，列表与统计因此
只扫一遍；只缓存查询结果、不引入写副作用（CQRS 查询侧只读纪律）。

缓存内存上界：全部缓存条目合计受 `_SCAN_CACHE_TOTAL_ENTRIES` 约束（与
`LOG_AUDIT_MAX_SCAN_ENTRIES` 同为 10 万条，超出预算先逐出最旧条目），单条结果
超过预算时不缓存（命中/未命中结果一致，仅失去 TTL 内免复扫）——常规 30 天窗口
（3.6 万~7.5 万行）与触顶窗口（10 万行）都在预算内，列表 / 统计可稳定命中。
"""
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Tuple

from shared.logging.config import get_log_settings
from shared.logging.enums import AUDIT_DIR, AUDIT_FILE_SUFFIX
from shared.logging.path_builder import AuditLogPathBuilder

# 游标下限（契约 §Q4）：审计文件条目 id = epoch 微秒，legacy logs 表自增
# id 实测 max=6,949,425；10^12 把两个 id 空间隔开，前端 int 精度无损。
CURSOR_FLOOR = 10 ** 12

_CST = timezone(timedelta(hours=8))
_LEVELS = ('debug', 'info', 'warning', 'error', 'critical')
_DATE_SEG_LEN = len('YYYY-MM-DD')

# TTL 结果缓存（模块级：读取器无状态定位不变，实例可随手创建）
_SCAN_CACHE: dict = {}
_SCAN_CACHE_LOCK = threading.Lock()
# 不同过滤组合的缓存条目数上限（溢出先清过期、再逐出最旧）
_SCAN_CACHE_MAX = 4
# 全部缓存条目合计的条目数预算（与 LOG_AUDIT_MAX_SCAN_ENTRIES 同量级）：
# 审计窗口语料 3.6 万~7.5 万行、触顶 10 万行，都在预算内；超出按最旧先出
# 逐出，防止多组过滤参数把读取侧内存拖垮
_SCAN_CACHE_TOTAL_ENTRIES = 100_000


def _parse_dt(value) -> Optional[datetime]:
    """宽容解析时间（datetime 原样 / ISO 字符串：'T' 或空格分隔、带微秒与时区）。"""
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _parse_date_seg(value) -> Optional[str]:
    """时间 → 日期段（YYYY-MM-DD，CST）；无法解析返回 None。"""
    moment = _parse_dt(value)
    if moment is None:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone(_CST)
    return moment.strftime('%Y-%m-%d')


def cursor_to_datetime(cursor: int) -> Optional[datetime]:
    """游标（epoch 微秒）→ CST naive datetime；非法返回 None。"""
    try:
        return datetime.fromtimestamp(int(cursor) / 1_000_000, tz=_CST).replace(tzinfo=None)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def cursor_to_date_seg(cursor: int) -> Optional[str]:
    """游标 → 该事件应落的日期目录段（与写入侧 `record['time'][:10]` 同口径）。"""
    moment = cursor_to_datetime(cursor)
    return moment.strftime('%Y-%m-%d') if moment is not None else None


def _record_cursor(record: dict) -> Optional[int]:
    """条目游标（int）；缺失/非法返回 None（该行不可用，读侧直接跳过）。"""
    value = record.get('cursor')
    if isinstance(value, bool) or value is None:
        return None
    try:
        cursor = int(value)
    except (TypeError, ValueError):
        return None
    return cursor if cursor > 0 else None


def _same_id(value, expected) -> bool:
    """id 类字段比较（DB 行是 int，JSONL 保留 emit 原值，可能是 str）。"""
    if expected in (None, ''):
        return True
    return str(value) == str(expected)


class AuditLogReader:
    """审计日志文件读取器（无状态，可跨服务共用）。"""

    def __init__(self, path_builder: AuditLogPathBuilder = None, root_dir: str = None):
        self._path_builder = path_builder or AuditLogPathBuilder()
        self._root_dir = root_dir if root_dir is not None else get_log_settings().root_dir

    # ---- 日期目录 / 文件枚举 ----

    @property
    def _audit_root(self) -> str:
        return os.path.join(self._root_dir, AUDIT_DIR)

    def _existing_date_segs(self) -> List[str]:
        """现存日期目录（升序，仅认 YYYY-MM-DD 形态）。"""
        try:
            names = os.listdir(self._audit_root)
        except OSError:
            return []
        segs = []
        for name in names:
            if len(name) != _DATE_SEG_LEN or _parse_date_seg(name) != name:
                continue
            if os.path.isdir(os.path.join(self._audit_root, name)):
                segs.append(name)
        return sorted(segs)

    def list_date_segs(self, *, start_time=None, end_time=None) -> List[str]:
        """枚举命中时间窗的日期目录（升序）。

        既无 start_time 也无 end_time 时取最近 `audit_query_default_days`
        天（契约 §Q2 的默认窗口，防无界扫描）；只给一侧时另一侧不设界。
        """
        existing = self._existing_date_segs()
        if not existing:
            return []
        start_dt = _parse_dt(start_time)
        end_dt = _parse_dt(end_time)
        if start_dt is None and end_dt is None:
            start_dt = datetime.now(_CST) - timedelta(days=self._default_window_days())
        start_seg = None
        if start_dt is not None:
            if start_dt.tzinfo is not None:
                start_dt = start_dt.astimezone(_CST)
            start_seg = start_dt.strftime('%Y-%m-%d')
        end_seg = _parse_date_seg(end_dt) if end_dt is not None else None
        return [seg for seg in existing
                if (start_seg is None or seg >= start_seg)
                and (end_seg is None or seg <= end_seg)]

    @staticmethod
    def _split_rank(filename: str) -> int:
        """文件新旧序（越大越新）：活跃文件（无 -NNN）最新，切分序号升序变旧。"""
        index = AuditLogPathBuilder.split_index_of(filename)
        return index if index else 10 ** 9

    def _files_of_date(self, date_seg: str, *, category: str = None,
                       newest_first: bool = True) -> List[str]:
        """某日期目录下的审计文件（含切分文件）。

        `category` 给定时按文件名首段剪枝（`{category}.{service}.{identity}`）。
        """
        dir_path = os.path.join(self._audit_root, date_seg)
        try:
            names = os.listdir(dir_path)
        except OSError:
            return []
        prefix = f'{category.lower()}.' if category and category != 'all' else None
        files = [
            name for name in names
            if name.endswith(AUDIT_FILE_SUFFIX)
            and (prefix is None or name.startswith(prefix))
            and os.path.isfile(os.path.join(dir_path, name))
        ]
        files.sort(key=self._split_rank, reverse=newest_first)
        return [os.path.join(dir_path, name) for name in files]

    # ---- 条目解析与过滤 ----

    @staticmethod
    def _parse_file(file_path: str) -> List[dict]:
        items = []
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if isinstance(record, dict):
                        items.append(record)
        except OSError:
            pass
        return items

    @staticmethod
    def _match(record: dict, *, levels=None, category=None, module=None,
               keyword=None, content_include=None, content_exclude=None,
               algorithm_type=None, test_case_id=None, thread_id=None,
               device_id=None, api_id=None, task_id=None, user_id=None,
               mark=None, start_dt=None, end_dt=None) -> bool:
        # 文件日志不可标记（契约 §Q3）：JSONL 无 mark 字段，mark 筛选恒空命中
        if mark:
            return False
        if levels and (record.get('level') or '').lower() not in levels:
            return False
        if category and category != 'all' and \
                (record.get('category') or '').lower() != category.lower():
            return False
        if module and module != 'all' and \
                (record.get('module') or '').lower() != module.lower():
            return False
        content = record.get('content') or ''
        if keyword and keyword not in content:
            return False
        if content_include and content_include not in content:
            return False
        if content_exclude and content_exclude in content:
            return False
        if algorithm_type and algorithm_type != 'all' and \
                record.get('algorithm_type') != algorithm_type:
            return False
        # thread_id 与 DB 侧同为包含匹配（log_repository 用 like %x%）
        if thread_id and thread_id not in str(record.get('thread_id') or ''):
            return False
        if not _same_id(record.get('test_case_id'), test_case_id):
            return False
        if not _same_id(record.get('device_id'), device_id):
            return False
        if not _same_id(record.get('api_id'), api_id):
            return False
        if not _same_id(record.get('task_id'), task_id):
            return False
        if user_id:
            # H2：写侧把 content 里的 operator_id 提取成 JSONL 顶层 user_id
            if not _same_id(record.get('user_id'), user_id):
                return False
        if start_dt is not None or end_dt is not None:
            log_time = record.get('time') or ''
            parsed = _parse_dt(log_time)
            if parsed is not None:
                try:
                    if start_dt is not None and parsed < start_dt:
                        return False
                    if end_dt is not None and parsed > end_dt:
                        return False
                except TypeError:
                    return AuditLogReader._match_time_text(
                        log_time, start_dt, end_dt)
            else:
                return AuditLogReader._match_time_text(log_time, start_dt, end_dt)
        return True

    @staticmethod
    def _match_time_text(log_time: str, start_dt, end_dt) -> bool:
        """一侧带时区一侧 naive 无法比较时回退字符串比较（与业务读取器同口径）。"""
        start_text = start_dt.isoformat(sep=' ') if isinstance(start_dt, datetime) else ''
        end_text = end_dt.isoformat(sep=' ') if isinstance(end_dt, datetime) else ''
        if start_text and log_time and log_time < start_text:
            return False
        if end_text and log_time and log_time > end_text:
            return False
        return True

    def _to_item(self, record: dict) -> Optional[dict]:
        """JSONL 行 → 读侧条目；`id` = cursor（契约 H3），缺游标的行跳过。"""
        cursor = _record_cursor(record)
        if cursor is None:
            return None
        user_id = record.get('user_id')
        if user_id is None:
            user_id = record.get('operator_id')
        return {
            'id': cursor,
            'time': record.get('time') or '',
            'level': (record.get('level') or '').upper(),
            'category': record.get('category') or '',
            'module': record.get('module') or '',
            'source': record.get('source') or '',
            'content': record.get('content') or '',
            'mark': None,
            'device_id': record.get('device_id'),
            'task_id': record.get('task_id'),
            'api_id': record.get('api_id'),
            'test_case_id': record.get('test_case_id'),
            'thread_id': record.get('thread_id'),
            'algorithm_type': record.get('algorithm_type'),
            'user_id': user_id,
            'service': record.get('service'),
        }

    @staticmethod
    def _sort_key(item: dict):
        """排序键（契约 §Q2）：(time desc, cursor desc)，cursor 唯一保证稳定。"""
        return (item.get('time') or '', item.get('id') or 0)

    # ---- 配置读取（缺失/非法时按最保守口径降级） ----

    @staticmethod
    def _settings_value(name: str, default: int) -> int:
        try:
            return max(0, int(getattr(get_log_settings(), name) or 0))
        except (AttributeError, TypeError, ValueError):
            return default

    def _default_window_days(self) -> int:
        return self._settings_value('audit_query_default_days', 30) or 30

    @staticmethod
    def default_window_start() -> str:
        """默认 30 天窗口起点（无 start_time/end_time 时列表 / 统计 / 导出共用）。"""
        days = AuditLogReader._settings_value('audit_query_default_days', 30) or 30
        return (datetime.now(_CST) - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

    # ---- 同参数查询结果短 TTL 缓存（只缓存查询结果） ----

    @staticmethod
    def _scan_cache_key(root_dir: str, kwargs: dict) -> tuple:
        parts = [str(root_dir)]
        for name in ('level', 'category', 'module', 'keyword', 'content_include',
                     'content_exclude', 'algorithm_type', 'test_case_id',
                     'thread_id', 'device_id', 'api_id', 'task_id', 'user_id',
                     'mark', 'start_time', 'end_time'):
            parts.append(str(kwargs.get(name)))
        return tuple(parts)

    @staticmethod
    def _scan_cache_ttl() -> int:
        try:
            return max(0, int(get_log_settings().audit_scan_cache_ttl_seconds or 0))
        except (AttributeError, TypeError, ValueError):
            return 0

    @staticmethod
    def _cache_purge_expired(now: float, ttl: int) -> None:
        for key in [k for k, entry in _SCAN_CACHE.items()
                    if now - entry[0] > ttl]:
            _SCAN_CACHE.pop(key, None)

    @staticmethod
    def _cache_total_entries() -> int:
        return sum(len(entry[1]) for entry in _SCAN_CACHE.values())

    @staticmethod
    def _scan_cache_get(key: tuple):
        """TTL 内命中返回 (条目列表快照, 是否触顶)，否则 None。"""
        ttl = AuditLogReader._scan_cache_ttl()
        if not ttl:
            return None
        now = time.monotonic()
        with _SCAN_CACHE_LOCK:
            AuditLogReader._cache_purge_expired(now, ttl)
            entry = _SCAN_CACHE.get(key)
            if entry is None:
                return None
            _stored_at, items, flag = entry
            return list(items), flag

    @staticmethod
    def _scan_cache_put(key: tuple, items: List[dict], flag) -> None:
        ttl = AuditLogReader._scan_cache_ttl()
        if not ttl or len(items) > _SCAN_CACHE_TOTAL_ENTRIES:
            return
        now = time.monotonic()
        with _SCAN_CACHE_LOCK:
            AuditLogReader._cache_purge_expired(now, ttl)
            while _SCAN_CACHE and (
                    len(_SCAN_CACHE) >= _SCAN_CACHE_MAX
                    or AuditLogReader._cache_total_entries() + len(items)
                    > _SCAN_CACHE_TOTAL_ENTRIES):
                _SCAN_CACHE.pop(min(_SCAN_CACHE, key=lambda k: _SCAN_CACHE[k][0]))
            _SCAN_CACHE[key] = (now, items, flag)

    # ---- 扫描 ----

    def _scan(self, *, date_segs: Iterable[str], filters: dict, cap: int,
              newest_first: bool) -> Tuple[List[dict], bool]:
        """按目录序扫描并过滤，返回 (条目, 是否触顶)；触顶保留最新部分。"""
        items: List[dict] = []
        truncated = False
        segs = list(date_segs)
        ordered = list(reversed(segs)) if newest_first else segs
        for date_seg in ordered:
            for path in self._files_of_date(
                    date_seg, category=filters.get('category'),
                    newest_first=newest_first):
                file_items = []
                for record in self._parse_file(path):
                    if not self._match(record, **filters):
                        continue
                    item = self._to_item(record)
                    if item is not None:
                        file_items.append(item)
                if newest_first:
                    # 文件内按写入顺序追加（后写更新）→ 新→旧需反转
                    file_items.reverse()
                if cap and len(items) + len(file_items) > cap:
                    file_items = file_items[:cap - len(items)]
                    truncated = True
                items.extend(file_items)
                if cap and len(items) >= cap:
                    break
            if cap and len(items) >= cap:
                break
        items.sort(key=self._sort_key, reverse=True)
        return items, truncated

    def _cap(self) -> int:
        return self._settings_value('audit_max_scan_entries', 100_000)

    # ---- 公开查询 ----

    def read_entries(self, *, level=None, category=None, module=None, keyword=None,
                     content_include=None, content_exclude=None,
                     algorithm_type=None, test_case_id=None, thread_id=None,
                     device_id=None, api_id=None, task_id=None, user_id=None,
                     mark=None, start_time=None, end_time=None) -> List[dict]:
        """读取命中条件的审计条目（(time desc, cursor desc)），不分页。"""
        return self.read_page(
            page=1, per_page=0, level=level, category=category, module=module,
            keyword=keyword, content_include=content_include,
            content_exclude=content_exclude, algorithm_type=algorithm_type,
            test_case_id=test_case_id, thread_id=thread_id, device_id=device_id,
            api_id=api_id, task_id=task_id, user_id=user_id, mark=mark,
            start_time=start_time, end_time=end_time)['items']

    def read_page(self, *, page: int = 1, per_page: int = 20, **filters) -> dict:
        """分页查询：返回 {items, total, page, per_page, pages, truncated}。

        `per_page=0` 表示不分页（导出 / 统计用，受扫描上界约束）。
        `total` 为窗口内命中数；`truncated=True` 时是下界（扫描触顶，保留最新）。
        """
        levels = None
        if filters.get('level'):
            levels = {lv.strip().lower()
                      for lv in str(filters['level']).split(',') if lv.strip()}
        cache_key = self._scan_cache_key(self._root_dir, filters)
        cached = self._scan_cache_get(cache_key)
        if cached is not None:
            items, truncated = cached
        else:
            start_dt = _parse_dt(filters.get('start_time'))
            end_dt = _parse_dt(filters.get('end_time'))
            match_filters = {
                'levels': levels,
                'category': filters.get('category'),
                'module': filters.get('module'),
                'keyword': filters.get('keyword'),
                'content_include': filters.get('content_include'),
                'content_exclude': filters.get('content_exclude'),
                'algorithm_type': filters.get('algorithm_type'),
                'test_case_id': filters.get('test_case_id'),
                'thread_id': filters.get('thread_id'),
                'device_id': filters.get('device_id'),
                'api_id': filters.get('api_id'),
                'task_id': filters.get('task_id'),
                'user_id': filters.get('user_id'),
                'mark': filters.get('mark'),
                'start_dt': start_dt,
                'end_dt': end_dt,
            }
            items, truncated = self._scan(
                date_segs=self.list_date_segs(
                    start_time=filters.get('start_time'),
                    end_time=filters.get('end_time')),
                filters=match_filters,
                cap=self._cap(),
                newest_first=True,
            )
            self._scan_cache_put(cache_key, items, truncated)
        total = len(items)
        page = max(1, int(page or 1))
        per_page = max(0, int(per_page or 0))
        if not per_page:
            page_items, pages = list(items), 1
        else:
            start = (page - 1) * per_page
            page_items = items[start:start + per_page]
            pages = (total + per_page - 1) // per_page if total else 0
        return {
            'items': page_items,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': pages,
            'truncated': truncated,
        }

    @staticmethod
    def count_by_level(items: Iterable[dict]) -> dict:
        """按 level 聚合（与 DB 统计同口径，未知级别只计入 total）。"""
        stats = {'total': 0, **{level: 0 for level in _LEVELS}}
        for item in items:
            stats['total'] += 1
            level = (item.get('level') or '').lower()
            if level in stats:
                stats[level] += 1
        return stats

    # ---- 增量游标（POST /logs/refresh，契约 §Q4）----

    def max_cursor(self) -> int:
        """当前审计语料的最大游标（无数据返回 0）。

        从最新日期目录往回找，命中即返回——游标与事件时间同序（H3），
        最新事件必在最新目录里。
        """
        for date_seg in reversed(self._existing_date_segs()):
            best = 0
            for path in self._files_of_date(date_seg, newest_first=True):
                for record in self._parse_file(path):
                    cursor = _record_cursor(record)
                    if cursor and cursor > best:
                        best = cursor
            if best:
                return best
        return 0

    def read_after_cursor(self, last_id: int, limit: int = 100) -> List[dict]:
        """游标升序增量：返回 cursor > last_id 的最多 limit 条。

        起始日期由 `last_id` 反推（游标即事件时间微秒），再枚举到最新目录；
        文件内按写入顺序升序，凑满 limit 即停（不扫完整窗口）。
        """
        try:
            cursor = int(last_id)
        except (TypeError, ValueError):
            return []
        if cursor <= 0:
            return []
        start_seg = cursor_to_date_seg(cursor)
        segs = [seg for seg in self._existing_date_segs()
                if start_seg is None or seg >= start_seg]
        items: List[dict] = []
        for date_seg in segs:
            for path in self._files_of_date(date_seg, newest_first=False):
                for record in self._parse_file(path):
                    item_cursor = _record_cursor(record)
                    if item_cursor is None or item_cursor <= cursor:
                        continue
                    item = self._to_item(record)
                    if item is not None:
                        items.append(item)
                if len(items) >= limit:
                    break
            if len(items) >= limit:
                break
        items.sort(key=lambda item: item['id'])
        return items[:limit]

    def read_by_cursors(self, cursors: Iterable[int]) -> List[dict]:
        """按游标反查条目（导出 `log_ids` 用）：由游标反推日期目录只扫当天。"""
        wanted_dates: dict = {}
        remaining = set()
        for value in cursors or []:
            try:
                cursor = int(value)
            except (TypeError, ValueError):
                continue
            date_seg = cursor_to_date_seg(cursor)
            if date_seg is None:
                continue
            wanted_dates.setdefault(date_seg, set()).add(cursor)
            remaining.add(cursor)
        if not remaining:
            return []
        items: List[dict] = []

        def _scan(date_segs):
            for date_seg in date_segs:
                if not remaining:
                    return
                for path in self._files_of_date(date_seg, newest_first=True):
                    for record in self._parse_file(path):
                        cursor = _record_cursor(record)
                        if cursor in remaining:
                            item = self._to_item(record)
                            if item is not None:
                                items.append(item)
                                remaining.discard(cursor)

        primary = list(wanted_dates.keys())
        _scan(primary)
        if remaining:
            # 时钟回拨 / 同微秒 +1 把游标推过日期边界：相邻日期兜底再找一次
            neighbours = set()
            for date_seg in primary:
                moment = _parse_dt(date_seg)
                if moment is None:
                    continue
                for delta in (-1, 1):
                    neighbours.add(
                        (moment + timedelta(days=delta)).strftime('%Y-%m-%d'))
            _scan(sorted(neighbours - set(primary)))
        items.sort(key=self._sort_key, reverse=True)
        return items
