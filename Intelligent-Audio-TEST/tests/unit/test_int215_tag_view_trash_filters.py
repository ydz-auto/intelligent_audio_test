# -*- coding: utf-8 -*-
"""INT-215 专项：标签视图回收站/收藏过滤（query_testcases_by_tag_ids）。

背景：INT-212 审计 P1——标签视图回收站断链：fetchTagView 未透传 only_deleted/
favorite，SQL 侧 query_testcases_by_tag_ids 也没有对应过滤参数，回收站下
标签视图仍显示活跃用例。INT-215 贯通后由本文件锁仓储层口径（与
query_testcases 一致），防止回归。

覆盖：
- only_deleted=True 仅返回软删项；默认（include_deleted=False）仅活跃项
- include_deleted=True 含活跃+已删
- only_deleted 优先于 include_deleted（组合不放大集合）
- favorite=True 仅当前用户收藏（per-user）；无 user_id 返回空集合
- favorite 与 only_deleted 组合（回收站内收藏项）

DB：进程级 SQLite（tests/conftest.py 注入），对齐 test_int193/test_int141 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)


_TABLES = None


def _ensure_tables():
    init_db(pool_size=2)
    global _TABLES
    if _TABLES is None:
        from task_service.infrastructure.persistence.models import (
            Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation,
            TestResult, TagCategory, Tag, TestCaseGroup, TestCase, TestCaseTag,
            Favorite, Log,
        )
        _TABLES = [t.__table__ for t in (
            Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation,
            TestResult, TagCategory, Tag, TestCaseGroup, TestCase, TestCaseTag,
            Favorite, Log,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLES)
    return _TABLES


def _cleanup_tables(tables):
    session = get_db_session()
    try:
        for table in tables:
            session.execute(table.delete())
        session.commit()
    finally:
        remove_db_session()


@pytest.fixture(autouse=True)
def _tag_view_env():
    tables = _ensure_tables()
    _cleanup_tables(tables)
    yield tables
    _cleanup_tables(tables)


def _add_tagged_cases(tag_name, *specs):
    """specs: (case_id, deleted) 元组；返回 tag_id。"""
    from task_service.infrastructure.persistence.models import TestCase, Tag, TestCaseTag

    session = get_db_session()
    try:
        session.add(Tag(name=tag_name))
        session.commit()
        tag = session.query(Tag).filter_by(name=tag_name).one()
        rows = []
        for i, (case_id, deleted) in enumerate(specs, start=1):
            rows.append(TestCase(id=case_id, name=f'用例{case_id}', config={},
                                 deleted=deleted))
        session.add_all(rows)
        session.commit()
        # 关联表主键为 BigInteger，SQLite 不自增，显式赋 id
        session.add_all([
            TestCaseTag(id=i, test_case_id=cid, tag_id=tag.id)
            for i, (cid, _d) in enumerate(specs, start=1)
        ])
        session.commit()
        return tag.id
    finally:
        remove_db_session()


def _favorite(user_id, case_id):
    from task_service.infrastructure.persistence.models import Favorite

    session = get_db_session()
    try:
        session.add(Favorite(user_id=user_id, entity_type='testcase', entity_id=case_id))
        session.commit()
    finally:
        remove_db_session()


class TestTagViewOnlyDeleted:
    """标签视图 only_deleted 口径（INT-215 P1）。"""

    def test_only_deleted_returns_trashed_only(self):
        from task_service.infrastructure.persistence.testcase_repository import (
            testcase_repository,
        )

        tag_id = _add_tagged_cases(
            'INT215回收标签',
            ('INT215_A1', False),
            ('INT215_A2', False),
            ('INT215_D1', True),
        )
        rows = testcase_repository.query_testcases_by_tag_ids(
            [tag_id], only_deleted=True)
        assert {tc.id for tc in rows} == {'INT215_D1'}
        assert all(tc.deleted for tc in rows)

    def test_default_returns_active_only(self):
        from task_service.infrastructure.persistence.testcase_repository import (
            testcase_repository,
        )

        tag_id = _add_tagged_cases(
            'INT215默认标签',
            ('INT215_B1', False),
            ('INT215_D2', True),
        )
        rows = testcase_repository.query_testcases_by_tag_ids([tag_id])
        assert {tc.id for tc in rows} == {'INT215_B1'}

        incl = testcase_repository.query_testcases_by_tag_ids(
            [tag_id], include_deleted=True)
        assert {tc.id for tc in incl} == {'INT215_B1', 'INT215_D2'}

    def test_only_deleted_overrides_include_deleted(self):
        from task_service.infrastructure.persistence.testcase_repository import (
            testcase_repository,
        )

        tag_id = _add_tagged_cases(
            'INT215组合标签',
            ('INT215_C1', False),
            ('INT215_D3', True),
        )
        rows = testcase_repository.query_testcases_by_tag_ids(
            [tag_id], include_deleted=True, only_deleted=True)
        assert {tc.id for tc in rows} == {'INT215_D3'}


class TestTagViewFavoriteFilter:
    """标签视图 favorite per-user 口径（INT-215 P1/P6）。"""

    def test_favorite_filters_by_user(self):
        from task_service.infrastructure.persistence.testcase_repository import (
            testcase_repository,
        )

        tag_id = _add_tagged_cases(
            'INT215收藏标签',
            ('INT215_F1', False),
            ('INT215_F2', False),
        )
        _favorite(901, 'INT215_F1')

        mine = testcase_repository.query_testcases_by_tag_ids(
            [tag_id], favorite=True, user_id=901)
        assert {tc.id for tc in mine} == {'INT215_F1'}

        others = testcase_repository.query_testcases_by_tag_ids(
            [tag_id], favorite=True, user_id=902)
        assert others == []

    def test_favorite_without_user_returns_empty(self):
        from task_service.infrastructure.persistence.testcase_repository import (
            testcase_repository,
        )

        tag_id = _add_tagged_cases(
            'INT215无用户标签', ('INT215_G1', False))
        _favorite(903, 'INT215_G1')

        assert testcase_repository.query_testcases_by_tag_ids(
            [tag_id], favorite=True) == []

    def test_favorite_within_trash(self):
        """回收站态收藏过滤（favorite+only_deleted 组合）。"""
        from task_service.infrastructure.persistence.testcase_repository import (
            testcase_repository,
        )

        tag_id = _add_tagged_cases(
            'INT215站内收藏标签',
            ('INT215_H1', True),
            ('INT215_H2', True),
        )
        _favorite(905, 'INT215_H2')

        rows = testcase_repository.query_testcases_by_tag_ids(
            [tag_id], only_deleted=True, favorite=True, user_id=905)
        assert {tc.id for tc in rows} == {'INT215_H2'}
