# -*- coding: utf-8 -*-
"""LogRepository - 系统日志仓储实现（写模型）。

仓储职责：
- 从 DB 加载 Log PO 并序列化为 dict
- 批量写入/更新/清除日志
- 归档冷日志（按 task_id/test_case_id/date 分组）

每个方法内部管理 DB session 生命周期（try/finally close），
写操作需要 commit + rollback。
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy import func as _func
from sqlalchemy import or_ as _or

from shared.infrastructure.config import BaseConfig
from shared.models.database import get_db_session
from shared.utils.query_utils import now_cst
from shared.infrastructure.user_context import normalize_user_id, get_current_user_id

logger = logging.getLogger(__name__)
from task_service.domain.repositories.log_repository import LogRepositoryABC
from task_service.infrastructure.persistence.models.system_models import Log


# ========== 聚合结果短 TTL 缓存（INT-1468）==========

# logs 表量级最大（30 万行级），列表 total 的 count(*) 与 stats 的 group by
# 每次请求都要全表扫描：并发 40 时是主要耗时与连接占用来源。这里只缓存
# 「聚合值」（计数 / 分组计数），不缓存行数据，键 = 过滤条件签名；窗口内同
# 条件请求共享一次聚合。写操作（新增/标记/清除/归档）在同进程内立即失效，
# 其它服务写入由 TTL 兜底（默认 3s，与文件侧扫描缓存同口径）。
_AGG_CACHE: Dict[tuple, tuple] = {}
_AGG_CACHE_LOCK = threading.Lock()
# 过期瞬间的并发请求单飞：只让一个线程重算聚合并回填，其余等它回填后命中，
# 否则 40 并发会在 TTL 到期同一刻各跑一次全表 count/group by
_AGG_REFRESH_LOCK = threading.Lock()


def _agg_cache_ttl() -> int:
    """TTL 秒数（0 = 关闭）；配置缺失/非法按关闭降级。"""
    try:
        return max(0, int(BaseConfig.LOG_DB_AGGREGATE_CACHE_TTL_SECONDS or 0))
    except (TypeError, ValueError):
        return 0


def _agg_cache_max_entries() -> int:
    try:
        return max(1, int(BaseConfig.LOG_DB_AGGREGATE_CACHE_MAX_ENTRIES or 1))
    except (TypeError, ValueError):
        return 1


def _agg_cache_get(key: tuple):
    """TTL 内命中返回聚合值，否则 None（访问时惰性清理过期条目）。"""
    ttl = _agg_cache_ttl()
    if not ttl:
        return None
    now = time.monotonic()
    with _AGG_CACHE_LOCK:
        expired = [k for k, (stored_at, _v) in _AGG_CACHE.items()
                   if now - stored_at > ttl]
        for k in expired:
            _AGG_CACHE.pop(k, None)
        entry = _AGG_CACHE.get(key)
        return entry[1] if entry is not None else None


def _agg_cache_put(key: tuple, value) -> None:
    if not _agg_cache_ttl():
        return
    now = time.monotonic()
    with _AGG_CACHE_LOCK:
        while len(_AGG_CACHE) >= _agg_cache_max_entries():
            _AGG_CACHE.pop(min(_AGG_CACHE, key=lambda k: _AGG_CACHE[k][0]))
        _AGG_CACHE[key] = (now, value)


def _agg_cache_clear() -> None:
    """写操作后整体失效（写少读多，整体清空比按条件精确失效更稳妥）。"""
    with _AGG_CACHE_LOCK:
        _AGG_CACHE.clear()


def _norm_text(value) -> str:
    return str(value).strip().lower() if value not in (None, '') else ''


def _filter_signature(kind: str, **filters) -> tuple:
    """过滤条件 → 规范化缓存键。

    只归一化「SQL 语义等价」的写法：空值/0 视为不过滤；level/module/category
    走 lower() 比较故大小写等价；module/category 的 'all' 在 SQL 层等同不过滤
    （`!= 'all'` 判断），level 的 'all' 不是——list_logs/get_stats 会把
    `level='all'` 当字面值过滤（返回空集），因此 level 只做小写归一。
    keyword 等 LIKE 敏感字段保持原样。
    """
    parts = [kind]
    for name in ('task_id', 'level', 'start_date', 'end_date', 'start_time',
                 'end_time', 'module', 'category', 'mark', 'device_id',
                 'api_id', 'test_case_id', 'thread_id', 'keyword',
                 'content_include', 'content_exclude', 'algorithm_type',
                 'user_id'):
        value = filters.get(name)
        if name == 'level':
            parts.append(_norm_text(value))
        elif name in ('module', 'category'):
            normalized = _norm_text(value)
            parts.append('' if normalized == 'all' else normalized)
        elif value in (None, '', 0, '0'):
            parts.append('')
        else:
            parts.append(str(value))
    return tuple(parts)


# ========== PO ↔ dict 转换 ==========

def _log_po_to_dict(po: Log) -> Dict[str, Any]:
    """Log PO → dict（包含所有业务字段）"""
    return {
        'id': po.id,
        'time': po.time.isoformat() if po.time else None,
        'level': po.level,
        'category': po.category,
        'module': po.module,
        'source': po.source,
        'content': po.content,
        'mark': po.mark,
        'device_id': po.device_id,
        'task_id': po.task_id,
        'api_id': po.api_id,
        'test_case_id': po.test_case_id,
        'thread_id': po.thread_id,
        'algorithm_type': po.algorithm_type,
        'created_by_user_id': po.created_by_user_id,
        'created_at': po.created_at.isoformat() if po.created_at else None,
    }


def _normalize_task_id(value):
    """logs.task_id 为 Integer 列（INT-90 缺陷 B）：数字/数字字符串规范为 int，
    非数字任务标识（e2e 合成任务 ID 如 't1'）置 None。原样写入 PostgreSQL
    必报「invalid input syntax for type bigint」，flush 失败毒化当前会话并
    拖垮同批全部日志。"""
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class LogRepository(LogRepositoryABC):
    """系统日志仓储实现。

    遵循 DDD 仓储模式：实现 LogRepositoryABC 接口。
    每个方法内部管理 DB session 生命周期。
    """

    def list_logs(self, task_id: int = 0, level: str = '',
                  start_date: str = '', end_date: str = '',
                  page: int = 1, per_page: int = 20,
                  module: str = '', category: str = '', mark: str = '',
                  device_id: int = 0, api_id: int = 0,
                  test_case_id: str = '', thread_id: str = '',
                  keyword: str = '', content_include: str = '',
                  content_exclude: str = '', algorithm_type: str = '',
                  user_id: int = 0) -> Dict[str, Any]:
        """查询 Log 列表（分页 + 过滤），返回 {items, total, page, per_page}。

        INT-100：level 支持逗号分隔多级别（大小写不敏感，与 get_stats 同语义）；
        module/category/mark/device_id/api_id/test_case_id/thread_id/keyword/
        content_*/algorithm_type 全部下推到 DB 过滤（调用方不传 = 不过滤）。
        INT-806：user_id 按 created_by_user_id 过滤（「仅自己」视图，不传 = 不过滤）。
        """
        session = get_db_session()
        try:
            query = session.query(Log)
            if task_id:
                query = query.filter(Log.task_id == task_id)
            if level:
                if ',' in level:
                    levels = [lv.strip().lower() for lv in level.split(',') if lv.strip()]
                    if levels:
                        query = query.filter(_func.lower(Log.level).in_(levels))
                else:
                    query = query.filter(_func.lower(Log.level) == level.lower())
            if start_date:
                try:
                    query = query.filter(Log.time >= datetime.fromisoformat(start_date))
                except ValueError:
                    logger.debug("list_logs start_date 非法 ISO 格式已忽略: %r", start_date)
            if end_date:
                try:
                    query = query.filter(Log.time <= datetime.fromisoformat(end_date))
                except ValueError:
                    logger.debug("list_logs end_date 非法 ISO 格式已忽略: %r", end_date)
            if module and module != 'all':
                query = query.filter(_func.lower(Log.module) == module.lower())
            if category and category != 'all':
                query = query.filter(_func.lower(Log.category) == category.lower())
            if mark:
                query = query.filter_by(mark=mark)
            if device_id:
                query = query.filter_by(device_id=device_id)
            if api_id:
                query = query.filter_by(api_id=api_id)
            if test_case_id:
                query = query.filter_by(test_case_id=test_case_id)
            if thread_id:
                query = query.filter(Log.thread_id.like(f"%{thread_id}%"))
            if keyword:
                query = query.filter(Log.content.like(f"%{keyword}%"))
            if content_include:
                query = query.filter(Log.content.like(f"%{content_include}%"))
            if content_exclude:
                query = query.filter(~Log.content.like(f"%{content_exclude}%"))
            if algorithm_type and algorithm_type != 'all':
                query = query.filter(Log.algorithm_type == algorithm_type)
            if user_id:
                query = query.filter(Log.created_by_user_id == user_id)
            page = page or 1
            per_page = per_page or 20
            # INT-1468：total 走聚合缓存（同条件 TTL 内复用一个 count(*)），
            # 分页行本身仍实时查询，只让「总数」有 TTL 级展示时延
            count_key = _filter_signature(
                'count', task_id=task_id, level=level, start_date=start_date,
                end_date=end_date, module=module, category=category, mark=mark,
                device_id=device_id, api_id=api_id, test_case_id=test_case_id,
                thread_id=thread_id, keyword=keyword,
                content_include=content_include,
                content_exclude=content_exclude,
                algorithm_type=algorithm_type, user_id=user_id,
            )
            total = _agg_cache_get(count_key)
            if total is None:
                with _AGG_REFRESH_LOCK:
                    total = _agg_cache_get(count_key)
                    if total is None:
                        total = query.count()
                        _agg_cache_put(count_key, total)
            # INT-1946：排序口径 = (time desc, id desc)，与网关合并视图的
            # `_merge_sort_key` 全序一致。此前只按 id 倒序，与合并侧按 time
            # 倒序不同序，导致合并视图「每页尾部重复、页间漏行」（库里存在
            # id 大而 time 早的行时，DB 前缀取不到本该进页的行）。
            # logs.time 已有 idx_time / (task_id, time) 复合索引可服务该序。
            rows = (
                query.order_by(Log.time.desc(), Log.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )
            items = [_log_po_to_dict(r) for r in rows]
            # INT-297：分页信封统一为 {items, page, pages, per_page, total}
            return {
                'items': items,
                'total': total,
                'page': page,
                'per_page': per_page,
                'pages': (total + per_page - 1) // per_page if per_page else 1,
            }
        finally:
            session.close()

    def batch_create(self, logs: List[Dict[str, Any]]) -> List[int]:
        """批量写入日志，返回写入后的 id 列表。

        INT-806：写侧归属——条目显式携带 user_id 时优先（worker 载荷透传），
        否则回退 servicer 上下文用户（get_current_user_id()）；两者皆无 → NULL
        （不硬编码兜底为真实用户，红线）。
        """
        if not logs:
            return []
        session = get_db_session()
        try:
            ids: List[int] = []
            for item in logs:
                po = Log(
                    time=item.get('time') or now_cst(),
                    level=item.get('level', 'INFO'),
                    category=item.get('category', 'System'),
                    module=item.get('module', ''),
                    source=item.get('source', ''),
                    content=item.get('content', ''),
                    mark=item.get('mark'),
                    device_id=item.get('device_id'),
                    task_id=_normalize_task_id(item.get('task_id')),
                    api_id=item.get('api_id'),
                    test_case_id=item.get('test_case_id'),
                    thread_id=item.get('thread_id'),
                    algorithm_type=item.get('algorithm_type'),
                    created_by_user_id=normalize_user_id(item.get('user_id'))
                    or get_current_user_id(),
                )
                session.add(po)
                session.flush()
                ids.append(po.id)
            session.commit()
            _agg_cache_clear()
            return ids
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_stats(self, level: str = '', module: str = '', category: str = '',
                  mark: str = '', device_id: int = 0, task_id: int = 0,
                  keyword: str = '', content_include: str = '',
                  content_exclude: str = '', start_time: str = '',
                  end_time: str = '', algorithm_type: str = '',
                  user_id: int = 0) -> Dict[str, Any]:
        """查询日志统计（group_by level + count）。

        INT-806：user_id 按 created_by_user_id 过滤（统计口径与列表一致）。
        """
        session = get_db_session()
        try:
            # INT-1468：stats 为全表 group by（30 万行级），同条件 TTL 内复用
            stats_key = _filter_signature(
                'stats', level=level, module=module, category=category,
                mark=mark, device_id=device_id, task_id=task_id,
                keyword=keyword, content_include=content_include,
                content_exclude=content_exclude, start_time=start_time,
                end_time=end_time, algorithm_type=algorithm_type,
                user_id=user_id,
            )
            cached_stats = _agg_cache_get(stats_key)
            if cached_stats is not None:
                return dict(cached_stats)
            query = session.query(Log.level, _func.count(Log.id))
            if level:
                if ',' in level:
                    levels = [l.strip().lower() for l in level.split(',')]
                    query = query.filter(_func.lower(Log.level).in_(levels))
                else:
                    query = query.filter(_func.lower(Log.level) == level.lower())
            if module and module != 'all':
                query = query.filter(_func.lower(Log.module) == module.lower())
            if category and category != 'all':
                query = query.filter(_func.lower(Log.category) == category.lower())
            if mark:
                query = query.filter_by(mark=mark)
            if device_id:
                query = query.filter_by(device_id=device_id)
            if task_id:
                query = query.filter_by(task_id=task_id)
            if keyword:
                query = query.filter(Log.content.like(f"%{keyword}%"))
            if content_include:
                query = query.filter(Log.content.like(f"%{content_include}%"))
            if content_exclude:
                query = query.filter(~Log.content.like(f"%{content_exclude}%"))
            if start_time:
                try:
                    query = query.filter(Log.time >= datetime.fromisoformat(start_time))
                except ValueError:
                    logger.debug("get_stats start_time 非法 ISO 格式已忽略: %r", start_time)
            if end_time:
                try:
                    query = query.filter(Log.time <= datetime.fromisoformat(end_time))
                except ValueError:
                    logger.debug("get_stats end_time 非法 ISO 格式已忽略: %r", end_time)
            if algorithm_type and algorithm_type != 'all':
                query = query.filter(Log.algorithm_type == algorithm_type)
            if user_id:
                query = query.filter(Log.created_by_user_id == user_id)
            with _AGG_REFRESH_LOCK:
                cached_stats = _agg_cache_get(stats_key)
                if cached_stats is not None:
                    return dict(cached_stats)
                stats = query.group_by(Log.level).all()
                stats_dict = {lv.lower(): count for lv, count in stats}
                result = {
                    'total': sum(stats_dict.values()) if stats_dict else 0,
                    'debug': stats_dict.get('debug', 0),
                    'info': stats_dict.get('info', 0),
                    'warning': stats_dict.get('warning', 0),
                    'error': stats_dict.get('error', 0),
                    'critical': stats_dict.get('critical', 0),
                }
                _agg_cache_put(stats_key, result)
            return dict(result)
        finally:
            session.close()

    def list_after_id(self, last_id: int, limit: int = 100) -> Dict[str, Any]:
        """增量查询日志（id > last_id），返回 {items, max_id}。"""
        session = get_db_session()
        try:
            limit = limit or 100
            rows = (
                session.query(Log)
                .filter(Log.id > last_id)
                .order_by(Log.id.asc())
                .limit(limit)
                .all()
            )
            items = [_log_po_to_dict(r) for r in rows]
            max_id_row = session.query(Log.id).order_by(Log.id.desc()).first()
            max_id = max_id_row[0] if max_id_row else 0
            return {'items': items, 'max_id': max_id}
        finally:
            session.close()

    def get_for_export(self, log_ids: List[int] = None, level: str = '',
                       module: str = '') -> List[Dict[str, Any]]:
        """按 id 列表/条件查询日志（导出用）。"""
        session = get_db_session()
        try:
            query = session.query(Log)
            if log_ids:
                query = query.filter(Log.id.in_(list(log_ids)))
            else:
                if level:
                    query = query.filter_by(level=level)
                if module:
                    query = query.filter(_func.lower(Log.module) == module.lower())
            rows = query.order_by(Log.time.desc()).all()
            return [_log_po_to_dict(r) for r in rows]
        finally:
            session.close()

    def get_count(self, start_date: str = '') -> Dict[str, int]:
        """查询日志总数（含按日期范围 hot 日志计数）。"""
        session = get_db_session()
        try:
            total = session.query(_func.count(Log.id)).scalar() or 0
            hot = 0
            if start_date:
                try:
                    cutoff = datetime.fromisoformat(start_date)
                    hot = (
                        session.query(_func.count(Log.id))
                        .filter(Log.time >= cutoff)
                        .scalar()
                        or 0
                    )
                except ValueError:
                    logger.debug("archive_logs start_date 非法 ISO 格式已忽略: %r", start_date)
            return {'total': total, 'hot': hot, 'cold': total - hot}
        finally:
            session.close()

    def update_marks(self, log_ids: List[int], mark: str) -> int:
        """批量更新日志标记，返回更新数。"""
        session = get_db_session()
        try:
            count = (
                session.query(Log)
                .filter(Log.id.in_(list(log_ids)))
                .update({'mark': mark}, synchronize_session=False)
            )
            session.commit()
            _agg_cache_clear()
            return count
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def clear(self, before_datetime: str = '', keep_marked: bool = False) -> int:
        """批量清除日志，返回删除数。"""
        session = get_db_session()
        try:
            query = session.query(Log)
            if before_datetime:
                query = query.filter(Log.time < datetime.fromisoformat(before_datetime))
            if keep_marked:
                query = query.filter(_or(Log.mark.is_(None), Log.mark == ''))
            count = query.delete(synchronize_session=False)
            session.commit()
            _agg_cache_clear()
            return count
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def archive(self, days: int = 30, dry_run: bool = False) -> Dict[str, Any]:
        """归档日志（按天数），返回分组结果。

        读取冷日志并按 (task_id, test_case_id, date) 分组返回，
        然后删除已归档的记录。调用方（api_gateway）负责将分组写入 OSS。

        dry_run=True 时仅返回冷日志数量与截止日期。
        """
        session = get_db_session()
        try:
            cutoff = now_cst() - timedelta(days=days or 30)
            cold_query = session.query(Log).filter(Log.time < cutoff)
            cold_count = cold_query.count()
            if dry_run:
                return {
                    'cold_logs_count': cold_count,
                    'cutoff_date': cutoff.isoformat(),
                }
            if cold_count == 0:
                remaining = session.query(_func.count(Log.id)).scalar() or 0
                return {
                    'archived_count': 0,
                    'deleted_count': 0,
                    'remaining_count': remaining,
                }
            # 读取冷日志并按 task/case/other 分组
            cold_logs = cold_query.order_by(Log.time.asc()).all()
            groups: Dict[str, List[Dict[str, Any]]] = {}
            for log in cold_logs:
                log_date = (log.time or datetime.now()).strftime('%Y-%m-%d')
                if log.task_id and log.test_case_id:
                    key = f'tasks/{log.task_id}/{log.test_case_id}/{log_date}'
                elif log.task_id:
                    key = f'tasks/{log.task_id}/{log_date}'
                elif log.test_case_id:
                    key = f'cases/{log.test_case_id}/{log_date}'
                else:
                    key = f'other/{log_date}'
                groups.setdefault(key, []).append(_log_po_to_dict(log))
            log_ids = [log.id for log in cold_logs]
            session.query(Log).filter(Log.id.in_(log_ids)).delete(synchronize_session=False)
            session.commit()
            _agg_cache_clear()
            remaining = session.query(_func.count(Log.id)).scalar() or 0
            return {
                'archived_count': cold_count,
                'deleted_count': len(log_ids),
                'remaining_count': remaining,
                'groups': groups,
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


# 模块级单例
log_repository = LogRepository()
