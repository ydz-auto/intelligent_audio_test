# -*- coding: utf-8 -*-
"""数据库 session 管理与软删除工具

提供装饰器和 Mixin，消除各 repository 中重复的 session 管理模板
（try / commit / rollback / close）和软删除过滤逻辑。

使用方式::

    from shared.utils.db_session import with_session, not_deleted, SoftDeleteMixin

    class TaskRepository(SoftDeleteMixin, TaskRepositoryABC):
        PO_CLASS = Task

        @with_session
        def get_by_id(self, task_id: int):
            po = get_db_session().get(Task, task_id)
            return _po_to_entity(po) if po else None

        @with_session(auto_commit=True)
        def save(self, aggregate):
            po = get_db_session().get(Task, aggregate.id)
            _apply_to_po(aggregate, po)

        # soft_delete(id) 由 SoftDeleteMixin 自动提供
"""
from __future__ import annotations

import functools
import logging
from typing import Any, Type

from sqlalchemy.orm import Query

from shared.models.database import get_db_session, utc8now

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# @with_session 装饰器
# ------------------------------------------------------------------

def with_session(func=None, *, auto_commit: bool = False, rollback_on_error: bool = True):
    """装饰器：自动管理 DB session 生命周期。

    统一处理 try / commit / rollback / close 模板，消除 40+ 处重复。

    同时支持两种用法::

        @with_session                # 读操作（无括号）
        @with_session(auto_commit=True)  # 写操作（带参数）

    Args:
        func: 被装饰函数（无括号用法时由解释器自动传入）。
        auto_commit: 写操作设为 True，方法成功后自动 commit；
                     读操作设为 False（默认），仅 close。
        rollback_on_error: 异常时是否 rollback，默认 True。

    被装饰方法内部直接使用 ``get_db_session()`` 获取 session，
    无需再手写 try/except/finally。

    用法::

        @with_session(auto_commit=True)
        def save(self, aggregate):
            po = get_db_session().get(Task, aggregate.id)
            _apply_to_po(aggregate, po)
            return aggregate.id
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            session = get_db_session()
            try:
                result = f(*args, **kwargs)
                if auto_commit:
                    session.commit()
                return result
            except Exception:
                if rollback_on_error:
                    session.rollback()
                raise
            finally:
                session.close()

        return wrapper

    # 兼容 @with_session 无括号用法：func 直接是callable
    if func is not None and callable(func):
        return decorator(func)

    return decorator


# ------------------------------------------------------------------
# 软删除过滤工具
# ------------------------------------------------------------------

def not_deleted(query: Query) -> Query:
    """在 query 上追加 ``deleted == False`` 过滤。

    消除各 repository 中 60+ 处 ``filter(Model.deleted == False)  # noqa: E712``
    和 ``filter_by(deleted=False)`` 重复写法。

    用法::

        from shared.utils.db_session import not_deleted

        query = not_deleted(session.query(Task)).filter(Task.status == 'running')
    """
    # 尝试从 query 的主实体获取 deleted 列
    try:
        entity = query.column_descriptions[0]['entity']
        if entity is None:
            return query
        deleted_col = getattr(entity, 'deleted', None)
        if deleted_col is not None:
            return query.filter(deleted_col == False)  # noqa: E712
    except (IndexError, KeyError, AttributeError):
        logger.debug("查询软删除列失败，跳过 deleted 过滤", exc_info=True)
    return query


def filter_active(session, model_cls: Type) -> Query:
    """快捷方法：查询未删除记录。

    等价于 ``session.query(model_cls).filter(model_cls.deleted == False)``。

    用法::

        from shared.utils.db_session import filter_active

        po = filter_active(session, Task).filter_by(id=task_id).first()
    """
    query = session.query(model_cls)
    deleted_col = getattr(model_cls, 'deleted', None)
    if deleted_col is not None:
        query = query.filter(deleted_col == False)  # noqa: E712
    return query


# ------------------------------------------------------------------
# SoftDeleteMixin
# ------------------------------------------------------------------

class SoftDeleteMixin:
    """软删除通用 Mixin。

    为 DDD 风格 repository 提供通用的 ``soft_delete(id)`` 方法，
    消除 4 处 DDD repository + 5 处 ACL repository 的重复。

    子类需设置类属性 ``PO_CLASS`` 指向 ORM 模型类。

    用法::

        class TaskRepository(SoftDeleteMixin, TaskRepositoryABC):
            PO_CLASS = Task
            # soft_delete 方法自动提供
    """

    PO_CLASS: Type = None

    @with_session(auto_commit=True)
    def soft_delete(self, entity_id: int, deleted_by: int | None = None) -> bool:
        """软删除指定 ID 的记录。

        统一盖 deleted_at（回收站/保留期清理依赖该时间戳；INT-141 起所有
        软删路径必须盖时间与操作人，单一删除不再裸置 deleted=True）。
        deleted_by 未显式传入时从 x-user-id 上下文取当前操作人。

        Args:
            entity_id: 记录 ID
            deleted_by: 操作人用户 ID（JWT；未认证/AUTH_MODE=off 为 None）

        Returns:
            True 如果记录存在且已标记删除；False 如果记录不存在。
        """
        from shared.infrastructure.user_context import get_current_user_id
        session = get_db_session()
        po = session.get(self.PO_CLASS, entity_id)
        if po is None:
            return False
        po.deleted = True
        if getattr(self.PO_CLASS, 'deleted_at', None) is not None:
            po.deleted_at = utc8now()
        if deleted_by is None:
            deleted_by = get_current_user_id()
        if deleted_by is not None and getattr(self.PO_CLASS, 'deleted_by_user_id', None) is not None:
            po.deleted_by_user_id = deleted_by
        return True

    @with_session(auto_commit=True)
    def bulk_soft_delete(self, ids: list, deleted_by: int | None = None) -> int:
        """批量软删除（时间戳/操作人语义与 soft_delete 一致）。

        Args:
            ids: 待删除的 ID 列表
            deleted_by: 操作人用户 ID（JWT；未认证/AUTH_MODE=off 为 None）

        Returns:
            实际删除的条数
        """
        from shared.infrastructure.user_context import get_current_user_id
        if not ids:
            return 0
        session = get_db_session()
        updates = {self.PO_CLASS.deleted: True}
        if getattr(self.PO_CLASS, 'deleted_at', None) is not None:
            updates[self.PO_CLASS.deleted_at] = utc8now()
        if deleted_by is None:
            deleted_by = get_current_user_id()
        if deleted_by is not None and getattr(self.PO_CLASS, 'deleted_by_user_id', None) is not None:
            updates[self.PO_CLASS.deleted_by_user_id] = deleted_by
        count = session.query(self.PO_CLASS).filter(
            self.PO_CLASS.id.in_(ids)
        ).update(updates, synchronize_session=False)
        return count
