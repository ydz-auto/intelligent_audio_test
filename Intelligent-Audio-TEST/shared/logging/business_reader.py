# -*- coding: utf-8 -*-
"""业务日志文件读取器（INT-81）。

按 任务ID/设备ID/API ID/评估ID(轮次) 路径检索业务日志文件，逐行解析
JSON Lines 并过滤、排序、分页。历史 logs 表数据保留只读不迁移，读取
侧由 api_gateway / report_service 的应用服务组合本读取器与 DB 历史行。

读取条数上限（审计问题 2 修复）：单次查询最多物化 business_max_scan_entries
条（LOG_BUSINESS_MAX_SCAN_ENTRIES，0 = 不限）。文件按活跃（最新）在前
枚举，超限时停止扫描更旧文件、溢出文件保留最新部分——total 为下界语义，
防止大任务轮询把读取侧拖垮；常规任务远低于上限无感知。

同参数短 TTL 结果缓存（INT-100）：TTL（LOG_BUSINESS_SCAN_CACHE_TTL_SECONDS，
默认 3s，0 = 关闭）窗口内相同过滤参数的查询共享一次文件扫描，消除任务
维度轮询 list + stats 的双遍扫描。只缓存查询结果、不引入写副作用（CQRS
查询侧只读纪律）；TTL 内新写入的行不可见（有界展示时延，前端展示处注明）。
"""
import json
import os
import threading
import time
from datetime import datetime
from typing import List, Optional

from shared.logging.config import get_log_settings
from shared.logging.enums import BusinessLogType
from shared.logging.path_builder import BusinessLogPathBuilder

# 条目字段（与写入侧 _ENTRY_FIELDS 对齐，读取时兜底空值）
_LEVELS = ('debug', 'info', 'warning', 'error', 'critical')

# TTL 结果缓存（模块级：BusinessLogReader 无状态定位不变，实例可随手创建）
_SCAN_CACHE: dict = {}
_SCAN_CACHE_LOCK = threading.Lock()
# 缓存条目上限：不同过滤组合有限收敛，溢出先清过期、再逐出最旧
_SCAN_CACHE_MAX = 32


def _stable_int_id(text: str) -> int:
    """相对路径+行号 → 稳定 int id（前端 key/详情展开用，非 DB id）。"""
    import hashlib
    return int(hashlib.md5(text.encode('utf-8')).hexdigest()[:12], 16)


def _parse_log_time(value) -> Optional[datetime]:
    """宽容解析日志时间（'T'/空格分隔、带/不带微秒与时区均可）。"""
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


