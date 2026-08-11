# -*- coding: utf-8 -*-
"""LogRepository ABC — 系统日志仓储接口。

infrastructure/persistence/log_repository.py 继承此 ABC，实现依赖倒置。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class LogRepositoryABC(ABC):
    """系统日志仓储抽象接口。"""

    @abstractmethod
    def list_logs(self, task_id: int = 0, level: str = '',
                  start_date: str = '', end_date: str = '',
                  page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        """查询 Log 列表（分页 + 过滤），返回 {items, total, page, per_page}。"""
        ...

    @abstractmethod
    def batch_create(self, logs: List[Dict[str, Any]]) -> List[int]:
        """批量写入日志，返回写入后的 id 列表。"""
        ...

    @abstractmethod
    def get_stats(self, level: str = '', module: str = '', category: str = '',
                  mark: str = '', device_id: int = 0, task_id: int = 0,
                  keyword: str = '', content_include: str = '',
                  content_exclude: str = '', start_time: str = '',
                  end_time: str = '', algorithm_type: str = '') -> Dict[str, Any]:
        """查询日志统计（group_by level + count）。"""
        ...

    @abstractmethod
    def list_after_id(self, last_id: int, limit: int = 100) -> Dict[str, Any]:
        """增量查询日志（id > last_id），返回 {items, max_id}。"""
        ...

    @abstractmethod
    def get_for_export(self, log_ids: List[int] = None, level: str = '',
                       module: str = '') -> List[Dict[str, Any]]:
        """按 id 列表/条件查询日志（导出用）。"""
        ...

    @abstractmethod
    def get_count(self, start_date: str = '') -> Dict[str, int]:
        """查询日志总数（含按日期范围 hot 日志计数）。"""
        ...

    @abstractmethod
    def update_marks(self, log_ids: List[int], mark: str) -> int:
        """批量更新日志标记，返回更新数。"""
        ...

    @abstractmethod
    def clear(self, before_datetime: str = '', keep_marked: bool = False) -> int:
        """批量清除日志，返回删除数。"""
        ...

    @abstractmethod
    def archive(self, days: int = 30, dry_run: bool = False) -> Dict[str, Any]:
        """归档日志（按天数），返回分组结果。"""
        ...
