"""
数据库初始化模块 - 共享层

原生 SQLAlchemy 实现（不依赖 Flask-SQLAlchemy）。
通过保留 `db` 命名空间对象提供向后兼容：`db.Model`、`db.session`、`db.Column` 等，
使下游 models.py 与业务代码无需改动。

连接池：create_engine(pool_size, max_overflow, pool_recycle, pool_pre_ping)，
scoped_session 基于 threading.local，线程内复用、跨线程隔离。
"""
import threading

from sqlalchemy import create_engine, func, and_, or_, not_, desc, asc
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker, Query
from sqlalchemy.ext.declarative import DeclarativeMeta

from shared.infrastructure.config import BaseConfig


class _Pagination:
    """模拟 Flask-SQLAlchemy Pagination 对象"""

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
    """Flask-SQLAlchemy 兼容：Query.paginate()"""
    if page is None:
        page = 1
    if per_page is None:
        per_page = 20
    if max_per_page is not None:
        per_page = min(per_page, max_per_page)
    return _Pagination(self, page, per_page, error_out=error_out)


# 给原生 Query 打补丁，添加 paginate 方法
Query.paginate = _query_paginate


class _QueryProperty:
    """模拟 Flask-SQLAlchemy 的 `Model.query` 属性。

    用描述符（descriptor）在类层面代理到 `scoped_session.query(cls)`，
    使 `Model.query.filter_by(...)` 等写法在原生 SQLAlchemy 下可用。
    """

    def __get__(self, instance, owner):
        # owner 是模型类，instance 是实例（类访问时为 None）
        session = _scoped_session_ref[0] if _scoped_session_ref[0] is not None else _scoped_session
        return session.query(owner)

# ── 兼容层：保留 `db` 命名空间 ──────────────────────────────
# db.Model  → declarative_base() 生成的 Base
# db.Column / db.Integer / db.String / ... → 直接 re-export 自 sqlalchemy
# db.session → scoped_session 对象（调用 db.session() 取本线程 session）
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, ForeignKey,
    Boolean, Float, JSON, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship


class _DbNamespace:
    """Flask-SQLAlchemy `db` 对象的兼容替身。

    - `db.Model`：declarative_base() 实例，所有 ORM 模型继承它
    - `db.session`：scoped_session，调用 `db.session()` 取本线程 session
    - `db.Column` / `db.Integer` / ...：原生 sqlalchemy 符号
    - `db.relationship`：sqlalchemy.orm.relationship
    - `db.init_app` / `db.create_all`：兼容旧调用（no-op 或转发）
    """

    def __init__(self, Base, scoped_sess):
        self.Model = Base
        self.session = scoped_sess
        # re-export 常用 sqlalchemy 符号，兼容 `db.Column` 等写法
        self.Column = Column
        self.Integer = Integer
        self.BigInteger = BigInteger
        self.String = String
        self.Text = Text
        self.DateTime = DateTime
        self.ForeignKey = ForeignKey
        self.Boolean = Boolean
        self.Float = Float
        self.JSON = JSON
        self.Index = Index
        self.UniqueConstraint = UniqueConstraint
        self.relationship = relationship
        self.func = func
        self.and_ = and_
        self.or_ = or_
        self.not_ = not_
        self.desc = desc
        self.asc = asc

    def init_app(self, app):
        """兼容 Flask-SQLAlchemy 的 init_app 调用（api_gateway 仍用 Flask）。

        原生 engine 已在 init_db 中建立，这里 no-op，仅为不破坏旧代码。
        """
        # 已在 init_db 中初始化，无需重复
        pass

    def create_all(self, bind=None):
        """兼容旧调用：在指定 engine 上创建所有表。"""
        _engine = bind or _engine_ref[0]
        if _engine_ref[0] is not None:
            self.Model.metadata.create_all(_engine_ref[0])


# 全局 engine 引用（单例，由 init_db 设置）
# 用模块级变量 + getter 函数，替代 [0] 魔法索引，可读性更好
_engine = None
_engine_ref = [None]  # 向后兼容：部分代码仍通过 _engine_ref[0] 访问
_scoped_session_ref = [None]

# Base = declarative_base()
_Base = declarative_base()

# 模拟 Flask-SQLAlchemy 的 `Model.query` 属性
_Base.query = _QueryProperty()

# 初始 scoped_session（在 init_db 之前调用 db.session() 会报错，与原 Flask-SQLAlchemy 一致）
_SessionFactory = sessionmaker(bind=None, autoflush=True, autocommit=False)
_scoped_session = scoped_session(_SessionFactory, scopefunc=threading.get_ident)

# 全局 `db` 对象（兼容 Flask-SQLAlchemy 习惯）
db = _DbNamespace(_Base, _scoped_session)


def get_engine():
    """获取全局 engine 实例（init_db 后可用）"""
    return _engine


def init_db(app=None, pool_size=10):
    """初始化数据库连接池。

    Args:
        app: 可选，Flask 应用实例。保留参数以兼容 api_gateway 的 `init_db(app, ...)` 调用，
             但内部不再依赖 app.config（直接用 BaseConfig.DATABASE_URL）。
        pool_size: 连接池大小

    Returns:
        db 命名空间对象
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
    _engine_ref[0] = engine  # 向后兼容
    _scoped_session_ref[0] = _scoped_session

    return db


def get_db_session():
    """获取当前线程的 DB session（scoped_session）。

    gRPC 线程 / 后台线程均可直接调用，无需 Flask app context。
    线程结束前应调用 `db.session.remove()` 清理（gRPC 由 DbScopeInterceptor 自动处理）。
    """
    return _scoped_session


def remove_db_session():
    """清理当前线程的 DB session（gRPC 拦截器 / 后台线程结束时调用）。"""
    if _scoped_session_ref[0] is not None:
        _scoped_session.remove()
