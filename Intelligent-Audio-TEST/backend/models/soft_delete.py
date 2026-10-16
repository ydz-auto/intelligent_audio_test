"""
软删除统一入口模块 (Soft Delete Single Entry Point)

本模块是 `deleted` 语义的**唯一定义处**。业务代码禁止再逐处手写
`filter(Model.deleted == False)` 或逐处手写软删打标——历史上正因为逐处手写，
才出现「报告路径过滤、执行路径不过滤」的口径漂移（同一用例能跑、却被报告静默剔除）。

三层职责：

1. 列定义 —— `SoftDeleteMixin` 统一提供 `deleted / deleted_at / created_by_user_id /
   updated_by_user_id` 四列；模型只要继承该 Mixin 即获得完整软删能力。
2. 查询过滤 —— 注册进 `SOFT_DELETE_FILTERED_MODELS` 的模型，其所有 ORM SELECT
   （含 `session.get()` / `Query.get()` / 懒加载关系）自动附加 `deleted = false`，
   因此「建任务 / 执行 / 报告 / 发布任务」四条路径天然同口径。
   需要读取软删行的场景（回收站列表、导入恢复、审计查询）必须显式用
   `include_deleted()` 或 `execution_options(include_deleted=True)` 放开——
   放开是**显式**的，不会再出现"某处忘了过滤"的静默漂移。
3. 删除审计 —— `before_flush` 统一拦截：任何实例 `deleted` 由 false 翻转为 true 时，
   写 `deleted_at = utc8now()`（东八区）与操作人；恢复（true→false）时清空 `deleted_at`。
   删除动作由此在整个 schema 上留下痕迹，不再依赖各控制器自觉。
   **注意**：bulk `Query.update()` 不走 ORM 事件，批量删除与级联删除必须改调
   `bulk_soft_delete()`，否则会成为审计盲区。

架构层次: Flask Model Layer（共享基础设施）
"""
from contextlib import contextmanager

from sqlalchemy import BigInteger, Boolean, Column, DateTime, event
from sqlalchemy.orm import Session, with_loader_criteria

# 放开软删过滤的执行选项名（statement 级 / 会话级均可）
INCLUDE_DELETED_OPTION = 'include_deleted'

# 会话级放开标记（挂在 Session 实例上，供 include_deleted() 上下文管理器使用）
_SESSION_FLAG = '_include_soft_deleted'

# 需要全局过滤软删行的模型注册表。
# 新增模型 = 在这里登记一行，四条路径自动同口径；不需要改任何控制器。
SOFT_DELETE_FILTERED_MODELS = []


class SoftDeleteMixin:
    """软删除 Mixin：统一 deleted 标志与删除审计列。

    对应数据库既有列（deleted / deleted_at / created_by_user_id / updated_by_user_id），
    继承后无需在各模型里重复声明。
    """
    deleted = Column(Boolean, nullable=False, default=False, comment='逻辑删除标志')
    deleted_at = Column(DateTime, comment='逻辑删除时间（软删时由 soft_delete 统一写入）')
    created_by_user_id = Column(BigInteger, comment='创建人用户ID（无认证体系时为 NULL）')
    updated_by_user_id = Column(BigInteger, comment='更新/删除人用户ID（无认证体系时为 NULL）')


def register_soft_delete_filter(*models):
    """把模型登记进全局软删过滤表（幂等）。"""
    for model in models:
        if model not in SOFT_DELETE_FILTERED_MODELS:
            SOFT_DELETE_FILTERED_MODELS.append(model)


def _utc8now():
    # 延迟导入：models.py 反向依赖本模块，模块级导入会成环
    from backend.models.models import utc8now
    return utc8now()


def _resolve_session(session):
    """把 scoped_session / sessionmaker 解析成真正的 Session 实例。"""
    if session is None:
        from backend.models.database import db
        session = db.session
    if isinstance(session, Session):
        return session
    if callable(session):
        return session()
    return session


@contextmanager
def include_deleted(session=None):
    """在 with 块内放开软删过滤（回收站 / 恢复 / 审计场景）。

    用法::

        with include_deleted():
            row = db.session.get(TestCase, soft_deleted_id)

    只影响当前 Session，退出后恢复原状态（可嵌套）。
    """
    real_session = _resolve_session(session)
    previous = real_session.info.get(_SESSION_FLAG, False)
    real_session.info[_SESSION_FLAG] = True
    try:
        yield real_session
    finally:
        if previous:
            real_session.info[_SESSION_FLAG] = True
        else:
            real_session.info.pop(_SESSION_FLAG, None)


