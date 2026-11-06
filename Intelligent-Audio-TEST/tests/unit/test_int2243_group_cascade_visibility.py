# -*- coding: utf-8 -*-
"""INT-2243 分组级联删除越权：他人私有用例不得被连带软删。

缺陷：delete_group_and_commit(cascade=True) 只校验分组自身可见性，对组内
全部未删用例无条件批量软删——共享分组下他人创建的 private 用例被一并删除。

覆盖验收标准：
1. 他人私有用例不被级联删除（deleted / deleted_at / deleted_by_user_id 均不动）
2. 共享用例、本人私有用例正常级联删除
3. 回执条数与实际一致（deleted_case_count / skipped_case_count）
4. 非级联删除计数为 0，组内用例原样保留
5. 网关回执文案与条数一致

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表，
用例内清理，对齐 test_int463_task_service_visibility.py 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.infrastructure.user_context import set_current_user_id, set_current_user_is_admin
from shared.models.database import Base, init_db, get_engine, get_db_session
from task_service.infrastructure.persistence.models import TestCase, TestCaseGroup

OWNER_A = 1101
OWNER_B = 1102

_TABLES = None


def _ensure_tables():
    init_db(pool_size=2)
    global _TABLES
    if _TABLES is None:
        _TABLES = [TestCaseGroup.__table__, TestCase.__table__]
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
    set_current_user_id(None)
    set_current_user_is_admin(False)


def _set_user(user_id=None, is_admin=False):
    set_current_user_id(user_id)
    set_current_user_is_admin(is_admin)


_CONFIG = {'rounds': []}


def _seed_group(gid='g-int2243', owner=OWNER_A, visibility='shared'):
    """共享分组 + 四条用例：A 的 shared / private，B 的 shared / private。"""
    session = get_db_session()
    try:
        session.add(TestCaseGroup(
            id=gid, name=f'组_{gid}', algorithm_type='translation',
            created_by_user_id=owner, visibility=visibility,
        ))
        session.add_all([
            TestCase(id=f'{gid}-a-shared', name='A共享', config=_CONFIG,
                     group_id=gid, created_by_user_id=OWNER_A, visibility='shared'),
            TestCase(id=f'{gid}-a-private', name='A私有', config=_CONFIG,
                     group_id=gid, created_by_user_id=OWNER_A, visibility='private'),
            TestCase(id=f'{gid}-b-shared', name='B共享', config=_CONFIG,
                     group_id=gid, created_by_user_id=OWNER_B, visibility='shared'),
            TestCase(id=f'{gid}-b-private', name='B私有', config=_CONFIG,
                     group_id=gid, created_by_user_id=OWNER_B, visibility='private'),
        ])
        session.commit()
    finally:
        session.close()


def _case_row(cid):
    session = get_db_session()
    try:
        return session.get(TestCase, cid)
    finally:
        session.close()


def _delete(gid='g-int2243', cascade=True):
    from task_service.infrastructure.persistence.testcase_repository import (
        testcase_repository,
    )
    return testcase_repository.delete_group_and_commit(gid, cascade=cascade)


class TestCascadeVisibilityFilter:
    """task_service：级联删除逐行校验用例 owner。"""

    def test_skips_other_users_private_case(self):
        _seed_group()
        _set_user(OWNER_A)

        result = _delete(cascade=True)

        assert result['cascade'] is True
        assert result['deleted_case_count'] == 3, 'A共享 + A私有 + B共享 应被删除'
        assert result['skipped_case_count'] == 1, 'B 的私有用例应被跳过'

        session = get_db_session()
        try:
            group = session.get(TestCaseGroup, 'g-int2243')
            assert group.deleted is True
            assert group.deleted_by_user_id == OWNER_A
        finally:
            session.close()

        for cid in ('g-int2243-a-shared', 'g-int2243-a-private',
                    'g-int2243-b-shared'):
            row = _case_row(cid)
            assert row.deleted is True, f'{cid} 应被级联软删'
            assert row.deleted_at is not None
            assert row.deleted_by_user_id == OWNER_A

        kept = _case_row('g-int2243-b-private')
        assert kept.deleted is False, '他人私有用例不得被级联删除'
        assert kept.deleted_at is None
        assert kept.deleted_by_user_id is None, '跳过行的删除人不落任何值'

    def test_own_private_and_shared_deleted(self):
        """本人私有用例与共享用例属可见范围，正常级联删除。"""
        _seed_group('g-int2243-own', owner=OWNER_B)
        _set_user(OWNER_B)

        result = _delete('g-int2243-own', cascade=True)

        assert result['deleted_case_count'] == 3
        assert result['skipped_case_count'] == 1
        assert _case_row('g-int2243-own-b-private').deleted is True
        assert _case_row('g-int2243-own-a-private').deleted is False

    def test_admin_deletes_all(self):
        _seed_group('g-int2243-admin')
        _set_user(1, is_admin=True)

        result = _delete('g-int2243-admin', cascade=True)

        assert result['deleted_case_count'] == 4
        assert result['skipped_case_count'] == 0
        assert _case_row('g-int2243-admin-b-private').deleted is True

    def test_unauthenticated_deletes_shared_only(self):
        """未认证（AUTH_MODE=off 占位身份）：仅共享用例可删，私有行一律跳过。"""
        _seed_group('g-int2243-anon')
        _set_user(None)

        result = _delete('g-int2243-anon', cascade=True)

        assert result['deleted_case_count'] == 2
        assert result['skipped_case_count'] == 2
        assert _case_row('g-int2243-anon-a-shared').deleted is True
        assert _case_row('g-int2243-anon-b-shared').deleted is True
        assert _case_row('g-int2243-anon-a-private').deleted is False
        assert _case_row('g-int2243-anon-b-private').deleted is False

    def test_non_cascade_keeps_cases(self):
        _seed_group('g-int2243-plain')
        _set_user(OWNER_A)

        result = _delete('g-int2243-plain', cascade=False)

        assert result['cascade'] is False
        assert result['deleted_case_count'] == 0
        assert result['skipped_case_count'] == 0
        assert _case_row('g-int2243-plain-a-shared').deleted is False
        assert _case_row('g-int2243-plain-b-private').deleted is False


class TestDeleteReceiptMessage:
    """api_gateway：删除回执条数与实际一致。"""

    def test_message_reports_deleted_and_skipped(self):
        from api_gateway.application.services.group_service import _delete_message

        assert _delete_message({
            'id': 'g', 'cascade': True,
            'deleted_case_count': 3, 'skipped_case_count': 1,
        }) == '分组已删除，级联删除用例 3 条，1 条非本人私有用例未删除'

    def test_message_without_skip(self):
        from api_gateway.application.services.group_service import _delete_message

        assert _delete_message({
            'id': 'g', 'cascade': True,
            'deleted_case_count': 3, 'skipped_case_count': 0,
        }) == '分组已删除，级联删除用例 3 条'

    def test_message_legacy_shape_unchanged(self):
        """非级联 / 旧形态回执（无计数键）文案不变。"""
        from api_gateway.application.services.group_service import _delete_message

        assert _delete_message({'id': 'g'}) == '分组已删除'
        assert _delete_message({'id': 'g', 'cascade': False}) == '分组已删除'

    def test_group_service_delete_surfaces_counts(self, monkeypatch):
        """网关 DELETE 回执带上级联实删/跳过条数。"""
        from types import SimpleNamespace

        import api_gateway.application.services.group_service as group_mod
        import api_gateway.infrastructure.grpc_proxies as proxies_pkg
        from api_gateway.infrastructure.request_adapter import set_current_request

        class _StubTds:
            def get_testcase_stats(self, **kwargs):
                return {'total': 4}

            def delete_testcase_group(self, group_id, cascade=False):
                return {
                    'id': group_id, 'cascade': True,
                    'deleted_case_count': 3, 'skipped_case_count': 1,
                }

        monkeypatch.setattr(proxies_pkg, 'task_data_service', _StubTds())
        state = SimpleNamespace(_json_body=None, _files={}, _form_data={})
        set_current_request(SimpleNamespace(
            state=state, query_params={'cascade': 'true'},
            method='DELETE', is_json=False, headers={}))
        try:
            payload, http_code = group_mod.GroupService.delete('g-int2243')
        finally:
            set_current_request(None)

        assert http_code == 200
        assert payload['message'] == '分组已删除，级联删除用例 3 条，1 条非本人私有用例未删除'
