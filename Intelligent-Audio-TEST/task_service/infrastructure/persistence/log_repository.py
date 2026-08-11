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

from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy import func as _func
from sqlalchemy import or_ as _or

from shared.models.database import get_db_session
from shared.utils.query_utils import now_cst
from task_service.domain.repositories.log_repository import LogRepositoryABC
from task_service.infrastructure.persistence.models.system_models import Log


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
        'created_at': po.created_at.isoformat() if po.created_at else None,
    }


class LogRepository(LogRepositoryABC):
    """系统日志仓储实现。

    遵循 DDD 仓储模式：实现 LogRepositoryABC 接口。
    每个方法内部管理 DB session 生命周期。
    """

    def list_logs(self, task_id: int = 0, level: str = '',
                  start_date: str = '', end_date: str = '',
                  page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        """查询 Log 列表（分页 + 过滤），返回 {items, total, page, per_page}。"""
        session = get_db_session()
        try:
            query = session.query(Log)
            if task_id:
                query = query.filter(Log.task_id == task_id)
            if level:
                query = query.filter(Log.level == level)
            if start_date:
                try:
                    query = query.filter(Log.time >= datetime.fromisoformat(start_date))
                except ValueError:
                    pass
            if end_date:
                try:
                    query = query.filter(Log.time <= datetime.fromisoformat(end_date))
                except ValueError:
                    pass
            page = page or 1
            per_page = per_page or 20
            total = query.count()
            rows = (
                query.order_by(Log.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )
            items = [_log_po_to_dict(r) for r in rows]
            return {
                'items': items,
                'total': total,
                'page': page,
                'per_page': per_page,
            }
        finally:
            session.close()

    def batch_create(self, logs: List[Dict[str, Any]]) -> List[int]:
        """批量写入日志，返回写入后的 id 列表。"""
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
                    task_id=item.get('task_id'),
                    api_id=item.get('api_id'),
                    test_case_id=item.get('test_case_id'),
                    thread_id=item.get('thread_id'),
                    algorithm_type=item.get('algorithm_type'),
                )
                session.add(po)
                session.flush()
                ids.append(po.id)
            session.commit()
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
                  end_time: str = '', algorithm_type: str = '') -> Dict[str, Any]:
        """查询日志统计（group_by level + count）。"""
        session = get_db_session()
        try:
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
                    pass
            if end_time:
                try:
                    query = query.filter(Log.time <= datetime.fromisoformat(end_time))
                except ValueError:
                    pass
            if algorithm_type and algorithm_type != 'all':
                query = query.filter(Log.algorithm_type == algorithm_type)
            stats = query.group_by(Log.level).all()
            stats_dict = {lv.lower(): count for lv, count in stats}
            return {
                'total': sum(stats_dict.values()) if stats_dict else 0,
                'debug': stats_dict.get('debug', 0),
                'info': stats_dict.get('info', 0),
                'warning': stats_dict.get('warning', 0),
                'error': stats_dict.get('error', 0),
                'critical': stats_dict.get('critical', 0),
            }
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
                    pass
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
                    key = f'task_case/{log.task_id}/{log.test_case_id}/{log_date}'
                elif log.task_id:
                    key = f'task/{log.task_id}/{log_date}'
                elif log.test_case_id:
                    key = f'case/{log.test_case_id}/{log_date}'
                else:
                    key = f'other/{log_date}'
                groups.setdefault(key, []).append(_log_po_to_dict(log))
            log_ids = [log.id for log in cold_logs]
            session.query(Log).filter(Log.id.in_(log_ids)).delete(synchronize_session=False)
            session.commit()
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
