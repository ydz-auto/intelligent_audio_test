"""
数据库初始化模块 - 共享层

原生 SQLAlchemy 实现。连接池：QueuePool 池类传 pool_size/max_overflow/
pool_recycle/pool_pre_ping，SQLite 内存库（SingletonThreadPool）等非
QueuePool 池类仅传池类兼容参数（INT-48）；scoped_session 的 scope 二级：
HTTP 请求内为请求级 scope（FastAPI 侧 DbSessionScopeMiddleware 在请求开始
bind_request_session_scope、结束 release_request_session_scope，同一线程池
线程先后处理的请求互不共享 session，污染不跨请求存活），gRPC / 后台线程等
未绑定场景回落线程级 scope（threading.get_ident，gRPC 由
ServerDbScopeInterceptor 在 RPC 结束 remove_db_session）。

公开 API：
- `Base`：ORM 基类（declarative_base()），PO 继承它
- `get_db_session()`：取当前 scope 的 scoped_session（毒化自愈兜底）
- `create_db_session()`：创建独立 Session 实例（嵌套调用链专用，close 不影响外层）
- `get_engine()`：取全局 engine（init_db 后可用）
- `init_db(pool_size)`：初始化连接池
- `remove_db_session()`：清理当前 scope 的 session
- `bind_request_session_scope()` / `release_request_session_scope(token)`：
  HTTP 请求级 scope 绑定/解绑+清理（DbSessionScopeMiddleware 专用）
- `Model.query`：描述符，代理到 scoped_session.query(cls)（32 个文件在用）
- `Query.paginate()`：分页补丁（17 处 repository 在用）
"""
import contextvars
import threading
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker, Query
from sqlalchemy.pool import QueuePool

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
    经 get_db_session() 取 session，获得与显式取用一致的毒化自愈兜底。
    """

    def __get__(self, instance, owner):
        # owner 是模型类，instance 是实例（类访问时为 None）
        return get_db_session().query(owner)


# 全局 engine 引用（单例，由 init_db 设置，通过 get_engine() 访问）
_engine = None

_Base = declarative_base()

# 公共基类：PO 定义继承 `Base`
Base = _Base

# `Model.query` 属性：兼容 `Model.query.filter_by(...)` 写法（32 个文件在用）
_Base.query = _QueryProperty()

# HTTP 请求级 session scope：FastAPI 中间件在请求开始绑定一个唯一 scope 键、
# 结束时解绑并 remove 该 scope 的 session（INT-90 缺陷 A——原先按线程复用
# session，线程池线程一旦被事务内失败毒化，后续所有请求持续失败，且事务
# 开着的连接滞留为 idle in transaction）。未绑定场景回落线程级 scope，
# gRPC / 后台线程 / 单测行为同旧版。
_request_session_scope: contextvars.ContextVar = contextvars.ContextVar(
    'request_session_scope', default=None)


def _session_scopefunc():
    """scoped_session 的 scope 键：请求级 ContextVar 优先，否则线程标识。

    ContextVar 经 anyio 线程池下发（sync 路由在 worker 线程执行时可见请求
    scope 键），裸线程（后台任务、gRPC handler 线程）不继承则回落线程键。
    """
    return _request_session_scope.get() or threading.get_ident()


# scoped_session：在 init_db 之前调用 get_db_session() 取到的 session 无绑定 engine
_SessionFactory = sessionmaker(bind=None, autoflush=True, autocommit=False)
_scoped_session = scoped_session(_SessionFactory, scopefunc=_session_scopefunc)


def bind_request_session_scope():
    """绑定当前 HTTP 请求的 session scope（DbSessionScopeMiddleware 调用）。

    返回令牌，请求结束时传给 release_request_session_scope() 解绑。
    """
    return _request_session_scope.set(uuid.uuid4())


def release_request_session_scope(token):
    """解绑请求 scope 并清理该 scope 的 session（DbSessionScopeMiddleware finally 调用）。

    必须先 remove（依赖 scope 仍绑定才能定位本请求的 session）、后 reset。
    """
    try:
        remove_db_session()
    finally:
        _request_session_scope.reset(token)


def get_engine():
    """获取全局 engine 实例（init_db 后可用）"""
    return _engine


def _pool_kwargs(uri, pool_size):
    """按 create_engine 实际将选用的池类装配连接池参数。

    pool_size/max_overflow 是 QueuePool 专属参数：生产（PostgreSQL/MySQL）
    与 SQLite 文件库的默认池类均为 QueuePool，参数照传、行为不变；SQLite
    内存库的默认池类是 SingletonThreadPool，仅接受 Pool 基类参数
    （pool_recycle/pool_pre_ping），传入 QueuePool 专属参数即 TypeError
    （INT-48）。
    """
    pool_kwargs = {
        'pool_recycle': 3600,
        'pool_pre_ping': True,
    }
    url = make_url(uri)
    if issubclass(url.get_dialect().get_pool_class(url), QueuePool):
        pool_kwargs.update({'pool_size': pool_size, 'max_overflow': 5})
    return pool_kwargs


def init_db(pool_size=3):
    """初始化数据库连接池。

    Args:
        pool_size: 连接池大小（默认 3，配合 max_overflow=5 上限 8 条，控制内存占用；
            仅 QueuePool 池类生效，SQLite 内存库等非 QueuePool 池类忽略）

    Returns:
        scoped_session 对象
    """
    global _engine
    uri = BaseConfig.DATABASE_URL
    if not uri:
        raise RuntimeError('未配置 DATABASE_URL 环境变量')

    engine = create_engine(
        uri,
        **_pool_kwargs(uri, pool_size),
    )

    # 绑定 session 工厂到 engine
    _SessionFactory.configure(bind=engine)

    # 持有全局引用，防止 GC
    _engine = engine

    return _scoped_session


def get_db_session():
    """获取当前 scope 的 DB session（HTTP 请求级 / 线程级 scoped_session）。

    HTTP 请求内为请求级 session（DbSessionScopeMiddleware 自动绑定/清理）；
    gRPC 线程 / 后台线程为线程级 session（线程结束前应调用 remove_db_session()，
    gRPC 由 ServerDbScopeInterceptor 自动处理）。

    毒化自愈兜底（INT-90 缺陷 A）：事务内前序语句失败（如 audit 写库类型错
    flush 失败）会把 session 毒化为 PendingRollbackError 状态（is_active=False），
    原先按线程复用该 session 时，毒化跨请求存活——同线程/同 scope 后续所有
    请求持续失败。获取时检测到非活跃先 rollback 解毒。
    """
    if not _scoped_session.is_active:
        try:
            _scoped_session.rollback()
        except Exception:
            remove_db_session()
    return _scoped_session


def create_db_session():
    """创建独立 Session 实例（非线程 scoped_session，嵌套调用链专用）。

    同线程内 `get_db_session()` 恒返回同一个 session，嵌套链路对它 close()
    会 expunge 全部实例，使外层仍持有的 ORM 对象脱管（已被 commit 过期的
    对象再访问属性即抛 DetachedInstanceError，见 INT-40）。独立 Session 的
    close 只释放自己的连接与实例，不影响外层。
    """
    return _SessionFactory()


def remove_db_session():
    """清理当前 scope 的 DB session（gRPC 拦截器 / 请求中间件 / 后台线程结束时调用）。"""
    _scoped_session.remove()
