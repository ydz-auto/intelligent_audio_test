# -*- coding: utf-8 -*-
"""INT-2242 专项：分组写路径缺可见性/软删校验的修复回归。

覆盖验收标准：
1. 分组按名称/ID 解析的仓储方法不再命中软删分组（get_group_by_name /
   get_group_by_id / get_group_by_name_as_dict 口径一致），同名再建不误判；
2. 批量复制/移动到他人私有分组 → 403；目标为软删分组 → 404；共享分组正常；
3. 用例改分组（group_id 直传 / group 名称）到他人私有分组 → 403；软删分组 →
   404（按名称自动建组时不再复用已删分组）；
4. copy_by_group 源分组软删/他人私有 → 404，同名目标分组为他人私有时不复用
   （另建当前用户自己的分组）。

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表，
用例内清理（对齐 test_int463 口径）。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.infrastructure.user_context import set_current_user_id, set_current_user_is_admin
from shared.models.database import (
    Base, init_db, get_engine, get_db_session,
)

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
    _ensure_tables()
    session = get_db_session()
    try:
        for table in reversed(_TABLES):
            session.execute(table.delete())
        session.commit()
    finally:
        session.close()
    yield
    set_current_user_id(None)
    set_current_user_is_admin(False)


def _set_user(user_id=None, is_admin=False):
    set_current_user_id(user_id)
    set_current_user_is_admin(is_admin)


def _repo():
    from task_service.infrastructure.persistence.testcase_repository import testcase_repository
    return testcase_repository


_UNSET = object()


def _set_visibility(table, row_id, visibility, owner=_UNSET):
    """直接置行 visibility / owner（测试夹具；生产经命令侧写入）。"""
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


def _make_group(group_id, name, user_id, visibility=None):
    _set_user(user_id)
    return _repo().create_group_and_commit(group_id, name, '', '', visibility=visibility)['id']


def _make_case(case_id, group_id, user_id, visibility=None):
    _set_user(user_id)
    repo = _repo()
    repo.create_testcase({
        'id': case_id, 'name': case_id, 'group_id': group_id,
        'config': {'rounds': []}, 'algorithm_type': 'translation',
        'visibility': visibility,
    })
    repo.commit()
    return case_id


def _group_row(group_id):
    from task_service.infrastructure.persistence.models import TestCaseGroup
    session = get_db_session()
    try:
        return session.get(TestCaseGroup, group_id)
    finally:
        session.close()


def _case_row(case_id):
    from task_service.infrastructure.persistence.models import TestCase
    session = get_db_session()
    try:
        return session.get(TestCase, case_id)
    finally:
        session.close()


def _count_cases_in_group(group_id):
    from task_service.infrastructure.persistence.models import TestCase
    session = get_db_session()
    try:
        return session.query(TestCase).filter_by(group_id=group_id, deleted=False).count()
    finally:
        session.close()


class _FakeIdempotencyStore:
    """内存幂等仓储替身（对齐 test_int463 口径）。"""

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


def _batch_svc():
    from task_service.application.testcase.testcase_batch_service import TestCaseBatchService
    return TestCaseBatchService(repo=_repo(), idempotency_store=_FakeIdempotencyStore())


# ---------------- 1. 仓储解析过滤软删分组 ----------------

class TestGroupLookupIgnoresSoftDeleted:
    def test_by_name_and_id_ignore_soft_deleted(self):
        _set_user(100)
        repo = _repo()
        repo.create_group_and_commit('g-del', 'deleted-grp', '', '')
        repo.delete_group_and_commit('g-del')

        assert repo.get_group_by_name('deleted-grp') is None
        assert repo.get_group_by_id('g-del') is None
        # 读路径（分组重名校验 / 详情）口径一致：软删分组视为不存在
        assert repo.get_group_by_name_as_dict('deleted-grp') is None
        assert repo.get_group_by_id_as_dict('g-del') is None

    def test_live_group_still_resolvable(self):
        _set_user(100)
        repo = _repo()
        repo.create_group_and_commit('g-live', 'live-grp', '', '')
        assert repo.get_group_by_name('live-grp').id == 'g-live'
        assert repo.get_group_by_id('g-live').id == 'g-live'


# ---------------- 2. 批量复制/移动目标分组校验 ----------------

class TestBatchCopyMoveTargetGroup:
    def _setup_shared_case(self, case_id='c-a'):
        """共享分组 + 用户 A 的共享用例（源数据）。"""
        _make_group('g-src', 'src', 100)
        return _make_case(case_id, 'g-src', 200)

    def test_copy_to_other_private_group_403(self):
        gid = _make_group('g-b-priv', 'b-priv', 100)
        _set_visibility(_group_model(), gid, 'private', owner=100)
        cid = self._setup_shared_case()

        _set_user(200)
        resp = _batch_svc().batch_action({
            'action': 'copy_to_group', 'ids': [cid], 'target_group_id': gid,
            'idempotency_key': 'int2242-copy-priv',
        })
        assert resp['success'] is False
        assert resp['code'] == 403
        assert _count_cases_in_group(gid) == 0  # 未写入他人私有分组

    def test_move_to_other_private_group_403(self):
        gid = _make_group('g-b-priv2', 'b-priv2', 100)
        _set_visibility(_group_model(), gid, 'private', owner=100)
        cid = self._setup_shared_case('c-move')

        _set_user(200)
        resp = _batch_svc().batch_action({
            'action': 'move_to_group', 'ids': [cid], 'target_group_id': gid,
            'idempotency_key': 'int2242-move-priv',
        })
        assert resp['success'] is False
        assert resp['code'] == 403
        assert _case_row(cid).group_id == 'g-src'  # 归属未变

    def test_copy_to_soft_deleted_group_404(self):
        _set_user(100)
        repo = _repo()
        repo.create_group_and_commit('g-dead', 'dead', '', '')
        repo.delete_group_and_commit('g-dead')
        cid = self._setup_shared_case('c-dead')

        _set_user(200)
        resp = _batch_svc().batch_action({
            'action': 'copy_to_group', 'ids': [cid], 'target_group_id': 'g-dead',
            'idempotency_key': 'int2242-copy-dead',
        })
        assert resp['success'] is False
        assert resp['code'] == 404
        assert _count_cases_in_group('g-dead') == 0

    def test_move_to_soft_deleted_group_404(self):
        _set_user(100)
        repo = _repo()
        repo.create_group_and_commit('g-dead2', 'dead2', '', '')
        repo.delete_group_and_commit('g-dead2')
        cid = self._setup_shared_case('c-dead2')

        _set_user(200)
        resp = _batch_svc().batch_action({
            'action': 'move_to_group', 'ids': [cid], 'target_group_id': 'g-dead2',
            'idempotency_key': 'int2242-move-dead',
        })
        assert resp['success'] is False
        assert resp['code'] == 404
        assert _case_row(cid).group_id == 'g-src'

    def test_copy_to_shared_group_ok(self):
        _make_group('g-shared', 'shared', 100)
        cid = self._setup_shared_case('c-ok')

        _set_user(200)
        resp = _batch_svc().batch_action({
            'action': 'copy_to_group', 'ids': [cid], 'target_group_id': 'g-shared',
            'idempotency_key': 'int2242-copy-shared',
        })
        assert resp['success'] is True, resp
        assert _count_cases_in_group('g-shared') == 1


class TestBatchCopyByGroup:
    def test_source_group_soft_deleted_404(self):
        _set_user(100)
        repo = _repo()
        repo.create_group_and_commit('g-bgs', 'bgs', '', '')
        _make_case('c-bgs', 'g-bgs', 100)
        repo.delete_group_and_commit('g-bgs')

        _set_user(200)
        resp = _batch_svc().batch_action({
            'action': 'copy_by_group', 'group_name': 'bgs',
            'idempotency_key': 'int2242-cbg-dead',
        })
        assert resp['success'] is False
        assert resp['code'] == 404

    def test_source_group_other_private_404(self):
        gid = _make_group('g-bgp', 'bgp', 100)
        _make_case('c-bgp', gid, 100)
        _set_visibility(_group_model(), gid, 'private', owner=100)

        _set_user(200)
        resp = _batch_svc().batch_action({
            'action': 'copy_by_group', 'group_name': 'bgp',
            'idempotency_key': 'int2242-cbg-priv',
        })
        assert resp['success'] is False
        assert resp['code'] == 404

    def test_private_same_name_target_not_reused(self):
        """同名目标分组为他人私有 → 另建当前用户自己的分组，不写入他人分组。"""
        _make_group('g-bgs2', 'bgs2', 100)
        _make_case('c-bgs2', 'g-bgs2', 100)

        # 用户 100 另有一个同名 bgs2_copy 私有分组（不可被 200 复用）
        priv_copy = _make_group('g-b-private-copy', 'bgs2_copy', 100)
        _set_visibility(_group_model(), priv_copy, 'private', owner=100)

        _set_user(200)
        resp = _batch_svc().batch_action({
            'action': 'copy_by_group', 'group_name': 'bgs2',
            'idempotency_key': 'int2242-cbg-reuse',
        })
        assert resp['success'] is True, resp

        # 复制结果落在 200 自己新建的 bgs2_copy 分组，而非 100 的私有同名分组
        assert _count_cases_in_group(priv_copy) == 0
        from task_service.infrastructure.persistence.models import TestCaseGroup
        session = get_db_session()
        try:
            own = session.query(TestCaseGroup).filter_by(
                name='bgs2_copy', created_by_user_id=200, deleted=False).first()
            assert own is not None
            assert own.visibility == 'shared'  # 继承源分组可见性
            assert _count_cases_in_group(own.id) == 1
        finally:
            session.close()


# ---------------- 3. 用例改分组校验 ----------------

class TestUpdateCaseGroupAssignment:
    def _own_case(self, case_id='c-own'):
        _make_group('g-own', 'own-grp', 200)
        return _make_case(case_id, 'g-own', 200)

    def test_update_to_other_private_group_403(self):
        gid = _make_group('g-p1', 'p1', 100)
        _set_visibility(_group_model(), gid, 'private', owner=100)
        cid = self._own_case()

        _set_user(200)
        from task_service.application.testcase.testcase_crud_service import testcase_crud_service
        resp = testcase_crud_service.update(cid, {'group_id': gid})
        assert resp['success'] is False
        assert resp['code'] == 403
        assert _case_row(cid).group_id == 'g-own'

    def test_update_to_soft_deleted_group_404(self):
        _set_user(100)
        repo = _repo()
        repo.create_group_and_commit('g-d1', 'd1', '', '')
        repo.delete_group_and_commit('g-d1')
        cid = self._own_case('c-d1')

        _set_user(200)
        from task_service.application.testcase.testcase_crud_service import testcase_crud_service
        resp = testcase_crud_service.update(cid, {'group_id': 'g-d1'})
        assert resp['success'] is False
        assert resp['code'] == 404
        assert _case_row(cid).group_id == 'g-own'

    def test_update_to_shared_group_ok(self):
        shared = _make_group('g-sh1', 'sh1', 100)
        cid = self._own_case('c-sh1')

        _set_user(200)
        from task_service.application.testcase.testcase_crud_service import testcase_crud_service
        resp = testcase_crud_service.update(cid, {'group_id': shared})
        assert resp['success'] is True, resp
        assert _case_row(cid).group_id == shared

    def test_update_by_private_group_name_403(self):
        gid = _make_group('g-p2', 'p-name', 100)
        _set_visibility(_group_model(), gid, 'private', owner=100)
        cid = self._own_case('c-pname')

        _set_user(200)
        from task_service.application.testcase.testcase_crud_service import testcase_crud_service
        resp = testcase_crud_service.update(cid, {'group': 'p-name'})
        assert resp['success'] is False
        assert resp['code'] == 403
        assert _case_row(cid).group_id == 'g-own'

    def test_update_by_soft_deleted_group_name_creates_new(self):
        """同名已删分组不复用：自动建新分组，用例不挂到软删分组上。"""
        _set_user(100)
        repo = _repo()
        repo.create_group_and_commit('g-d2', 'd-name', '', '')
        repo.delete_group_and_commit('g-d2')
        cid = self._own_case('c-dname')

        _set_user(200)
        from task_service.application.testcase.testcase_crud_service import testcase_crud_service
        resp = testcase_crud_service.update(cid, {'group': 'd-name'})
        assert resp['success'] is True, resp

        new_group_id = _case_row(cid).group_id
        assert new_group_id != 'g-d2'
        new_group = _group_row(new_group_id)
        assert new_group is not None
        assert new_group.deleted is False
        assert new_group.created_by_user_id == 200


# ---------------- 4. 分组重名检查不误判软删分组 ----------------

class TestGroupCreateNameCheck:
    def test_soft_deleted_same_name_can_be_recreated(self):
        """GroupService.create 经 as_dict 查重：软删同名分组不阻断重新创建。"""
        _set_user(100)
        repo = _repo()
        repo.create_group_and_commit('g-dup', 'dup', '', '')
        repo.delete_group_and_commit('g-dup')

        # 网关 create 的重名校验走 gRPC GetTestCaseGroupByName（as_dict 口径）
        assert repo.get_group_by_name_as_dict('dup') is None

        _set_user(200)
        new_id = _make_group('g-dup2', 'dup', 200)
        assert new_id == 'g-dup2'
        row = _group_row('g-dup2')
        assert row.deleted is False
        assert row.created_by_user_id == 200


def _group_model():
    from task_service.infrastructure.persistence.models import TestCaseGroup
    return TestCaseGroup