def _soft_delete_filter_enabled(execute_state):
    """判断当前语句是否要附加软删过滤。"""
    if not execute_state.is_select or not execute_state.is_orm_statement:
        return False
    # 列加载（refresh 等）由对象既有状态决定，不重复附加
    if execute_state.is_column_load:
        return False
    if execute_state.execution_options.get(INCLUDE_DELETED_OPTION, False):
        return False
    session = execute_state.session
    if session is not None and session.info.get(_SESSION_FLAG, False):
        return False
    return bool(SOFT_DELETE_FILTERED_MODELS)


@event.listens_for(Session, 'do_orm_execute')
def _apply_soft_delete_filter(execute_state):
    """全局软删过滤：单一入口，杜绝逐路径手写过滤的漂移。"""
    if not _soft_delete_filter_enabled(execute_state):
        return
    execute_state.statement = execute_state.statement.options(*[
        with_loader_criteria(
            model,
            lambda cls: cls.deleted.is_(False),
            include_aliases=True,
        )
        for model in SOFT_DELETE_FILTERED_MODELS
    ])


def _query_entity(query):
    """取 legacy Query 的主体模型（取不到返回 None）。"""
    try:
        descriptions = query.column_descriptions
    except Exception:
        return None
    if not descriptions:
        return None
    return descriptions[0].get('entity')


def bulk_soft_delete(query, operator_user_id=None):
    """批量 / 级联软删的统一入口。

    bulk `Query.update()` 直接构造 Core UPDATE，**不经过 ORM 的 `before_flush`**，
    因此 `_apply_soft_delete_audit` 拦不到它——逐处手写 `update({"deleted": True})`
    会让批量删除与级联删除成为审计盲区（`deleted_at` 永远为 NULL）。
    凡批量或级联软删一律走本函数，与单条删除留下同样的痕迹。

    **幂等守卫内聚在本函数**：只打标 `deleted == False` 的行，重复软删（例如标签级联
    时关联表里还留着已软删用例的 id）不会覆盖首次写入的 `deleted_at` 与操作人。
    调用方**不需要**自己再加守卫——守卫只有一处，才不会再出现「同一张卡内三种写法」。

    用法::

        bulk_soft_delete(TestCase.query.filter(TestCase.id.in_(ids)))

    :param query: 待软删行的 legacy `Query`（调用方负责提交事务）
    :param operator_user_id: 操作人；默认按当前请求上下文解析（无认证体系时为 None，不伪造身份）
    :return: 受影响行数（仅计本次真正由未删转为已删的行）
    """
    from backend.utils.web.operator import current_operator_user_id

    entity = _query_entity(query)
    if entity is not None and hasattr(entity, 'deleted'):
        # 幂等守卫：重复软删不覆盖首次的 deleted_at / updated_by_user_id
        query = query.filter(entity.deleted.is_(False))

    if operator_user_id is None:
        operator_user_id = current_operator_user_id()

    values = {'deleted': True, 'deleted_at': _utc8now()}
    if operator_user_id is not None:
        values['updated_by_user_id'] = operator_user_id
    return query.update(values, synchronize_session=False)


def _set_operator(obj, mapper, operator_user_id):
    """写操作人字段（无认证体系时为 None，不伪造身份）。"""
    if 'updated_by_user_id' in mapper.attrs:
        obj.updated_by_user_id = operator_user_id


def _stamp_soft_delete(session, operator_user_id):
    """软删 / 恢复状态翻转时统一打标。"""
    from sqlalchemy import inspect as sa_inspect

    for obj in session.dirty:
        state = sa_inspect(obj)
        mapper = state.mapper
        if 'deleted' not in mapper.attrs or 'deleted_at' not in mapper.attrs:
            continue
        history = state.attrs.deleted.history
        if not history.has_changes():
            continue
        added = history.added[0] if history.added else None
        if added is None:
            continue
        if bool(added):
            # 软删：写删除时间 + 操作人
            obj.deleted_at = _utc8now()
            _set_operator(obj, mapper, operator_user_id)
        else:
            # 恢复：清空删除痕迹
            obj.deleted_at = None
            _set_operator(obj, mapper, operator_user_id)


def _stamp_created_by(session, operator_user_id):
    """新增时写创建人（无认证体系时保持 NULL，不伪造身份）。"""
    from sqlalchemy import inspect as sa_inspect

    for obj in session.new:
        mapper = sa_inspect(obj).mapper
        if 'created_by_user_id' not in mapper.attrs:
            continue
        if getattr(obj, 'created_by_user_id', None) is None:
            obj.created_by_user_id = operator_user_id


@event.listens_for(Session, 'before_flush')
def _apply_soft_delete_audit(session, flush_context, instances):
    """软删审计统一入口：覆盖所有继承 SoftDeleteMixin 的模型的软删入口。"""
    from backend.utils.web.operator import current_operator_user_id
    operator_user_id = current_operator_user_id()
    _stamp_soft_delete(session, operator_user_id)
    _stamp_created_by(session, operator_user_id)
