# -*- coding: utf-8 -*-
"""INT-141 专项：收藏 / 回收站 / CUD 操作人记录。

覆盖：
- 收藏（per-user）：A 用户收藏对 B 不可见；重复收藏幂等（already_favorited）；
  取消收藏幂等；非法实体类型拒绝（favorites 按服务分治：task_service 仅
  task|testcase）；收藏过滤（favorite=true）只命中当前用户收藏项
- 回收站：删除（含删除人/删除时间）→ 回收站可见 → 恢复（单个+批量）→
  purge 全链；purge 仅 admin/owner（非 owner 非 admin 抛权限拒绝）；purge
  清理收藏悬挂引用
- 操作人列：dev 上下文 create/update/delete/批量 每步 user_id 正确；
  无上下文（AUTH_MODE=off 等价）列保持 NULL，不硬编码 0 充当真实用户

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表，
用例内自行清理，对齐 test_int65_task_testcase_restore.py 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.infrastructure.user_context import (
    set_current_user_id, get_current_user_id, normalize_user_id,
    user_id_metadata, user_admin_metadata,
)
from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session, utc8now,
)
from shared.infrastructure.purge_permission import (
    check_purge_permission, PurgePermissionDenied,
)


# ---------------- 工具 ----------------

_TASK_TABLES = None
_CASE_TABLES = None
_REPORT_TABLES = None


def _ensure_db():
    init_db(pool_size=2)


def _ensure_task_tables():
    _ensure_db()
    global _TASK_TABLES
    if _TASK_TABLES is None:
        from task_service.infrastructure.persistence.models import (
            Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation,
            TestResult, Tag, TagCategory, TestCaseGroup, TestCase, TestCaseTag,
            Favorite, Log,
        )
        # INT-337：purge 级联下探孙代 TRD（test_result_dimensions 归属
        # evaluation_service，与 test_results 同库；夹具须一并建表）
        from evaluation_service.infrastructure.persistence.models import (
            TestResultDimension,
        )
        _TASK_TABLES = [t.__table__ for t in (
            Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation,
            TestResult, TestResultDimension, TagCategory, Tag, TestCaseGroup,
            TestCase, TestCaseTag, Favorite, Log,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_TASK_TABLES)
    return _TASK_TABLES


def _ensure_report_tables():
    _ensure_db()
    global _REPORT_TABLES
    if _REPORT_TABLES is None:
        from report_service.infrastructure.persistence.models import (
            Report, ReportSummary, ReportSummaryMeta, ReportRawData,
            ReportCase, ReportMetricStats, ReportComparisonMatrix, ReportFavorite,
        )
        _REPORT_TABLES = [t.__table__ for t in (
            Report, ReportSummary, ReportSummaryMeta, ReportRawData,
            ReportCase, ReportMetricStats, ReportComparisonMatrix, ReportFavorite,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_REPORT_TABLES)
    return _REPORT_TABLES


def _cleanup_tables(tables):
    session = get_db_session()
    try:
        for table in tables:
            session.execute(table.delete())
        session.commit()
    finally:
        remove_db_session()


# ---------------- 用户上下文 ----------------

class TestUserContext:
    """x-user-id 上下文与归一化红线。"""

    def test_normalize_falsy_and_zero_not_real_user(self):
        assert normalize_user_id(None) is None
        assert normalize_user_id(0) is None
        assert normalize_user_id('0') is None
        assert normalize_user_id('') is None
        assert normalize_user_id('abc') is None

    def test_normalize_valid_ids(self):
        assert normalize_user_id('5') == 5
        assert normalize_user_id(42) == 42

    def test_set_get_and_metadata(self):
        set_current_user_id('7')
        assert get_current_user_id() == 7
        assert user_id_metadata() == [('x-user-id', '7')]
        set_current_user_id(0)
        assert get_current_user_id() is None
        assert user_id_metadata() == []
        set_current_user_id(None)

    def test_admin_metadata_only_when_true(self):
        from shared.infrastructure.user_context import (
            set_current_user_is_admin, get_current_user_is_admin,
        )
        set_current_user_is_admin(True)
        assert user_admin_metadata() == [('x-user-is-admin', 'true')]
        assert get_current_user_is_admin() is True
        set_current_user_is_admin(False)
        assert user_admin_metadata() == []
        set_current_user_is_admin(False)


class TestPurgePermission:
    """purge 权限收敛：admin / owner 双通道。"""

    def test_admin_allowed(self):
        check_purge_permission(999, True, [1, 2])

    def test_owner_allowed(self):
        check_purge_permission(2, False, [1, 2])

    def test_non_owner_rejected(self):
        with pytest.raises(PurgePermissionDenied):
            check_purge_permission(999, False, [1, 2])

    def test_unauthenticated_rejected(self):
        with pytest.raises(PurgePermissionDenied):
            check_purge_permission(None, False, [1, 2])


# ---------------- 收藏 ----------------

class TestFavoritesTaskDomain:
    """task_service 收藏：per-user 语义 + 幂等 + 分治域校验。"""

    def setup_method(self):
        _ensure_task_tables()

    def teardown_method(self):
        _cleanup_tables(_TASK_TABLES)

    def test_favorite_idempotent_and_per_user_isolated(self):
        from task_service.infrastructure.persistence.favorite_repository import favorite_repository
        from task_service.infrastructure.persistence.models import Task

        session = get_db_session()
        try:
            task = Task(name='INT141_收藏任务', status='pending', total_cases=0)
            session.add(task)
            session.commit()
            tid = task.id
        finally:
            remove_db_session()

        # A 收藏
        r1 = favorite_repository.add(101, 'task', str(tid))
        assert r1['success'] is True and r1['already_favorited'] is False
        # 重复收藏幂等
        r2 = favorite_repository.add(101, 'task', str(tid))
        assert r2['success'] is True and r2['already_favorited'] is True
        # B 不可见 A 的收藏
        assert favorite_repository.list_ids(102, 'task') == []
        assert favorite_repository.list_ids(101, 'task') == [str(tid)]
        # B 也可独立收藏同一实体（per-user）
        r3 = favorite_repository.add(102, 'task', str(tid))
        assert r3['success'] is True and r3['already_favorited'] is False
        assert sorted(favorite_repository.list_ids(101, 'task')) == [str(tid)]

        # 取消收藏幂等
        r4 = favorite_repository.remove(101, 'task', str(tid))
        assert r4['success'] is True and r4['removed'] == 1
        r5 = favorite_repository.remove(101, 'task', str(tid))
        assert r5['success'] is True and r5['removed'] == 0
        # B 的收藏不受影响（per-user）
        assert favorite_repository.list_ids(102, 'task') == [str(tid)]

    def test_favorite_unauthenticated_rejected(self):
        from task_service.infrastructure.persistence.favorite_repository import favorite_repository
        with pytest.raises(ValueError):
            favorite_repository.add(None, 'task', '1')

    def test_favorite_entity_must_exist_and_active(self):
        from task_service.infrastructure.persistence.favorite_repository import favorite_repository
        r = favorite_repository.add(101, 'task', '999999')
        assert r['success'] is False and r.get('code') == 404

    def test_favorite_entity_type_confined_to_domain(self):
        """分治红线：report 归 report_service，task_service 拒绝。"""
        from task_service.infrastructure.persistence.favorite_repository import favorite_repository
        with pytest.raises(ValueError):
            favorite_repository.add(101, 'report', '1')

    def test_favorite_testcase(self):
        from task_service.infrastructure.persistence.favorite_repository import favorite_repository
        from task_service.infrastructure.persistence.models import TestCase

        session = get_db_session()
        try:
            session.add(TestCase(id='INT141_FAV_CASE', name='收藏用例',
                                 config={}, deleted=False))
            session.commit()
        finally:
            remove_db_session()

        r = favorite_repository.add(101, 'testcase', 'INT141_FAV_CASE')
        assert r['success'] is True and r['already_favorited'] is False
        assert favorite_repository.list_ids(101, 'testcase') == ['INT141_FAV_CASE']


class TestFavoriteFilter:
    """列表 favorite=true 过滤只命中当前用户收藏项。"""

    def setup_method(self):
        _ensure_task_tables()

    def teardown_method(self):
        _cleanup_tables(_TASK_TABLES)

    def test_task_list_favorite_filter(self):
        from task_service.infrastructure.persistence.models import Task, Favorite
        from task_service.infrastructure.read_models.task_read_model import task_read_model

        session = get_db_session()
        try:
            t1 = Task(name='INT141_收藏过滤A', status='pending', total_cases=0)
            t2 = Task(name='INT141_收藏过滤B', status='pending', total_cases=0)
            session.add_all([t1, t2])
            session.commit()
            tids = (t1.id, t2.id)
        finally:
            remove_db_session()

        # 用户 101 收藏 t2
        set_current_user_id(101)
        try:
            session = get_db_session()
            try:
                session.add(Favorite(user_id=101, entity_type='task',
                                     entity_id=str(tids[1])))
                session.commit()
            finally:
                remove_db_session()

            result = task_read_model.search_tasks(user_id=101, favorite=True, page=1, per_page=10)
            assert result['total'] == 1
            assert result['items'][0]['id'] == tids[1]
            assert result['items'][0]['is_favorite'] is True

            # 未收藏用户 favorite=true → 空
            empty = task_read_model.search_tasks(user_id=202, favorite=True)
            assert empty['total'] == 0
            # 未认证 favorite=true → 空（不报错）
            noauth = task_read_model.search_tasks(user_id=None, favorite=True)
            assert noauth['total'] == 0
        finally:
            set_current_user_id(None)

    def test_testcase_list_favorite_and_only_deleted(self):
        from task_service.infrastructure.persistence.models import TestCase, Favorite
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository

        session = get_db_session()
        try:
            session.add_all([
                TestCase(id='INT141_F1', name='收藏命中', config={}),
                TestCase(id='INT141_F2', name='未收藏', config={}),
            ])
            session.add(Favorite(user_id=303, entity_type='testcase', entity_id='INT141_F1'))
            session.commit()
        finally:
            remove_db_session()

        page = testcase_repository.query_testcases(favorite=True, user_id=303)
        assert page.total == 1
        assert page.items[0].id == 'INT141_F1'

        # 删除后 only_deleted 命中
        testcase_repository.soft_delete_testcases_by_ids(['INT141_F1'])
        testcase_repository.commit()
        del_page = testcase_repository.query_testcases(only_deleted=True)
        assert {tc.id for tc in del_page.items} == {'INT141_F1'}
        # only_deleted 时活跃项不出现
        active_page = testcase_repository.query_testcases()
        assert 'INT141_F1' not in {tc.id for tc in active_page.items}

    def test_testcase_list_grpc_handler_chain_accepts_favorite(self):
        """回归：gRPC servicer → handler → 门面 → 查询服务全链透传 favorite。

        servicer ListTestCases 无条件传 favorite/only_deleted/user_id，门面
        TestCaseCrudService.list_testcases 签名曾缺参导致全量用例列表 500
        （'unexpected keyword argument favorite'）。本用例按 servicer 同款
        形态走 handler 链，签名回归即在此失败。
        """
        from task_service.application.queries.task_queries import ListTestCasesQuery
        from task_service.application.handlers import task_query_handler
        from task_service.infrastructure.persistence.models import TestCase, Favorite

        session = get_db_session()
        try:
            session.add_all([
                TestCase(id='INT141_CHAIN1', name='链路收藏命中', config={}),
                TestCase(id='INT141_CHAIN2', name='链路未收藏', config={}),
            ])
            session.add(Favorite(user_id=311, entity_type='testcase',
                                 entity_id='INT141_CHAIN1'))
            session.commit()
        finally:
            remove_db_session()

        # 与 servicer ListTestCases 相同的构造与委托形态（含无条件传参）
        result = task_query_handler.handle_list_testcases(ListTestCasesQuery(
            page=1, per_page=10, keyword=None, tag=None, group_id=None,
            algorithm_type=None, view=None, include_deleted=False,
            favorite=True, only_deleted=False, user_id=311))
        assert result.get('success') is True
        items = result.get('data', {}).get('items') or []
        assert [tc['id'] for tc in items] == ['INT141_CHAIN1']

        # 不带 favorite 的普通列表同样走通（历史上该路径也因签名 500）
        plain = task_query_handler.handle_list_testcases(ListTestCasesQuery(
            page=1, per_page=10, favorite=False, only_deleted=False, user_id=311))
        assert plain.get('success') is True
        plain_ids = {tc['id'] for tc in (plain.get('data', {}).get('items') or [])}
        assert {'INT141_CHAIN1', 'INT141_CHAIN2'} <= plain_ids

        # view=tag 聚合视图（成员实测口径）走通
        tagged = task_query_handler.handle_list_testcases(ListTestCasesQuery(
            page=1, per_page=10, view='tag', favorite=False,
            only_deleted=False, user_id=311))
        assert tagged.get('success') is True


# ---------------- 回收站（任务/用例） ----------------

class TestTrashTasks:
    """任务回收站全链：软删盖时间/操作人 → 列表 → 恢复 → purge。"""

    def setup_method(self):
        _ensure_task_tables()

    def teardown_method(self):
        _cleanup_tables(_TASK_TABLES)

    def _make_task(self, name='INT141_回收站任务'):
        from task_service.infrastructure.persistence.models import Task
        session = get_db_session()
        try:
            task = Task(name=name, status='completed', total_cases=0,
                        created_by_user_id=404)
            session.add(task)
            session.commit()
            return task.id
        finally:
            remove_db_session()

    def test_soft_delete_mixin_stamps_deleted_at_and_by(self):
        from task_service.infrastructure.persistence.models import Task
        from task_service.infrastructure.persistence.task_repository import task_repository

        tid = self._make_task()
        set_current_user_id(505)
        try:
            assert task_repository.soft_delete(tid) is True
            session = get_db_session()
            try:
                po = session.get(Task, tid)
                assert po.deleted is True
                assert po.deleted_at is not None
                assert po.deleted_by_user_id == 505
            finally:
                remove_db_session()
        finally:
            set_current_user_id(None)

    def test_batch_delete_stamps_operator(self):
        from task_service.infrastructure.persistence.models import Task
        from task_service.infrastructure.persistence.task_repository import task_repository

        tid = self._make_task()
        set_current_user_id(606)
        try:
            count = task_repository.batch_stop_and_soft_delete([tid])
            assert count == 1
            session = get_db_session()
            try:
                po = session.get(Task, tid)
                assert po.deleted is True and po.deleted_at is not None
                assert po.deleted_by_user_id == 606
            finally:
                remove_db_session()
        finally:
            set_current_user_id(None)

    def test_trash_list_restore_purge_full_chain(self):
        from task_service.infrastructure.persistence.trash_repository import trash_repository
        from task_service.infrastructure.persistence.models import Task, Favorite

        tid = self._make_task()
        # A 删除（owner=404 创建，A=707 删除）
        set_current_user_id(707)
        try:
            from task_service.infrastructure.persistence.task_repository import task_repository
            task_repository.soft_delete(tid)
        finally:
            set_current_user_id(None)
        # 用户收藏该任务（purge 后悬挂引用应被清理）
        session = get_db_session()
        try:
            session.add(Favorite(user_id=808, entity_type='task', entity_id=str(tid)))
            session.commit()
        finally:
            remove_db_session()

        # 回收站可见（含删除人/时间）
        listing = trash_repository.list_deleted_tasks()
        item = next(i for i in listing['items'] if i['id'] == tid)
        assert item['deleted_at'] is not None
        assert item['deleted_by_user_id'] == 707

        # 恢复（单个=批量入口传一个 id）
        assert trash_repository.restore_tasks([tid]) == 1
        session = get_db_session()
        try:
            assert session.get(Task, tid).deleted is False
        finally:
            remove_db_session()

        # 再次删除后 purge：非 owner 非 admin → 拒绝
        set_current_user_id(707)
        try:
            task_repository.soft_delete(tid)
        finally:
            set_current_user_id(None)
        with pytest.raises(PurgePermissionDenied):
            trash_repository.purge_tasks([tid], user_id=999, is_admin=False)
        # owner（删除人）可 purge
        assert trash_repository.purge_tasks([tid], user_id=707, is_admin=False) == 1
        session = get_db_session()
        try:
            assert session.get(Task, tid) is None
            # 收藏悬挂引用已清理
            assert session.query(Favorite).filter_by(
                entity_type='task', entity_id=str(tid)).count() == 0
        finally:
            remove_db_session()

    def test_purge_admin_allowed_and_active_row_skipped(self):
        from task_service.infrastructure.persistence.trash_repository import trash_repository
        from task_service.infrastructure.persistence.models import Task

        tid = self._make_task()
        # 活跃行：admin purge 也只清软删行 → 0 条，活跃行不动
        assert trash_repository.purge_tasks([tid], user_id=1, is_admin=True) == 0
        assert session_get(Task, tid) is not None

    def test_restore_report_api_shape(self):
        """favorite_trash_service.restore_tasks 空列表 400。"""
        from task_service.application.favorite_trash_service import favorite_trash_service
        result = favorite_trash_service.restore_tasks([])
        assert result['success'] is False and result['code'] == 400


def session_get(model, pk):
    session = get_db_session()
    try:
        return session.get(model, pk)
    finally:
        remove_db_session()


class TestTrashTestcases:
    """用例回收站：删除盖操作人 → only_deleted 列表 → 恢复 → purge。"""

    def setup_method(self):
        _ensure_task_tables()

    def teardown_method(self):
        _cleanup_tables(_TASK_TABLES)

    def test_delete_stamp_operator_and_trash_chain(self):
        from task_service.infrastructure.persistence.models import TestCase
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository
        from task_service.infrastructure.persistence.trash_repository import trash_repository

        session = get_db_session()
        try:
            session.add(TestCase(id='INT141_TRASH_CASE', name='回收用例', config={}))
            session.commit()
        finally:
            remove_db_session()

        set_current_user_id(909)
        try:
            testcase_repository.soft_delete_testcases_by_ids(['INT141_TRASH_CASE'])
            testcase_repository.commit()
        finally:
            set_current_user_id(None)

        listing = trash_repository.list_deleted_testcases(keyword='INT141_TRASH_CASE')
        assert listing['total'] == 1
        item = listing['items'][0]
        assert item['deleted_by_user_id'] == 909
        assert item['deleted_at'] is not None

        # 恢复
        assert trash_repository.restore_testcases(['INT141_TRASH_CASE']) == 1
        po = session_get(TestCase, 'INT141_TRASH_CASE')
        assert po.deleted is False and po.deleted_at is None

        # purge：非 owner 非 admin 拒绝；admin 放行
        set_current_user_id(909)
        try:
            testcase_repository.soft_delete_testcases_by_ids(['INT141_TRASH_CASE'])
            testcase_repository.commit()
        finally:
            set_current_user_id(None)
        with pytest.raises(PurgePermissionDenied):
            trash_repository.purge_testcases(['INT141_TRASH_CASE'], user_id=1, is_admin=False)
        assert trash_repository.purge_testcases(
            ['INT141_TRASH_CASE'], user_id=1, is_admin=True) == 1
        assert session_get(TestCase, 'INT141_TRASH_CASE') is None

    def test_restore_purge_nonexistent_string_id_returns_zero(self):
        """R1 ②：testcase 非法/不存在 ID 在服务层按计数口径表达（0 行恢复/删除），不报错不 400。"""
        from task_service.infrastructure.persistence.trash_repository import trash_repository

        assert trash_repository.restore_testcases(['nonexistent-case-id']) == 0
        assert trash_repository.purge_testcases(
            ['nonexistent-case-id'], user_id=1, is_admin=True) == 0


# ---------------- 操作人填充 ----------------

class TestOperatorFill:
    """created_by_user_id / updated_by_user_id 填充链路。"""

    def setup_method(self):
        _ensure_task_tables()

    def teardown_method(self):
        _cleanup_tables(_TASK_TABLES)

    def test_task_create_fills_created_by_user_id_from_context(self):
        from task_service.application.task.task_crud_service import task_crud_service

        set_current_user_id(111)
        try:
            result = task_crud_service.create({
                'name': 'INT141_操作人任务',
                'case_ids': [],
                'device_ids': [],
                'api_ids': [],
                'created_by': 999,  # 客户端自报值不得充当操作人
            })
            assert result['success'] is True
            tid = result['data']['id']
            po = session_get(Task_, tid)
            assert po.created_by_user_id == 111
            assert po.created_by == 999  # 旧列保持既有客户端语义
        finally:
            set_current_user_id(None)

    def test_task_create_without_context_leaves_null(self):
        """AUTH_MODE=off 等价：无上下文 → NULL，不硬编码 0/None 充当真实用户。"""
        from task_service.application.task.task_crud_service import task_crud_service

        set_current_user_id(None)
        result = task_crud_service.create({
            'name': 'INT141_OFF模式任务', 'case_ids': [], 'device_ids': [], 'api_ids': [],
        })
        assert result['success'] is True
        po = session_get(Task_, result['data']['id'])
        assert po.created_by_user_id is None

    def test_task_update_fills_updated_by_user_id(self):
        from task_service.application.task.task_crud_service import task_crud_service

        set_current_user_id(111)
        result = task_crud_service.create({
            'name': 'INT141_更新前', 'case_ids': [], 'device_ids': [], 'api_ids': [],
        })
        tid = result['data']['id']
        set_current_user_id(222)
        try:
            updated = task_crud_service.update(tid, {'name': 'INT141_更新后'})
            assert updated['success'] is True
            po = session_get(Task_, tid)
            assert po.name == 'INT141_更新后'
            assert po.updated_by_user_id == 222
        finally:
            set_current_user_id(None)

    def test_testcase_create_fills_created_by(self):
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository

        set_current_user_id(333)
        try:
            tc = testcase_repository.create_testcase({
                'id': 'INT141_OP_CASE', 'name': '操作人用例', 'config': {},
            })
            assert tc.created_by_user_id == 333
        finally:
            set_current_user_id(None)
            _cleanup_tables(_TASK_TABLES)


# 导入防抖：Task 模型符号（test_task_create_fills_* 中使用）
from task_service.infrastructure.persistence.models import Task as Task_  # noqa: E402


# ---------------- 回收站（报告） ----------------

class TestReportFavoriteTrash:
    """report_service 收藏 + 回收站全链。"""

    def setup_method(self):
        _ensure_report_tables()

    def teardown_method(self):
        _cleanup_tables(_REPORT_TABLES)

    def _make_report(self, name='INT141_回收站报告'):
        from report_service.infrastructure.persistence.models import Report
        session = get_db_session()
        try:
            po = Report(name=name, type='task', status='completed',
                        created_by_user_id=444)
            session.add(po)
            session.commit()
            return po.id
        finally:
            remove_db_session()

    def test_favorite_report_idempotent_and_per_user(self):
        from report_service.infrastructure.persistence.report_favorite_trash_repository import (
            report_favorite_trash_repository,
        )

        rid = self._make_report()
        r1 = report_favorite_trash_repository.add(101, rid)
        assert r1['success'] is True and r1['already_favorited'] is False
        r2 = report_favorite_trash_repository.add(101, rid)
        assert r2['success'] is True and r2['already_favorited'] is True
        # B 不可见
        assert report_favorite_trash_repository.list_ids(102) == []
        # 取消幂等
        r3 = report_favorite_trash_repository.remove(101, rid)
        assert r3['success'] is True and r3['removed'] == 1
        r4 = report_favorite_trash_repository.remove(101, rid)
        assert r4['success'] is True and r4['removed'] == 0

    def test_report_trash_chain_and_purge_permission(self):
        from report_service.infrastructure.persistence.report_favorite_trash_repository import (
            report_favorite_trash_repository,
        )
        from report_service.infrastructure.persistence.models import Report

        rid = self._make_report()
        # 软删（盖时间 + 删除人）
        from shared.utils.db_session import SoftDeleteMixin
        from report_service.infrastructure.persistence.report_repository import report_repository
        set_current_user_id(555)
        try:
            assert report_repository.soft_delete(rid) is True
        finally:
            set_current_user_id(None)

        listing = report_favorite_trash_repository.list_deleted_reports()
        item = next(i for i in listing['items'] if i['id'] == rid)
        assert item['deleted_by_user_id'] == 555
        assert item['deleted_at'] is not None

        # 非权限用户 purge 拒绝
        with pytest.raises(PurgePermissionDenied):
            report_favorite_trash_repository.purge_reports([rid], user_id=999, is_admin=False)
        # owner（删除人）purge 成功，物理行消失
        assert report_favorite_trash_repository.purge_reports(
            [rid], user_id=555, is_admin=False) == 1
        session = get_db_session()
        try:
            assert session.get(Report, rid) is None
        finally:
            remove_db_session()

    def test_report_restore(self):
        from report_service.infrastructure.persistence.report_favorite_trash_repository import (
            report_favorite_trash_repository,
        )
        from report_service.infrastructure.persistence.models import Report

        rid = self._make_report()
        report_repository_soft_delete(rid)
        assert report_favorite_trash_repository.restore_reports([rid]) == 1
        session = get_db_session()
        try:
            po = session.get(Report, rid)
            assert po.deleted is False and po.deleted_at is None
        finally:
            remove_db_session()

    def test_report_list_favorite_filter(self):
        from report_service.infrastructure.persistence.report_favorite_trash_repository import (
            report_favorite_trash_repository,
        )
        from report_service.infrastructure.persistence.report_repository import report_repository

        rid = self._make_report()
        report_favorite_trash_repository.add(606, rid)
        aggregates = report_repository.list_reports(favorite=True, user_id=606)
        assert [a.id for a in aggregates] == [rid]
        # 其他用户收藏过滤为空
        assert report_repository.list_reports(favorite=True, user_id=777) == []

    def test_report_soft_delete_stamps_operator(self):
        from report_service.infrastructure.persistence.models import Report
        from report_service.infrastructure.persistence.report_repository import report_repository

        rid = self._make_report()
        set_current_user_id(888)
        try:
            assert report_repository.soft_delete(rid) is True
            session = get_db_session()
            try:
                po = session.get(Report, rid)
                assert po.deleted is True
                assert po.deleted_at is not None
                assert po.deleted_by_user_id == 888
            finally:
                remove_db_session()
        finally:
            set_current_user_id(None)


# ---------------- 真实 gRPC server 拦截器链（验收 F1/F3 回归） ----------------

class TestGrpcInterceptorChain:
    """起真实 gRPC server（挂全量服务端拦截器）断言 metadata → contextvar。

    验收 F1/F3：服务端拦截器曾依赖 `hasattr(handler_call_details,
    'unary_unary')` 判断包装时机，grpcio 1.83 的 HandlerCallDetails 仅含
    method/invocation_metadata，判断恒 False → 三个服务端拦截器整体 no-op
    （metadata 到达 servicer 但 contextvar 恒空、DB session 从不清理）。
    本类用真实 server + 真实 metadata 走完整链路，拦截器回归 no-op 即在此失败。
    """

    def test_user_context_and_db_scope_via_real_grpc_server(self, monkeypatch):
        import json as _json
        from concurrent import futures

        import grpc

        import shared.models.database as db_mod
        from shared.proto import task_service_pb2 as task_pb
        from shared.proto import task_service_pb2_grpc as task_grpc
        from shared.infrastructure.grpc_interceptors import (
            server_log_interceptor, server_db_scope_interceptor,
            server_user_context_interceptor,
        )
        from shared.infrastructure.user_context import (
            get_current_user_id, get_current_user_is_admin,
        )

        captured = []
        cleanup_calls = []
        real_remove = db_mod.remove_db_session

        def fake_remove():
            cleanup_calls.append(True)
            return real_remove()

        monkeypatch.setattr(db_mod, 'remove_db_session', fake_remove)

        class _CaptureServicer(task_grpc.TestCaseConfigServiceServicer):
            def GetTestCaseStats(self, request, context=None):
                captured.append((get_current_user_id(), get_current_user_is_admin()))
                return task_pb.TestCaseConfigResponse(success=True, message='ok')

        server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=2),
            interceptors=[server_db_scope_interceptor, server_log_interceptor,
                          server_user_context_interceptor])
        task_grpc.add_TestCaseConfigServiceServicer_to_server(_CaptureServicer(), server)
        port = server.add_insecure_port('127.0.0.1:0')
        server.start()
        try:
            with grpc.insecure_channel(f'127.0.0.1:{port}') as channel:
                stub = task_grpc.TestCaseConfigServiceStub(channel)
                # 带 metadata：拦截器应把 x-user-id/x-user-is-admin 写入 contextvar（F1）
                resp = stub.GetTestCaseStats(
                    task_pb.GetTestCaseStatsRequest(), timeout=10,
                    metadata=(('x-user-id', '8'), ('x-user-is-admin', 'true')))
                assert resp.success is True
                assert captured[-1] == (8, True)
                # 不带 metadata：RPC 结束清理生效，不得串号
                stub.GetTestCaseStats(task_pb.GetTestCaseStatsRequest(), timeout=10)
                assert captured[-1] == (None, False)
        finally:
            server.stop(0)
        # DB scope 清理曾被同款 no-op 吞掉（F3）：每次 RPC 结束必须 remove_db_session
        assert len(cleanup_calls) >= 2


# ---------------- 网关业务码映射（验收 F2 回归） ----------------

class TestGatewayBusinessCodeMapping:
    """服务层业务码经 gRPC data JSON 透传后在网关提升到顶层（F2）。

    链路：服务失败响应 data={'code': X} → servicer _resp（proto 仅
    success/message/data 三字段）→ 网关代理 _resp / _report_resp 提升
    data['code'] 到顶层 → BFF resp.get('code') → 路由映射 400/401/403/404。
    """

    @staticmethod
    def _fake_stub_resp(success, message, data):
        from types import SimpleNamespace
        import json as _json
        return SimpleNamespace(success=success, message=message,
                               data=_json.dumps(data) if data is not None else '')

    def test_task_proxy_resp_lifts_code_on_failure_only(self):
        from api_gateway.infrastructure.grpc_proxies.task_testcase_config_proxies import (
            _TaskConfigProxy,
        )
        proxy = _TaskConfigProxy()
        fail = proxy._resp(self._fake_stub_resp(False, '权限不足', {'code': 403}))
        assert fail['code'] == 403 and fail['success'] is False
        # 成功响应不提升：data 内业务字段 code 不受影响
        ok = proxy._resp(self._fake_stub_resp(True, 'ok', {'code': 'ABC'}))
        assert 'code' not in ok and ok['data']['code'] == 'ABC'
        # 失败但 data 无码：保持默认（无 code 键）
        noc = proxy._resp(self._fake_stub_resp(False, '失败', {'other': 1}))
        assert 'code' not in noc

    def test_testcase_proxy_resp_lifts_code_on_failure(self):
        from api_gateway.infrastructure.grpc_proxies.task_testcase_config_proxies import (
            _TestCaseConfigProxy,
        )
        out = _TestCaseConfigProxy()._resp(self._fake_stub_resp(False, '未认证', {'code': 401}))
        assert out['code'] == 401 and out['success'] is False

    def test_report_resp_helper_lifts_code_on_failure(self):
        from api_gateway.application.services.favorite_trash_service import _report_resp
        fail = _report_resp(self._fake_stub_resp(False, '彻底删除仅限管理员', {'code': 403}))
        assert fail['code'] == 403 and fail['success'] is False
        ok = _report_resp(self._fake_stub_resp(True, 'ok', {'ids': ['1']}))
        assert 'code' not in ok and ok['data'] == {'ids': ['1']}

    def test_service_4xx_failures_carry_code_in_data(self):
        """服务侧 4xx 失败必须把码放进 data JSON（否则网关无法取码）。"""
        from task_service.application.favorite_trash_service import favorite_trash_service as task_svc
        r1 = task_svc.purge_tasks([])
        assert r1['code'] == 400 and r1['data'] == {'code': 400}
        r2 = task_svc.restore_testcases([])
        assert r2['code'] == 400 and r2['data'] == {'code': 400}

        from report_service.application.favorite_trash_service import (
            report_favorite_trash_service as report_svc,
        )
        r3 = report_svc.favorite(None, 1)
        assert r3['code'] == 401 and r3['data'] == {'code': 401}
        r4 = report_svc.restore_reports([])
        assert r4['code'] == 400 and r4['data'] == {'code': 400}


# ---------------- 批量 purge 逐行 owner 校验（审计 P2-1） ----------------

class TestBatchPurgeOwnerScoping:
    """混合 owner 批量 purge：非 admin 仅删除自己 created_by/deleted_by 命中的行。

    回归：曾为"整批任一 owner 即放行整批"——B 混入他人行可越权物理删除。
    口径：admin 放行整批；非 admin 逐行过滤，非 owned 行跳过（计数体现），
    全非 owned 抛 PurgePermissionDenied（403）。
    """

    def setup_method(self):
        _ensure_task_tables()

    def teardown_method(self):
        _cleanup_tables(_TASK_TABLES)

    def _make_task(self, name, owner):
        from task_service.infrastructure.persistence.models import Task
        session = get_db_session()
        try:
            t = Task(name=name, status='completed', total_cases=0,
                     created_by_user_id=owner)
            session.add(t)
            session.commit()
            return t.id
        finally:
            remove_db_session()

    def _soft_delete_task(self, tid, deleter):
        from task_service.infrastructure.persistence.task_repository import task_repository
        set_current_user_id(deleter)
        try:
            task_repository.soft_delete(tid)
        finally:
            set_current_user_id(None)

    def test_mixed_owner_batch_purge_skips_non_owned(self):
        from task_service.infrastructure.persistence.trash_repository import trash_repository
        from task_service.infrastructure.persistence.models import Task

        mine = self._make_task('P2A_我的', owner=301)
        others = self._make_task('P2A_他人', owner=302)
        self._soft_delete_task(mine, deleter=301)
        self._soft_delete_task(others, deleter=302)

        # B（301）混合批量：只删自己的，他人行跳过（计数=1）
        assert trash_repository.purge_tasks(
            [mine, others], user_id=301, is_admin=False) == 1
        assert session_get(Task, mine) is None
        assert session_get(Task, others) is not None

    def test_purge_all_non_owned_rejected(self):
        from task_service.infrastructure.persistence.trash_repository import trash_repository

        others = self._make_task('P2A_他人2', owner=302)
        self._soft_delete_task(others, deleter=302)
        with pytest.raises(PurgePermissionDenied):
            trash_repository.purge_tasks([others], user_id=301, is_admin=False)

    def test_admin_mixed_batch_purges_all(self):
        from task_service.infrastructure.persistence.trash_repository import trash_repository
        from task_service.infrastructure.persistence.models import Task

        a = self._make_task('P2A_混1', owner=301)
        b = self._make_task('P2A_混2', owner=302)
        self._soft_delete_task(a, deleter=301)
        self._soft_delete_task(b, deleter=302)
        assert trash_repository.purge_tasks([a, b], user_id=1, is_admin=True) == 2
        assert session_get(Task, a) is None and session_get(Task, b) is None

    def test_deleter_counts_as_owner(self):
        from task_service.infrastructure.persistence.trash_repository import trash_repository

        tid = self._make_task('P2A_删除人owner', owner=302)
        self._soft_delete_task(tid, deleter=301)
        assert trash_repository.purge_tasks([tid], user_id=301, is_admin=False) == 1

    def test_mixed_owner_batch_purge_testcases(self):
        from task_service.infrastructure.persistence.trash_repository import trash_repository
        from task_service.infrastructure.persistence.models import TestCase
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository

        session = get_db_session()
        try:
            session.add_all([
                TestCase(id='P2A_CASE_MINE', name='P2A我的用例', config={},
                         created_by_user_id=301),
                TestCase(id='P2A_CASE_OTHER', name='P2A他人用例', config={},
                         created_by_user_id=302),
            ])
            session.commit()
        finally:
            remove_db_session()
        set_current_user_id(301)
        try:
            testcase_repository.soft_delete_testcases_by_ids(['P2A_CASE_MINE'])
            testcase_repository.commit()
        finally:
            set_current_user_id(None)
        set_current_user_id(302)
        try:
            testcase_repository.soft_delete_testcases_by_ids(['P2A_CASE_OTHER'])
            testcase_repository.commit()
        finally:
            set_current_user_id(None)

        # 301 混合批量：只删自己的（创建人+删除人），他人行跳过
        assert trash_repository.purge_testcases(
            ['P2A_CASE_MINE', 'P2A_CASE_OTHER'], user_id=301, is_admin=False) == 1
        assert session_get(TestCase, 'P2A_CASE_MINE') is None
        assert session_get(TestCase, 'P2A_CASE_OTHER') is not None
        # 无关用户整批拒绝
        with pytest.raises(PurgePermissionDenied):
            trash_repository.purge_testcases(['P2A_CASE_OTHER'], user_id=303, is_admin=False)

    def test_mixed_owner_batch_purge_reports(self):
        _ensure_report_tables()
        from report_service.infrastructure.persistence.report_favorite_trash_repository import (
            report_favorite_trash_repository,
        )
        from report_service.infrastructure.persistence.models import Report
        from report_service.infrastructure.persistence.report_repository import report_repository

        def make_report(name, owner):
            session = get_db_session()
            try:
                po = Report(name=name, type='task', status='completed',
                            created_by_user_id=owner)
                session.add(po)
                session.commit()
                return po.id
            finally:
                remove_db_session()

        mine = make_report('P2A_报告_我的', owner=401)
        others = make_report('P2A_报告_他人', owner=402)
        set_current_user_id(401)
        try:
            assert report_repository.soft_delete(mine) is True
        finally:
            set_current_user_id(None)
        set_current_user_id(402)
        try:
            assert report_repository.soft_delete(others) is True
        finally:
            set_current_user_id(None)

        # 401 混合批量：只删自己的
        assert report_favorite_trash_repository.purge_reports(
            [mine, others], user_id=401, is_admin=False) == 1
        assert session_get(Report, mine) is None
        assert session_get(Report, others) is not None

    def test_restore_backfills_updated_by(self):
        """恢复人可追溯：三域恢复回填 updated_by_user_id（off 语义 NULL 不报错）。"""
        from task_service.infrastructure.persistence.trash_repository import trash_repository
        from task_service.infrastructure.persistence.models import Task, TestCase
        from task_service.infrastructure.persistence.testcase_repository import (
            testcase_repository,
        )

        tid = self._make_task('P2A_恢复回填', owner=501)
        self._soft_delete_task(tid, deleter=501)
        set_current_user_id(502)
        try:
            assert trash_repository.restore_tasks([tid]) == 1
            po = session_get(Task, tid)
            assert po.deleted is False and po.deleted_by_user_id is None
            assert po.updated_by_user_id == 502
        finally:
            set_current_user_id(None)

        session = get_db_session()
        try:
            session.add(TestCase(id='P2A_CASE_RESTORE', name='P2A恢复用例', config={}))
            session.commit()
        finally:
            remove_db_session()
        set_current_user_id(501)
        try:
            testcase_repository.soft_delete_testcases_by_ids(['P2A_CASE_RESTORE'])
            testcase_repository.commit()
        finally:
            set_current_user_id(None)
        set_current_user_id(503)
        try:
            assert trash_repository.restore_testcases(['P2A_CASE_RESTORE']) == 1
            po = session_get(TestCase, 'P2A_CASE_RESTORE')
            assert po.deleted is False and po.deleted_by_user_id is None
            assert po.updated_by_user_id == 503
        finally:
            set_current_user_id(None)

    def test_restore_without_context_keeps_null(self):
        """无上下文（off 等价）恢复：updated_by 保持 NULL，不报错。"""
        from task_service.infrastructure.persistence.trash_repository import trash_repository
        from task_service.infrastructure.persistence.models import Task

        tid = self._make_task('P2A_恢复无上下文', owner=501)
        self._soft_delete_task(tid, deleter=501)
        assert trash_repository.restore_tasks([tid]) == 1
        po = session_get(Task, tid)
        assert po.deleted is False and po.updated_by_user_id is None


class TestBffIdValidation:
    """审计 P3-1：task/report 批量 ID 统一在 BFF 转换，非法 ID 返回 400
    （不再被代理吞成 500）。R1 回归修复：testcase 主键为 String(50) UUID，
    BFF 不做 int 化，字符串原样透传（非法 ID 语义交服务层）。"""

    def test_restore_bad_id_returns_400(self):
        from api_gateway.application.services.favorite_trash_service import FavoriteTrashService
        r = FavoriteTrashService.restore('task', ['abc'])
        assert r['code'] == 400 and '格式' in r['message']

    def test_purge_bad_id_returns_400(self):
        from api_gateway.application.services.favorite_trash_service import FavoriteTrashService
        r = FavoriteTrashService.purge('report', [None])
        assert r['code'] == 400

    def test_restore_report_bad_id_returns_400(self):
        from api_gateway.application.services.favorite_trash_service import FavoriteTrashService
        r = FavoriteTrashService.restore('report', ['xyz'])
        assert r['code'] == 400

    def test_testcase_uuid_ids_pass_through_bff(self):
        """R1 回归锁定：合法 UUID（及任意字符串形态）testcase ID 经 BFF
        restore/purge 原样到达代理，不被 int 化拦截。"""
        from api_gateway.application.services import favorite_trash_service as bff_mod

        captured = {}

        class _FakeTestcaseProxy:
            def restore_testcases(self, case_ids):
                captured['restore'] = case_ids
                return {'success': True, 'message': 'ok', 'data': {'restored_count': 1}}

            def purge_testcases(self, case_ids):
                captured['purge'] = case_ids
                return {'success': True, 'message': 'ok', 'data': {'purged_count': 1}}

        uuid_id = '3f2b9c1e-7a4d-4e8f-9b2c-1d5e6f7a8b9c'
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(bff_mod, 'testcase_config_service', _FakeTestcaseProxy())
            r1 = bff_mod.FavoriteTrashService.restore('testcase', [uuid_id, 'not-even-a-uuid'])
            r2 = bff_mod.FavoriteTrashService.purge('testcase', [uuid_id])
        assert r1['data'] == {'restored_count': 1}
        assert r2['data'] == {'purged_count': 1}
        assert captured['restore'] == [uuid_id, 'not-even-a-uuid']
        assert captured['purge'] == [uuid_id]


def report_repository_soft_delete(rid):
    from report_service.infrastructure.persistence.report_repository import report_repository
    report_repository.soft_delete(rid)