class BusinessLogReader:
    """业务日志文件读取器（无状态，可跨服务共用）。"""

    def __init__(self, path_builder: BusinessLogPathBuilder = None, root_dir: str = None):
        self._path_builder = path_builder or BusinessLogPathBuilder()
        self._root_dir = root_dir if root_dir is not None else get_log_settings().root_dir

    # ---- 文件枚举 ----

    def list_log_files(self, *, task_id, device_id=None, api_id=None,
                       evaluation_id=None, round_value=None,
                       log_type: Optional[BusinessLogType] = None) -> List[str]:
        """枚举命中路径范围的日志文件绝对路径（含切分文件）。

        路径段按调用方显式给定的条件逐级收敛：给 device/api 收敛第二段，
        给 evaluation/round 收敛第三段；仅给轮次不给设备时扫描任务下全部
        设备目录中匹配轮次的文件。
        """
        if task_id in (None, ''):
            return []
        task_seg = self._path_builder.sanitize_segment(task_id)
        abs_root = os.path.join(self._root_dir, 'business', task_seg)
        if not os.path.isdir(abs_root):
            return []

        target_seg = None
        if device_id not in (None, ''):
            target_seg = self._path_builder.sanitize_segment(device_id)
        elif api_id not in (None, ''):
            target_seg = self._path_builder.sanitize_segment(api_id)
        scope_seg = None
        if evaluation_id not in (None, ''):
            scope_seg = self._path_builder.sanitize_segment(evaluation_id)
        elif round_value not in (None, ''):
            scope_seg = self._path_builder.sanitize_segment(round_value)

        abs_scan = os.path.join(abs_root, target_seg) if target_seg else abs_root
        if not os.path.isdir(abs_scan):
            return []

        type_prefix = f'{log_type.value}.' if log_type is not None else None
        files: List[str] = []
        for root, _dirs, names in os.walk(abs_scan):
            for name in sorted(names):
                if not name.endswith('.log'):
                    continue
                if type_prefix is not None and not name.startswith(type_prefix):
                    continue
                rel_parts = os.path.relpath(root, abs_root).split(os.sep)
                # 过滤第三段：轮次/评估目录位于 设备段 之后（从设备目录起扫描时为首段）
                if scope_seg is not None:
                    scope_idx = 0 if target_seg else 1
                    if len(rel_parts) <= scope_idx or rel_parts[scope_idx] != scope_seg:
                        continue
                files.append(os.path.join(root, name))
        # 切分序号升序（-001 在前），活跃文件（无序号）最后
        files.sort(key=lambda p: (self._path_builder.split_index_of(os.path.basename(p)), p))
        return files

    # ---- 条目解析与过滤 ----

    def _parse_file(self, file_path: str) -> List[dict]:
        items = []
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as handle:
                for line_no, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if isinstance(record, dict):
                        record['_src'] = file_path
                        record['_line'] = line_no
                        items.append(record)
        except OSError:
            pass
        return items

    @staticmethod
    def _match(record: dict, *, levels=None, category=None, module=None,
               keyword=None, content_include=None, content_exclude=None,
               algorithm_type=None, test_case_id=None, start_time=None,
               end_time=None) -> bool:
        level = (record.get('level') or '').lower()
        if levels and level not in levels:
            return False
        if category and category != 'all' and \
                (record.get('category') or '').lower() != category.lower():
            return False
        if module and (record.get('module') or '').lower() != module.lower():
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
        if test_case_id and str(record.get('test_case_id') or '') != str(test_case_id):
            return False
        log_time = record.get('time') or ''
        if start_time or end_time:
            parsed = _parse_log_time(log_time)
            start_dt = _parse_log_time(start_time)
            end_dt = _parse_log_time(end_time)
            if parsed is not None and (start_dt is not None or end_dt is not None):
                # 双方可解析为 datetime：按时间比较（兼容 'T'/空格/微秒/时区差异）
                try:
                    if start_dt is not None and parsed < start_dt:
                        return False
                    if end_dt is not None and parsed > end_dt:
                        return False
                except TypeError:
                    # 一侧带时区一侧 naive 无法比较：回退字符串比较
                    if start_time and log_time and log_time < start_time:
                        return False
                    if end_time and log_time and log_time > end_time:
                        return False
            else:
                if start_time and log_time and log_time < start_time:
                    return False
                if end_time and log_time and log_time > end_time:
                    return False
        return True

    def _to_item(self, record: dict) -> dict:
        rel = os.path.relpath(record['_src'], self._root_dir).replace(os.sep, '/')
        return {
            'id': _stable_int_id(f'{rel}:{record["_line"]}'),
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
            'round': record.get('round'),
            'log_type': record.get('log_type'),
            'service': record.get('service'),
        }

    # ---- 同参数查询结果短 TTL 缓存（INT-100，只缓存查询结果） ----

    @staticmethod
    def _scan_cache_key(root_dir: str, kwargs: dict) -> tuple:
        """过滤参数 → 规范化缓存键（log_type 取枚举值，其余 str 化）。"""
        parts = [str(root_dir)]
        for name in ('task_id', 'device_id', 'api_id', 'evaluation_id',
                     'round_value', 'level', 'category', 'module', 'keyword',
                     'content_include', 'content_exclude', 'algorithm_type',
                     'test_case_id', 'start_time', 'end_time'):
            parts.append(str(kwargs.get(name)))
        log_type = kwargs.get('log_type')
        parts.append(log_type.value if log_type is not None else '')
        return tuple(parts)

    @staticmethod
    def _scan_cache_ttl() -> int:
        """TTL 秒数（0 = 关闭）；配置缺失/非法时按关闭降级（与 cap 兜底同风格）。"""
        try:
            return max(0, int(get_log_settings().business_scan_cache_ttl_seconds or 0))
        except (AttributeError, TypeError, ValueError):
            return 0

    @staticmethod
    def _scan_cache_get(key: tuple):
        """TTL 内命中返回条目列表快照（浅拷贝，条目只读共享），否则 None。"""
        ttl = BusinessLogReader._scan_cache_ttl()
        if not ttl:
            return None
        now = time.monotonic()
        with _SCAN_CACHE_LOCK:
            entry = _SCAN_CACHE.get(key)
            if entry is None:
                return None
            stored_at, items = entry
            if now - stored_at > ttl:
                _SCAN_CACHE.pop(key, None)
                return None
            return list(items)

    @staticmethod
    def _scan_cache_put(key: tuple, items: List[dict]) -> None:
        ttl = BusinessLogReader._scan_cache_ttl()
        if not ttl:
            return
        now = time.monotonic()
        with _SCAN_CACHE_LOCK:
            if len(_SCAN_CACHE) >= _SCAN_CACHE_MAX:
                expired = [k for k, (ts, _v) in _SCAN_CACHE.items() if now - ts > ttl]
                for k in expired:
                    _SCAN_CACHE.pop(k, None)
                while len(_SCAN_CACHE) >= _SCAN_CACHE_MAX:
                    _SCAN_CACHE.pop(min(_SCAN_CACHE, key=lambda k: _SCAN_CACHE[k][0]))
            _SCAN_CACHE[key] = (now, list(items))

    # ---- 公开查询 ----

    def read_entries(self, *, task_id, device_id=None, api_id=None,
                     evaluation_id=None, round_value=None,
                     log_type: Optional[BusinessLogType] = None,
                     level=None, category=None, module=None, keyword=None,
                     content_include=None, content_exclude=None,
                     algorithm_type=None, test_case_id=None,
                     start_time=None, end_time=None) -> List[dict]:
        """读取命中条件的日志条目（按时间倒序），不分页。

        条数上限 business_max_scan_entries（0 = 不限）：文件按活跃（最新）
        在前枚举，达上限即停止扫描更旧文件；溢出文件保留最新部分，
        total 为下界语义（防止大任务轮询全量物化拖垮读取侧）。

        同参数短 TTL 结果缓存（business_scan_cache_ttl_seconds，0 = 关闭）：
        TTL 窗口内相同过滤参数直接复用上次扫描结果（list 与 stats 共享一次
        文件扫描）；命中返回列表浅拷贝，条目为共享只读 dict。
        """
        levels = None
        if level:
            levels = {lv.strip().lower() for lv in str(level).split(',') if lv.strip()}
        cache_key = self._scan_cache_key(self._root_dir, {
            'task_id': task_id, 'device_id': device_id, 'api_id': api_id,
            'evaluation_id': evaluation_id, 'round_value': round_value,
            'log_type': log_type, 'level': level, 'category': category,
            'module': module, 'keyword': keyword,
            'content_include': content_include, 'content_exclude': content_exclude,
            'algorithm_type': algorithm_type, 'test_case_id': test_case_id,
            'start_time': start_time, 'end_time': end_time,
        })
        cached = self._scan_cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            cap = max(0, int(get_log_settings().business_max_scan_entries))
        except (AttributeError, TypeError, ValueError):
            cap = 0
        items: List[dict] = []
        for file_path in self.list_log_files(
                task_id=task_id, device_id=device_id, api_id=api_id,
                evaluation_id=evaluation_id, round_value=round_value,
                log_type=log_type):
            if cap and len(items) >= cap:
                break
            file_items = []
            for record in self._parse_file(file_path):
                if self._match(record, levels=levels, category=category,
                               module=module, keyword=keyword,
                               content_include=content_include,
                               content_exclude=content_exclude,
                               algorithm_type=algorithm_type,
                               test_case_id=test_case_id,
                               start_time=start_time, end_time=end_time):
                    file_items.append(self._to_item(record))
            if cap and len(items) + len(file_items) > cap:
                # 溢出文件保留最新部分（文件内按行追加升序，取尾部）
                file_items = file_items[-(cap - len(items)):]
            items.extend(file_items)
        items.sort(key=lambda item: item['time'] or '', reverse=True)
        self._scan_cache_put(cache_key, items)
        return list(items)

    def read_page(self, **filters) -> dict:
        """分页查询：filters 含 page/per_page，返回 {items, total, page, per_page}。"""
        page = max(1, int(filters.pop('page', 1) or 1))
        per_page = max(1, int(filters.pop('per_page', 20) or 20))
        items = self.read_entries(**filters)
        start = (page - 1) * per_page
        return {
            'items': items[start:start + per_page],
            'total': len(items),
            'page': page,
            'per_page': per_page,
        }

    def load_file_bytes(self, *, task_id, device_id=None, api_id=None,
                        evaluation_id=None, round_value=None,
                        log_type: Optional[BusinessLogType] = None) -> List[tuple]:
        """收集命中路径范围的日志文件（相对路径, 字节内容），供打包下载。"""
        results = []
        for file_path in self.list_log_files(
                task_id=task_id, device_id=device_id, api_id=api_id,
                evaluation_id=evaluation_id, round_value=round_value,
                log_type=log_type):
            rel = os.path.relpath(file_path, os.path.join(self._root_dir, self._path_builder.build_task_dir(task_id)))
            try:
                with open(file_path, 'rb') as handle:
                    results.append((rel.replace(os.sep, '/'), handle.read()))
            except OSError:
                continue
        return results
