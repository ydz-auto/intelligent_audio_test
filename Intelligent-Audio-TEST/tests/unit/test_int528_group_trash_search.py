# -*- coding: utf-8 -*-
"""INT-528 专项：分组列表回收站态搜索已删用例（分组视图空白根因）。

缺陷：回收站态分组视图 `fetchTestCases` 并行调用 getGroups({keyword}) 与
getAll({onlyDeleted: true, keyword})，而 /groups 的 keyword 筛选在 task_service
统计实现中硬过滤 deleted == False，已删用例被排除 → case_counts 为空 →
分组视图空白。INT-528 修复：get_testcase_stats 增 deleted/favorite 口径
（镜像 get_task_stats.deleted），网关 GroupListQuery 增 only_deleted/favorite，
前端 getGroups 透传。

本文件锁定仓储层统计口径（与 query_testcases 一致的 per-user 收藏过滤）：
- deleted=True 仅统计回收站（软删除）用例；默认仅未删除（既有行为不回归）
- favorite=True 仅当前用户收藏（user_id 缺失恒空）
- favorite 与 deleted 组合（回收站内收藏项）
- keyword + deleted 组合（回收站态搜索已删用例名 → 分组计数命中）

DB：进程级 SQLite（tests/conftest.py 注入），对齐 test_int215 口径。
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
            TestCaseGroup, TestCase, Favorite,
        )
        _TABLES = [t.__table__ for t in (TestCaseGroup, TestCase, Favorite)]
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
def _stats_env():
    tables = _ensure_tables()
    _cleanup_tables(tables)
    yield tables
    _cleanup_tables(tables)


def _add_cases(*specs):
    """specs: (case_id, group_id, deleted, favorite_user_id) 元组。"""
    from task_service.infrastructure.persistence.models import (
        TestCase, TestCaseGroup, Favorite,
    )

    session = get_db_session()
    try:
        group = TestCaseGroup(id='g1', name='回收组', algorithm_type='translation')
        session.add(group)
        session.commit()
        for case_id, gid, deleted, fav_user in specs:
            session.add(TestCase(
                id=case_id, name=f'用例{case_id}', description=f'desc{case_id}',
                config={}, group_id=gid, algorithm_type='translation',
                deleted=deleted,
            ))
        session.commit()
        for case_id, _gid, _d, fav_user in specs:
            if fav_user is not None:
                session.add(Favorite(
                    user_id=fav_user, entity_type='testcase', entity_id=case_id))
        session.commit()
        return group.id
    finally:
        remove_db_session()


class TestStatsDeletedScope:
    """get_testcase_stats 回收站口径（INT-528）。"""

    def test_deleted_true_counts_trashed_only(self):
        from task_service.infrastructure.persistence._testcase_query_mixin import TestCaseQueryMixin
        repo = TestCaseQueryMixin()

        _add_cases(('A1', 'g1', False, None), ('A2', 'g1', True, None))
        assert repo.get_testcase_stats(deleted=True)['total'] == 1
        assert repo.get_testcase_stats(deleted=False)['total'] == 1
        assert repo.get_testcase_stats()['total'] == 1, '默认口径不应回归（仅未删除）'

    def test_keyword_plus_deleted_matches_trashed_case(self):
        from task_service.infrastructure.persistence._testcase_query_mixin import TestCaseQueryMixin
        repo = TestCaseQueryMixin()

        _add_cases(('B1', 'g1', True, None))
        # 回收站态搜索已删用例名 → 命中
        assert repo.get_testcase_stats(keyword='B1', deleted=True)['total'] == 1
        items = repo.get_testcase_stats(keyword='B1', deleted=True, group_by='group_id')['items']
        assert items == [{'key': 'g1', 'count': 1}]
        # 默认活跃口径不命中已删
        assert repo.get_testcase_stats(keyword='B1')['total'] == 0


class TestStatsFavoriteScope:
    """get_testcase_stats 收藏口径（INT-528，per-user）。"""

    def test_favorite_filters_by_user(self):
        from task_service.infrastructure.persistence._testcase_query_mixin import TestCaseQueryMixin
        repo = TestCaseQueryMixin()

        _add_cases(('F1', 'g1', False, 901), ('F2', 'g1', False, None))
        assert repo.get_testcase_stats(favorite=True, user_id=901)['total'] == 1
        assert repo.get_testcase_stats(favorite=True, user_id=902)['total'] == 0
        items = repo.get_testcase_stats(favorite=True, user_id=901, group_by='group_id')['items']
        assert items == [{'key': 'g1', 'count': 1}]

    def test_favorite_without_user_returns_empty(self):
        from task_service.infrastructure.persistence._testcase_query_mixin import TestCaseQueryMixin
        repo = TestCaseQueryMixin()

        _add_cases(('F3', 'g1', False, 901))
        assert repo.get_testcase_stats(favorite=True)['total'] == 0
        assert repo.get_testcase_stats(favorite=True, group_by='group_id')['items'] == []

    def test_favorite_plus_deleted_combine(self):
        from task_service.infrastructure.persistence._testcase_query_mixin import TestCaseQueryMixin
        repo = TestCaseQueryMixin()

        _add_cases(('G1', 'g1', True, 901), ('G2', 'g1', True, None))
        # 回收站内该用户收藏项
        assert repo.get_testcase_stats(favorite=True, deleted=True, user_id=901)['total'] == 1
        assert repo.get_testcase_stats(favorite=True, deleted=True, user_id=902)['total'] == 0
