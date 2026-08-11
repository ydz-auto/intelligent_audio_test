"""
数据库初始化模块 - 共享层

原生 SQLAlchemy 实现。连接池：create_engine(pool_size, max_overflow,
pool_recycle, pool_pre_ping)，scoped_session 基于 threading.local，
线程内复用、跨线程隔离。

公开 API：
- `Base`：ORM 基类（declarative_base()），PO 继承它
- `get_db_session()`：取当前线程的 scoped_session
- `get_engine()`：取全局 engine（init_db 后可用）
- `init_db(pool_size)`：初始化连接池
- `remove_db_session()`：清理当前线程的 session
- `Model.query`：描述符，代理到 scoped_session.query(cls)（32 个文件在用）
- `Query.paginate()`：分页补丁（17 处 repository 在用）
"""
import threading
from datetime import datetime, timezone, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker, Query

from shared.infrastructure.config import BaseConfig


def utc8now():
    """东八区当前时间（所有 PO 的 created_at/updated_at 默认值）。"""
    return datetime.now(timezone(timedelta(hours=8)))


class _Pagination:
    """分页结果对象"""

    def __init__(self, query, page, per_page, error_out=True):
        self.query = query
        self.page = page
        self.per_page = per_page
        self.total = query.count()
        self.items = query.limit(per_page).offset((page - 1) * per_page).all()

    @property
    def pages(self):
        if self.per_page == 0:
            return 0
        return (self.total + self.per_page - 1) // self.per_page

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def prev_num(self):
        return self.page - 1 if self.has_prev else None

    @property
    def next_num(self):
        return self.page + 1 if self.has_next else None

    def iter_pages(self, left_edge=2, left_current=2, right_current=5, right_edge=2):
        last = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge or (num > self.page - left_current - 1 and num < self.page + right_current) or num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num


def _query_paginate(self, page=None, per_page=None, error_out=True, max_per_page=None):
    """Query.paginate()：返回 _Pagination"""
    if page is None:
        page = 1
    if per_page is None:
        per_page = 20
    if max_per_page is not None:
        per_page = min(per_page, max_per_page)
    return _Pagination(self, page, per_page, error_out=error_out)


# 给原生 Query 打补丁，添加 paginate 方法（被下游 repository 大量使用）
Query.paginate = _query_paginate


class _QueryProperty:
    """`Model.query` 描述符，代理到 `scoped_session.query(cls)`。

    使 `Model.query.filter_by(...)` 等写法在原生 SQLAlchemy 下可用。
    """

    def __get__(self, instance, owner):
        # owner 是模型类，instance 是实例（类访问时为 None）
        return _scoped_session.query(owner)


# 全局 engine 引用（单例，由 init_db 设置，通过 get_engine() 访问）
_engine = None

_Base = declarative_base()

# 公共基类：PO 定义继承 `Base`
Base = _Base

# `Model.query` 属性：兼容 `Model.query.filter_by(...)` 写法（32 个文件在用）
_Base.query = _QueryProperty()

# scoped_session：在 init_db 之前调用 get_db_session() 取到的 session 无绑定 engine
_SessionFactory = sessionmaker(bind=None, autoflush=True, autocommit=False)
_scoped_session = scoped_session(_SessionFactory, scopefunc=threading.get_ident)


def get_engine():
    """获取全局 engine 实例（init_db 后可用）"""
    return _engine


def init_db(pool_size=10):
    """初始化数据库连接池。

    Args:
        pool_size: 连接池大小

    Returns:
        scoped_session 对象
    """
    global _engine
    uri = BaseConfig.DATABASE_URL
    if not uri:
        raise RuntimeError('未配置 DATABASE_URL 环境变量')

    engine = create_engine(
        uri,
        pool_size=pool_size,
        pool_recycle=3600,
        pool_pre_ping=True,
        max_overflow=20,
    )

    # 绑定 session 工厂到 engine
    _SessionFactory.configure(bind=engine)

    # 持有全局引用，防止 GC
    _engine = engine

    return _scoped_session


def get_db_session():
    """获取当前线程的 DB session（scoped_session）。

    gRPC 线程 / 后台线程均可直接调用，无需 app context。
    线程结束前应调用 `remove_db_session()` 清理（gRPC 由 DbScopeInterceptor 自动处理）。
    """
    return _scoped_session


def remove_db_session():
    """清理当前线程的 DB session（gRPC 拦截器 / 后台线程结束时调用）。"""
    _scoped_session.remove()
