# -*- coding: utf-8 -*-
"""回收站仓储（INT-141，task_service 分治域：task|testcase）

- 列表：deleted=True 项 + 删除人/删除时间
- 恢复：单个+批量统一入口（复用 batch_restore 口径：deleted=False、deleted_at=None）
- purge：物理删除，子→父顺序对齐 TaskServiceCleaner.hard_delete_expired；
  purge 仅针对当前处于软删除状态的行，活跃行不受影响

SQL 写法跨库兼容（PostgreSQL 生产 / SQLite 测试）：模糊匹配用
``lower(col) LIKE lower(:kw)``，不使用 ILIKE。
"""
from sqlalchemy import text, bindparam

from shared.infrastructure.purge_permission import filter_purgeable_owners
from shared.infrastructure.user_context import get_current_user_id
from shared.models.database import get_db_session, utc8now
from shared.utils.db_session import with_session


def _bind_in(sql: str):
    return text(sql).bindparams(bindparam('ids', expanding=True))


class TrashRepository:
    """test_tasks / test_cases 回收站读写"""

    # ------------------------------------------------------------------
    # 任务
    # ------------------------------------------------------------------
    @with_session(auto_commit=False)
    def list_deleted_tasks(self, page: int = 1, per_page: int = 20, search: str | None = None) -> dict:
        session = get_db_session()
        where = "WHERE deleted = TRUE"
        params = {}
        if search:
            where += " AND (lower(name) LIKE lower(:kw) OR lower(CAST(id AS VARCHAR)) LIKE lower(:kw))"
            params['kw'] = f"%{search}%"
        total = session.execute(
            text(f"SELECT COUNT(*) FROM test_tasks {where}"), params).scalar() or 0
        rows = session.execute(text(
            f"SELECT id, name, algorithm_type, status, deleted_at, deleted_by_user_id "
            f"FROM test_tasks {where} "
            f"ORDER BY deleted_at DESC LIMIT :lim OFFSET :off"),
            {**params, 'lim': per_page, 'off': (page - 1) * per_page}).mappings().all()
        return {'total': int(total), 'items': [dict(r) for r in rows]}

    @with_session(auto_commit=True)
    def restore_tasks(self, task_ids: list) -> int:
        """恢复任务（仅恢复当前处于软删除状态的行；回填 updated_by 记录恢复人）"""
        if not task_ids:
            return 0
        session = get_db_session()
        count = session.execute(
            text("UPDATE test_tasks SET deleted = FALSE, deleted_at = NULL, "
                 "deleted_by_user_id = NULL, updated_by_user_id = :uid "
                 "WHERE id IN :ids AND deleted = TRUE").bindparams(
                bindparam('ids', expanding=True)),
            {"ids": [int(i) for i in task_ids],
             'uid': get_current_user_id()}).rowcount
        return int(count or 0)

    @with_session(auto_commit=True)
    def purge_tasks(self, task_ids: list, user_id=None, is_admin: bool = False) -> int:
        """彻底删除任务及关联数据（子→父，对齐 TaskServiceCleaner）。

        权限收敛（INT-141，审计 P2-1）：admin 放行整批；非 admin 逐行校验
        owner（创建人/删除人）——非 owned 行跳过不删，全非 owned 抛
        PurgePermissionDenied（HTTP 403）。
        """
        if not task_ids:
            return 0
        session = get_db_session()
        ids = [int(i) for i in task_ids]
        # 仅对软删除行执行 purge；活跃行直接跳过（防误删）
        rows = session.execute(
            text("SELECT id, created_by_user_id, deleted_by_user_id FROM test_tasks "
                 "WHERE id IN :ids AND deleted = TRUE").bindparams(
                bindparam('ids', expanding=True)), {"ids": ids}).all()
        if not rows:
            return 0
        # 逐行 owner 过滤（审计 P2-1）：非 admin 仅 purge 自己创建/删除的行，
        # 非_owned 行跳过（体现在返回计数），全非_owned 抛 403 语义异常
        purgeable = filter_purgeable_owners(rows, user_id, is_admin)
        # 关联表与子表
        session.execute(_bind_in("DELETE FROM task_tags WHERE task_id IN :ids"), {"ids": purgeable})
        session.execute(_bind_in("DELETE FROM task_case_relations WHERE task_id IN :ids"), {"ids": purgeable})
        session.execute(_bind_in("DELETE FROM task_device_relations WHERE task_id IN :ids"), {"ids": purgeable})
        session.execute(_bind_in("DELETE FROM task_api_relations WHERE task_id IN :ids"), {"ids": purgeable})
        session.execute(text(
            "DELETE FROM task_merge_relations "
            "WHERE merged_task_id IN :ids OR source_task_id IN :ids").bindparams(
            bindparam('ids', expanding=True)), {"ids": purgeable})
        session.execute(_bind_in("DELETE FROM test_results WHERE task_id IN :ids"), {"ids": purgeable})
        session.execute(_bind_in("DELETE FROM logs WHERE task_id IN :ids"), {"ids": purgeable})
        # 收藏悬挂引用清理
        session.execute(text(
            "DELETE FROM favorites WHERE entity_type = 'task' "
            "AND entity_id IN :sids").bindparams(bindparam('sids', expanding=True)),
            {"sids": [str(i) for i in purgeable]})
        # 主表
        session.execute(_bind_in("DELETE FROM test_tasks WHERE id IN :ids"), {"ids": purgeable})
        return len(purgeable)

    # ------------------------------------------------------------------
    # 用例
    # ------------------------------------------------------------------
    @with_session(auto_commit=False)
    def list_deleted_testcases(self, page: int = 1, per_page: int = 20, keyword: str | None = None) -> dict:
        session = get_db_session()
        where = "WHERE deleted = TRUE"
        params = {}
        if keyword:
            where += " AND (lower(name) LIKE lower(:kw) OR lower(id) LIKE lower(:kw))"
            params['kw'] = f"%{keyword}%"
        total = session.execute(
            text(f"SELECT COUNT(*) FROM test_cases {where}"), params).scalar() or 0
        rows = session.execute(text(
            f"SELECT id, name, algorithm_type, deleted_at, deleted_by_user_id "
            f"FROM test_cases {where} "
            f"ORDER BY deleted_at DESC LIMIT :lim OFFSET :off"),
            {**params, 'lim': per_page, 'off': (page - 1) * per_page}).mappings().all()
        return {'total': int(total), 'items': [dict(r) for r in rows]}

    @with_session(auto_commit=True)
    def restore_testcases(self, case_ids: list) -> int:
        """恢复用例（衔接 testcase 批量恢复口径；回填 updated_by 记录恢复人）"""
        if not case_ids:
            return 0
        session = get_db_session()
        count = session.execute(
            text("UPDATE test_cases SET deleted = FALSE, deleted_at = NULL, "
                 "deleted_by_user_id = NULL, updated_by_user_id = :uid, updated_at = :now "
                 "WHERE id IN :ids AND deleted = TRUE").bindparams(
                bindparam('ids', expanding=True)),
            {"ids": [str(i) for i in case_ids], 'now': utc8now(),
             'uid': get_current_user_id()}).rowcount
        return int(count or 0)

    @with_session(auto_commit=True)
    def purge_testcases(self, case_ids: list, user_id=None, is_admin: bool = False) -> int:
        """彻底删除用例及关联数据（子→父，对齐 TaskServiceCleaner.test_cases 段）。

        权限收敛（INT-141，审计 P2-1）：逐行 owner 校验，同 purge_tasks。
        """
        if not case_ids:
            return 0
        session = get_db_session()
        ids = [str(i) for i in case_ids]
        rows = session.execute(
            text("SELECT id, created_by_user_id, deleted_by_user_id FROM test_cases "
                 "WHERE id IN :ids AND deleted = TRUE").bindparams(
                bindparam('ids', expanding=True)), {"ids": ids}).all()
        if not rows:
            return 0
        # 逐行 owner 过滤（审计 P2-1），同 purge_tasks
        purgeable = filter_purgeable_owners(rows, user_id, is_admin)
        session.execute(_bind_in("DELETE FROM test_case_tags WHERE test_case_id IN :ids"), {"ids": purgeable})
        session.execute(_bind_in("DELETE FROM task_case_relations WHERE test_case_id IN :ids"), {"ids": purgeable})
        session.execute(_bind_in("DELETE FROM test_results WHERE test_case_id IN :ids"), {"ids": purgeable})
        session.execute(_bind_in("DELETE FROM logs WHERE test_case_id IN :ids"), {"ids": purgeable})
        session.execute(text(
            "DELETE FROM favorites WHERE entity_type = 'testcase' "
            "AND entity_id IN :sids").bindparams(bindparam('sids', expanding=True)),
            {"sids": purgeable})
        session.execute(_bind_in("DELETE FROM test_cases WHERE id IN :ids"), {"ids": purgeable})
        return len(purgeable)


# 单例
trash_repository = TrashRepository()
