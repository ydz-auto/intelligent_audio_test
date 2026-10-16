# -*- coding: utf-8 -*-
"""INT-463 专项：task_service 数据可见性落地（列 + 行级过滤 + owner 校验）。

覆盖验收标准（后端）：
1. 私有隔离：用户 B 访问用户 A 的私有 task/testcase/group/tag ——
   列表不可见、详情 404、update/delete 403；owner 全操作正常
2. 共享零回归：存量默认 shared，有权限点角色访问与现状一致
3. 批量逐行过滤：batch 对私有非 owner 行跳过
4. published_tasks 新建写当前 user_id；存量 NULL 访问不报错
5. 收藏 / 挑选 per-user 回归不破（由既有套件覆盖）

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表，
用例内清理，对齐 test_int141_favorites_trash_operator.py 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.infrastructure.user_context import set_current_user_id, set_current_user_is_admin
from shared.infrastructure.visibility_filter import VisibilityDenied, check_visible
from shared.models.database import (
    Base, init_db, get_engine, get_db_session,
)

# ---------------- 工具 ----------------

_TABLES = None


def _ensure_tables():
    init_db(pool_size=2)
    global _TABLES
    if _TABLES is None:
        from task_service.infrastructure.persistence.models import (
            Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation,
            TestResult, Tag, TagCategory, TestCaseGroup, TestCase, TestCaseTag,
            Favorite, Log, PublishedTask, TaskCherryPickRelation,
        )
        _TABLES = [t.__table__ for t in (
            Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation,
            TestResult, TagCategory, Tag, TestCaseGroup, TestCase, TestCaseTag,
            Favorite, Log, PublishedTask, TaskCherryPickRelation,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLES)
    return _TABLES


@pytest.fixture(autouse=True)
def _cleanup():
    """每个用例前清空涉及表，保证固定 ID 夹具互不冲突。"""
    _ensure_tables()
    session = get_db_session()
    try:
        for table in reversed(_TABLES):
            session.execute(table.delete())
        session.commit()
    finally:
        session.close()
    yield
    # 清理上下文，避免泄漏到后续用例
    set_current_user_id(None)
    set_current_user_is_admin(False)


def _set_user(user_id=None, is_admin=False):
    set_current_user_id(user_id)
    set_current_user_is_admin(is_admin)


_UNSET = object()


def _set_visibility(table, row_id, visibility, owner=_UNSET):
    """直接置行 visibility（测试夹具；生产路径经命令侧写入）。

    owner 仅在显式传入时更新（传 None 表示置 NULL，缺省保持既有 owner）。
    用 SQL UPDATE 绕过 ORM 身份映射，避免已提交 PO 的 DetachedInstanceError。
    """
    from sqlalchemy import update
    session = get_db_session()
    try:
        values = {'visibility': visibility}
        if owner is not _UNSET:
            values['created_by_user_id'] = owner
        session.execute(update(table).where(table.id == row_id).values(**values))
        session.commit()
    finally:
        session.close()


class _FakeIdempotencyStore:
    """内存幂等仓储替身（对齐 test_int75 两态语义：processing 占位 / completed 回放）。"""

    def __init__(self):
        self.records = {}

    def lookup(self, key):
        record = self.records.get(key)
        return dict(record) if record else None

    def reserve(self, key, ttl_seconds):
        if key in self.records:
            return False
        self.records[key] = {'status': 'processing'}
        return True

    def complete(self, key, response, ttl_seconds):
        self.records[key] = {'status': 'completed', 'response': dict(response)}

    def release(self, key):
        self.records.pop(key, None)


# ---------------- 1. 私有隔离：task ----------------

class TestTaskVisibility:
    def _make_task(self, user_id):
        from task_service.infrastructure.persistence.task_repository import task_repository
        return task_repository.create_task_with_relations(
            name='t1', description='', config={}, algorithm_type='translation',
            algorithm_params={}, case_ids=[], device_ids=[], api_ids=[], created_by=user_id,
        )

    def test_private_task_hidden_from_other_user_list(self):
        from task_service.infrastructure.persistence.models import Task
        _set_user(100)
        tid = self._make_task(100)
        _set_visibility(Task, tid, 'private')
        # 其他用户列表不可见
        _set_user(200)
        from task_service.infrastructure.read_models.task_read_model import task_read_model
        result = task_read_model.search_tasks(page=1, per_page=10, user_id=200)
        ids = [item['id'] for item in result['items']]
        assert tid not in ids

    def test_private_task_detail_404_for_other(self):
        from task_service.infrastructure.persistence.models import Task
        _set_user(100)
        tid = self._make_task(100)
        _set_visibility(Task, tid, 'private')
        _set_user(200)
        from task_service.application.task.task_query_service import task_query_service
        resp = task_query_service.get_task_detail(tid)
        assert resp['code'] == 404

    def test_private_task_write_403_for_other(self):
        from task_service.infrastructure.persistence.models import Task
        _set_user(100)
        tid = self._make_task(100)
        _set_visibility(Task, tid, 'private')
        _set_user(200)
        from task_service.application.task.task_crud_service import task_crud_service
        resp = task_crud_service.update(tid, {'name': 'x'})
        assert resp['code'] == 403
        resp = task_crud_service.delete(tid)
        assert resp['code'] == 403

    def test_owner_full_access(self):
        from task_service.infrastructure.persistence.models import Task
        _set_user(100)
        tid = self._make_task(100)
        _set_visibility(Task, tid, 'private')
        from task_service.application.task.task_query_service import task_query_service
        from task_service.application.task.task_crud_service import task_crud_service
        resp = task_query_service.get_task_detail(tid)
        assert resp['success'] is True
        resp = task_crud_service.update(tid, {'name': 't1-renamed'})
        assert resp['success'] is True

    def test_admin_sees_private_task(self):
        from task_service.infrastructure.persistence.models import Task
        _set_user(100)
        tid = self._make_task(100)
        _set_visibility(Task, tid, 'private')
        _set_user(200, is_admin=True)
        from task_service.application.task.task_query_service import task_query_service
        resp = task_query_service.get_task_detail(tid)
        assert resp['success'] is True


# ---------------- 1. 私有隔离：testcase ----------------

class TestTestCaseVisibility:
    def _make_case(self, user_id, group_id):
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository
        tc = testcase_repository.create_testcase({
            'id': 'c-1', 'name': 'case1', 'group_id': group_id,
            'config': {'rounds': []}, 'algorithm_type': 'translation',
        })
        testcase_repository.commit()
        return tc.id

    def _make_group(self, user_id):
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository
        group = testcase_repository.create_group_and_commit('g-1', 'grp', '', '')
        return group['id']

    def test_private_case_hidden_from_other_list(self):
        from task_service.infrastructure.persistence.models import TestCase
        _set_user(100)
        gid = self._make_group(100)
        cid = self._make_case(100, gid)
        _set_visibility(TestCase, cid, 'private')
        _set_user(200)
        from task_service.application.testcase.testcase_crud_service import testcase_crud_service
        resp = testcase_crud_service.list_testcases(user_id=200)
        ids = [item['id'] for item in resp['data']['items']]
        assert cid not in ids

    def test_private_case_detail_404_for_other(self):
        from task_service.infrastructure.persistence.models import TestCase
        _set_user(100)
        gid = self._make_group(100)
        cid = self._make_case(100, gid)
        _set_visibility(TestCase, cid, 'private')
        _set_user(200)
        from task_service.application.testcase.testcase_crud_service import testcase_crud_service
        resp = testcase_crud_service.get_testcase_detail(cid)
        assert resp['code'] == 404

    def test_private_case_write_403_for_other(self):
        from task_service.infrastructure.persistence.models import TestCase
        _set_user(100)
        gid = self._make_group(100)
        cid = self._make_case(100, gid)
        _set_visibility(TestCase, cid, 'private')
        _set_user(200)
        from task_service.application.testcase.testcase_crud_service import testcase_crud_service
        resp = testcase_crud_service.update(cid, {'name': 'x'})
        assert resp['code'] == 403
        resp = testcase_crud_service.delete(cid)
        assert resp['code'] == 403


# ---------------- 1. 私有隔离：group / tag ----------------

class TestGroupTagVisibility:
    def test_private_group_hidden_from_other_list(self):
        from task_service.infrastructure.persistence.models import TestCaseGroup
        _set_user(100)
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository
        testcase_repository.create_group_and_commit('g-2', 'grp2', '', '')
        _set_visibility(TestCaseGroup, 'g-2', 'private')
        _set_user(200)
        items = testcase_repository.list_groups()
        assert 'g-2' not in [str(i['id']) for i in items]

    def test_private_group_detail_404_and_write_403(self):
        from task_service.infrastructure.persistence.models import TestCaseGroup
        _set_user(100)
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository
        testcase_repository.create_group_and_commit('g-3', 'grp3', '', '')
        _set_visibility(TestCaseGroup, 'g-3', 'private')
        _set_user(200)
        assert testcase_repository.get_group_by_id_as_dict('g-3') is None
        from shared.infrastructure.visibility_filter import VisibilityDenied
        with pytest.raises(VisibilityDenied):
            testcase_repository.update_group_and_commit('g-3', name='x')
        with pytest.raises(VisibilityDenied):
            testcase_repository.delete_group_and_commit('g-3')

    def test_private_tag_hidden_from_other_list(self):
        from task_service.infrastructure.persistence.models import Tag
        _set_user(100)
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository
        tag = testcase_repository.create_tag({'name': 'tag1'})
        tag_id = tag.id
        testcase_repository.commit()
        _set_visibility(Tag, tag_id, 'private')
        _set_user(200)
        names = testcase_repository.list_tag_names_paginated(page=1, per_page=100)
        assert 'tag1' not in [t.name for t in names.items]

    def test_private_tag_detail_404_and_write_403(self):
        from task_service.infrastructure.persistence.models import Tag
        _set_user(100)
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository
        tag = testcase_repository.create_tag({'name': 'tag2'})
        tag_id = tag.id
        testcase_repository.commit()
        _set_visibility(Tag, tag_id, 'private')
        _set_user(200)
        from task_service.application.testcase.tag_crud_service import tag_crud_service
        resp = tag_crud_service.get_tag(tag_id)
        assert resp['code'] == 404
        resp = tag_crud_service.update_tag(tag_id, {'name': 'x'})
        assert resp['code'] == 403
        resp = tag_crud_service.delete_tag(tag_id)
        assert resp['code'] == 403


# ---------------- 2. 共享零回归 ----------------

class TestSharedZeroRegression:
    def test_shared_task_visible_to_any_user(self):
        from task_service.infrastructure.persistence.models import Task
        _set_user(100)
        from task_service.infrastructure.persistence.task_repository import task_repository
        tid = task_repository.create_task_with_relations(
            name='shared-t', description='', config={}, algorithm_type='translation',
            algorithm_params={}, case_ids=[], device_ids=[], api_ids=[], created_by=100,
        )
        # 存量默认 shared（不显式置 private）
        _set_user(300)
        from task_service.application.task.task_query_service import task_query_service
        assert task_query_service.get_task_detail(tid)['success'] is True
        _set_user(None)
        assert task_query_service.get_task_detail(tid)['success'] is True

    def test_shared_case_visible_to_any_user(self):
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository
        from task_service.infrastructure.persistence.models import TestCase
        _set_user(100)
        gid = testcase_repository.create_group_and_commit('g-s1', 'sg', '', '')['id']
        cid = testcase_repository.create_testcase({
            'id': 'c-s1', 'name': 'sc', 'group_id': gid, 'config': {'rounds': []},
            'algorithm_type': 'translation'}).id
        testcase_repository.commit()
        _set_user(300)
        from task_service.application.testcase.testcase_crud_service import testcase_crud_service
        assert testcase_crud_service.get_testcase_detail(cid)['success'] is True


# ---------------- 3. 批量逐行过滤 ----------------

class TestBatchRowFiltering:
    def test_batch_delete_skips_private_non_owner(self):
        from task_service.infrastructure.persistence.models import TestCase, Task
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository
        _set_user(100)
        gid = testcase_repository.create_group_and_commit('g-b1', 'bg', '', '')['id']
        cid_own = testcase_repository.create_testcase({
            'id': 'c-b1', 'name': 'own', 'group_id': gid, 'config': {'rounds': []},
            'algorithm_type': 'translation'}).id
        testcase_repository.commit()
        _set_user(200)
        cid_other = testcase_repository.create_testcase({
            'id': 'c-b2', 'name': 'other', 'group_id': gid, 'config': {'rounds': []},
            'algorithm_type': 'translation'}).id
        testcase_repository.commit()
        _set_visibility(TestCase, cid_other, 'private')
        # user1 批量删除包含自己的共享/私有用例 + 他人私有用例
        _set_user(100)
        deleted = testcase_repository.soft_delete_testcases_by_ids([cid_own, cid_other])
        testcase_repository.commit()
        assert deleted == 1  # 仅自己的可见行被删
        session = get_db_session()
        try:
            assert session.get(TestCase, cid_own).deleted is True
            assert session.get(TestCase, cid_other).deleted is False
        finally:
            session.close()


# ---------------- 3b. 批量配置更新 / 参考刷新逐行过滤（审计 P1 修复回归） ----------------

def _get_tc_repo():
    from task_service.infrastructure.persistence.testcase_repository import testcase_repository
    return testcase_repository


def _silence_ref_params(monkeypatch):
    """屏蔽 create 内参考参数生成（避免测试环境触达 gRPC/OSS）。

    task_service.application.testcase 包 __init__ 用同名单例遮蔽子模块，
    import ... as x 拿到的可能是单例对象，故经 sys.modules 取真模块。
    """
    import sys
    tcs_mod = sys.modules['task_service.application.testcase.testcase_crud_service']
    monkeypatch.setattr(tcs_mod, '_apply_reference_params_to_config', lambda tc: None)


class TestBatchConfigUpdateVisibility:
    """批量配置写路径取数后逐行可见性过滤——他人私有用例不被改写（审计 P1）。"""

    def _svc(self):
        from task_service.application.testcase.testcase_batch_service import TestCaseBatchService
        return TestCaseBatchService(repo=_get_tc_repo(), idempotency_store=_FakeIdempotencyStore())

    def test_update_algorithm_params_skips_private_non_owner(self):
        from task_service.infrastructure.persistence.models import TestCase
        repo = _get_tc_repo()
        _set_user(100)
        gid = repo.create_group_and_commit('g-bc1', 'bc1', '', '')['id']
        cid_own = repo.create_testcase({
            'id': 'c-bc1', 'name': 'own', 'group_id': gid, 'config': {'rounds': []},
            'algorithm_type': 'translation'}).id
        repo.commit()
        _set_visibility(TestCase, cid_own, 'private')
        _set_user(200)
        cid_other = repo.create_testcase({
            'id': 'c-bc2', 'name': 'other', 'group_id': gid, 'config': {'rounds': []},
            'algorithm_type': 'translation'}).id
        repo.commit()
        _set_visibility(TestCase, cid_other, 'private')

        # user 100 批量更新包含他人私有用例：仅自己的可见行被更新
        _set_user(100)
        resp = self._svc().batch_action({
            'action': 'update_algorithm_params',
            'ids': [cid_own, cid_other],
            'algorithm_params': [{'field_code': 'sample_rate', 'field_value': '16000'}],
        })
        assert resp['success'] is True
        session = get_db_session()
        try:
            own = session.get(TestCase, cid_own)
            other = session.get(TestCase, cid_other)
            assert own.algorithm_params  # 自己的私有用例被更新
            assert not other.algorithm_params  # 他人私有用例未被越权改写
        finally:
            session.close()

    def test_refresh_reference_sync_skips_private_non_owner(self):
        from task_service.infrastructure.persistence.models import TestCase
        repo = _get_tc_repo()
        _set_user(100)
        gid = repo.create_group_and_commit('g-bc3', 'bc3', '', '')['id']
        cid_own = repo.create_testcase({
            'id': 'c-bc3', 'name': 'own', 'group_id': gid, 'config': {'rounds': []},
            'algorithm_type': 'translation'}).id
        repo.commit()
        _set_visibility(TestCase, cid_own, 'private')
        _set_user(200)
        cid_other = repo.create_testcase({
            'id': 'c-bc4', 'name': 'other', 'group_id': gid, 'config': {'rounds': []},
            'algorithm_type': 'translation'}).id
        repo.commit()
        _set_visibility(TestCase, cid_other, 'private')

        _set_user(100)
        resp = self._svc()._batch_refresh_reference({'ids': [cid_own, cid_other]})
        # 同步路径：仅可见行被刷新（他人私有用例不计入）
        assert resp == '已成功刷新 1 个用例的参考参数'


# ---------------- 3c. group_id 直传建用例分组可见性校验（审计 P2 修复回归） ----------------

class TestCreateUnderPrivateGroup:
    def _create_case(self, user_id, group_id):
        from task_service.application.testcase.testcase_crud_service import testcase_crud_service
        _set_user(user_id)
        return testcase_crud_service.create({
            'name': 'case-x', 'group_id': group_id, 'config': {},
            'algorithm_type': 'translation',
        })

    def test_group_id_direct_private_non_owner_403(self, monkeypatch):
        """group_id 直传他人私有分组 → 403（审计 P2 修复）。"""
        from task_service.infrastructure.persistence.models import TestCaseGroup
        repo = _get_tc_repo()
        _set_user(100)
        gid = repo.create_group_and_commit('g-priv1', 'priv1', '', '')['id']
        _set_visibility(TestCaseGroup, gid, 'private')

        _silence_ref_params(monkeypatch)
        resp = self._create_case(200, gid)
        assert resp['code'] == 403

    def test_group_id_direct_private_owner_ok(self, monkeypatch):
        """私有分组 owner 以 group_id 直传建用例 → 201。"""
        from task_service.infrastructure.persistence.models import TestCaseGroup
        repo = _get_tc_repo()
        _set_user(100)
        gid = repo.create_group_and_commit('g-priv2', 'priv2', '', '')['id']
        _set_visibility(TestCaseGroup, gid, 'private')

        _silence_ref_params(monkeypatch)
        resp = self._create_case(100, gid)
        assert resp['code'] == 201

    def test_group_id_direct_shared_other_ok(self, monkeypatch):
        """共享分组下他人建用例不受限（零回归）。"""
        repo = _get_tc_repo()
        _set_user(100)
        gid = repo.create_group_and_commit('g-shr1', 'shr1', '', '')['id']

        _silence_ref_params(monkeypatch)
        resp = self._create_case(200, gid)
        assert resp['code'] == 201


# ---------------- 4. published_tasks ----------------

class TestPublishedTaskVisibility:
    def test_publish_writes_current_user_as_owner(self):
        from task_service.infrastructure.persistence.published_task_repository import published_task_repository
        from task_service.infrastructure.persistence.models import PublishedTask
        _set_user(500)
        pt = published_task_repository.create(
            name='pt1', source_task_id=1, task_type='e2e', algorithm_type='translation',
        )
        session = get_db_session()
        try:
            row = session.get(PublishedTask, pt.id)
            assert row.created_by_user_id == 500
            assert row.visibility == 'shared'
        finally:
            session.close()

    def test_legacy_null_owner_shared_access_ok(self):
        """存量 NULL owner 行（默认 shared）访问不报错。"""
        from task_service.infrastructure.persistence.published_task_repository import published_task_repository
        from task_service.infrastructure.persistence.models import PublishedTask
        _set_user(500)
        pt = published_task_repository.create(
            name='pt2', source_task_id=2, task_type='e2e', algorithm_type='translation',
        )
        _set_visibility(PublishedTask, pt.id, 'shared', owner=None)  # 存量 NULL owner
        _set_user(999)
        from task_service.application.services.published_task_service import published_task_service
        resp = published_task_service.get_detail(pt.id)
        assert resp['success'] is True

    def test_private_published_task_404_for_other(self):
        from task_service.infrastructure.persistence.published_task_repository import published_task_repository
        from task_service.infrastructure.persistence.models import PublishedTask
        _set_user(500)
        pt = published_task_repository.create(
            name='pt3', source_task_id=3, task_type='e2e', algorithm_type='translation',
        )
        _set_visibility(PublishedTask, pt.id, 'private')
        _set_user(999)
        from task_service.application.services.published_task_service import published_task_service
        resp = published_task_service.get_detail(pt.id)
        assert resp['code'] == 201  # 已发布任务不存在语义（404 映射）
