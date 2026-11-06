# -*- coding: utf-8 -*-
"""INT-215 P2-R1 回归：fetch_case_ids 服务层算法/维度过滤透传。

背景（验收打回项）：task_service 服务层 fetch_case_ids 仅读
group/test_type/search/tag/only_deleted，丢弃 algorithm_type/dimension_id
（仓储层 fetch_case_ids 早已支持并正确过滤）。后果：
- 回收站「全部恢复」在算法/维度筛选下按**忽略筛选的全量已删集合**恢复
  （确认弹窗 N 与可见列表不符，恢复超集）；
- E2E/API 起跑链路（useE2eExecution/useE2eView.testRun/apiTest.steps）
  按当前算法筛选圈定用例时 algorithm_type 同样被静默忽略。

覆盖（直驱 TestCaseQueryService.fetch_case_ids，断言 ids 差集）：
- only_deleted 无过滤 → 全量已删集合
- only_deleted + algorithm_type → 筛选生效（修复前为超集）
- only_deleted + dimension_id → 筛选生效
- only_deleted + 两者组合 → 交集
- 活跃路径 + algorithm_type / dimension_id（E2E/API 起跑口径）→ 筛选生效

DB：进程级 SQLite（tests/conftest.py 注入），对齐 test_int215_tag_view_trash_filters
口径。维度过滤为 config JSON 全文 LIKE 匹配 '"id": N'，造数用单位数 id 避免前缀碰撞。
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
def _fetch_ids_env():
    tables = _ensure_tables()
    _cleanup_tables(tables)
    yield tables
    _cleanup_tables(tables)


def _seed_cases():
    """四用例覆盖 算法(a/b) × 维度(1/2) × 生命周期(活跃/已删)：

    - P215_A: algo_a, 维度1, 已删
    - P215_B: algo_b, 维度2, 已删
    - P215_C: algo_a, 维度2, 已删
    - P215_D: algo_a, 维度1, 活跃
    """
    from task_service.infrastructure.persistence.models import TestCase

    session = get_db_session()
    try:
        session.add_all([
            TestCase(id='P215_A', name='用例A',
                     config={'dimensions': [{'id': 1}]},
                     algorithm_type='algo_a', deleted=True),
            TestCase(id='P215_B', name='用例B',
                     config={'dimensions': [{'id': 2}]},
                     algorithm_type='algo_b', deleted=True),
            TestCase(id='P215_C', name='用例C',
                     config={'dimensions': [{'id': 2}]},
                     algorithm_type='algo_a', deleted=True),
            TestCase(id='P215_D', name='用例D',
                     config={'dimensions': [{'id': 1}]},
                     algorithm_type='algo_a', deleted=False),
        ])
        session.commit()
    finally:
        remove_db_session()


def _fetch_ids(**params):
    from task_service.application.testcase.testcase_query_service import (
        TestCaseQueryService,
    )
    result = TestCaseQueryService().fetch_case_ids(params)
    assert result['success'], result
    return sorted(result['data']['ids'])


class TestFetchCaseIdsFilterPassThrough:
    """服务层 algorithm_type/dimension_id 透传（P2-R1 修复断言）。"""

    def test_only_deleted_without_filter_returns_full_trash(self):
        _seed_cases()
        assert _fetch_ids(only_deleted=True) == ['P215_A', 'P215_B', 'P215_C']

    def test_only_deleted_with_algorithm_type_filters(self):
        # 修复前：服务层丢弃 algorithm_type，此处返回超集 [A,B,C]
        _seed_cases()
        assert _fetch_ids(only_deleted=True, algorithm_type='algo_a') == [
            'P215_A', 'P215_C',
        ]

    def test_only_deleted_with_dimension_id_filters(self):
        _seed_cases()
        assert _fetch_ids(only_deleted=True, dimension_id=2) == [
            'P215_B', 'P215_C',
        ]

    def test_only_deleted_with_combined_filters_intersects(self):
        _seed_cases()
        assert _fetch_ids(
            only_deleted=True, algorithm_type='algo_a', dimension_id=2,
        ) == ['P215_C']

    def test_active_path_with_algorithm_type_filters(self):
        # E2E/API 起跑圈定口径：活跃集合按算法过滤（修复前返回全集 [A,B,C,D]）
        _seed_cases()
        assert _fetch_ids(algorithm_type='algo_a') == ['P215_D']

    def test_active_path_with_dimension_id_filters(self):
        _seed_cases()
        assert _fetch_ids(dimension_id=1) == ['P215_D']

    def test_test_type_param_ignored_and_search_still_works(self):
        # 用例不再区分 api/e2e：type 参数不参与过滤（返回全部活跃用例）；
        # search 在回收站路径生效
        _seed_cases()
        assert _fetch_ids(type='e2e') == ['P215_D']
        assert _fetch_ids(search='用例A', only_deleted=True) == ['P215_A']
