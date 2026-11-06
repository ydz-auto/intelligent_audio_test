# -*- coding: utf-8 -*-
"""INT-2240 专项：用例维度筛选 LIKE 右界（维度 3 不得命中 30/31/300）。

缺陷：`build_dim_id_filter` 的 LIKE 模式以裸 `%` 收尾，`%"id": 3%` 同时命中
`"id": 30` / `"id": 31` / `"id": 300`。该过滤器同时用于列表、分组计数、
stats 与 fetch_case_ids（回收站全部恢复 / 按筛选批量与导出圈定），
命中超集会让批量与导出作用到非筛选范围内的用例。

本文件锁定：
- 整值匹配：维度 3 / 30 / 31 / 300 互不串；int 与字符串 id 形态同验
- 轮次内维度（rounds[].evaluation.dimensions）同样由右界收敛
- 紧凑序列化（无空格）形态：`{"id":3}` 同样整值匹配
- 同口径一致性：列表 / 分组计数 / stats / fetch_case_ids 四路结果一致

DB：进程级 SQLite（tests/conftest.py 注入），对齐 test_int539 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)

_TABLE_CACHE = None


def _ensure_tables():
    init_db(pool_size=2)
    global _TABLE_CACHE
    if _TABLE_CACHE is None:
        from task_service.infrastructure.persistence.models import (
            Tag, TagCategory, TestCaseGroup, TestCase, TestCaseTag, Favorite,
        )
        _TABLE_CACHE = [t.__table__ for t in (
            TagCategory, Tag, TestCaseGroup, TestCase, TestCaseTag, Favorite,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLE_CACHE)
    return _TABLE_CACHE


def _cleanup(tables):
    session = get_db_session()
    try:
        for table in tables:
            session.execute(table.delete())
        session.commit()
    finally:
        remove_db_session()


def _seed_cases(rows):
    """rows: [(id, name, config_dict, group_id or None), ...]"""
    from task_service.infrastructure.persistence.models import TestCase

    session = get_db_session()
    try:
        session.add_all([
            TestCase(id=cid, name=name, config=config, group_id=group_id)
            for cid, name, config, group_id in rows
        ])
        session.commit()
    finally:
        remove_db_session()


def _seed_groups(rows):
    """rows: [(id, name), ...]"""
    from task_service.infrastructure.persistence.models import TestCaseGroup

    session = get_db_session()
    try:
        session.add_all([
            TestCaseGroup(id=gid, name=name, visibility='shared')
            for gid, name in rows
        ])
        session.commit()
    finally:
        remove_db_session()


def _insert_raw_config(case_id, name, config_text):
    """绕过 ORM JSON 序列化，直接落紧凑（无空格）JSON 文本。

    SQLite 的 JSON 列即 TEXT 亲和，读回仍可 json.loads；
    PG 的 json 列同样保留原文本，用于覆盖非 json.dumps 默认分隔符的存量数据。
    """
    from sqlalchemy import text

    session = get_db_session()
    try:
        session.execute(
            text(
                "INSERT INTO test_cases (id, name, config, deleted, visibility) "
                "VALUES (:id, :name, :config, 0, 'shared')"
            ),
            {'id': case_id, 'name': name, 'config': config_text},
        )
        session.commit()
    finally:
        remove_db_session()


def _query_ids(dimension_id):
    from task_service.infrastructure.persistence.testcase_repository import testcase_repository
    page = testcase_repository.query_testcases(per_page=100, dimension_id=dimension_id)
    return {tc.id for tc in page.items}


@pytest.fixture(autouse=True)
def _env():
    tables = _ensure_tables()
    _cleanup(tables)
    yield tables
    _cleanup(tables)


# ---------------- 整值匹配 ----------------

class TestDimFilterBoundary:

    def test_prefix_ids_not_hit(self):
        _seed_cases([
            ('D3', '维度3', {'dimensions': [{'id': 3, 'name': 'dim3'}]}, None),
            ('D30', '维度30', {'dimensions': [{'id': 30, 'name': 'dim30'}]}, None),
            ('D31', '维度31', {'dimensions': [{'id': 31, 'name': 'dim31'}]}, None),
            ('D300', '维度300', {'dimensions': [{'id': 300, 'name': 'dim300'}]}, None),
            ('NONE', '无维度', {}, None),
        ])
        assert _query_ids(3) == {'D3'}
        assert _query_ids(30) == {'D30'}
        assert _query_ids(300) == {'D300'}

    def test_string_id_forms(self):
        _seed_cases([
            ('S3', '字符串3', {'dimensions': [{'id': '3', 'name': 'dim3'}]}, None),
            ('S30', '字符串30', {'dimensions': [{'id': '30', 'name': 'dim30'}]}, None),
            ('S300', '字符串300', {'dimensions': [{'id': '300'}]}, None),
        ])
        assert _query_ids(3) == {'S3'}
        assert _query_ids(30) == {'S30'}

    def test_round_nested_dimensions(self):
        """轮次内维度（rounds[].evaluation.dimensions）同口径收敛。"""
        _seed_cases([
            ('R3', '轮次3', {'rounds': [
                {'round_number': 1, 'evaluation': {'dimensions': [{'id': 3}]}}]}, None),
            ('R30', '轮次30', {'rounds': [
                {'round_number': 1, 'evaluation': {'dimensions': [{'id': 30}]}}]}, None),
        ])
        assert _query_ids(3) == {'R3'}
        assert _query_ids(30) == {'R30'}

    def test_compact_serialization(self):
        """无空格序列化形态（{"id":3}）同样整值匹配。"""
        _insert_raw_config('C3', '紧凑3', '{"dimensions":[{"id":3}]}')
        _insert_raw_config('C30', '紧凑30', '{"dimensions":[{"id":30}]}')
        _insert_raw_config('C300', '紧凑300', '{"dimensions":[{"id":300}]}')
        _insert_raw_config('CS3', '紧凑字符串3', '{"dimensions":[{"id":"3"}]}')
        assert _query_ids(3) == {'C3', 'CS3'}
        assert _query_ids(30) == {'C30'}

    def test_no_filter_unchanged(self):
        """回归：不传 dimension_id 时不过滤。"""
        _seed_cases([
            ('A', '维度3', {'dimensions': [{'id': 3}]}, None),
            ('B', '维度30', {'dimensions': [{'id': 30}]}, None),
            ('C', '无维度', {}, None),
        ])
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository
        ids = {tc.id for tc in testcase_repository.query_testcases(per_page=100).items}
        assert {'A', 'B', 'C'} <= ids


# ---------------- 同口径一致性 ----------------

class TestDimFilterConsistency:
    """列表 / 分组计数 / stats / fetch_case_ids 四路同一口径。"""

    def test_all_read_paths_agree(self):
        _seed_groups([('G1', '含维度3'), ('G2', '仅维度30')])
        _seed_cases([
            ('D3', '维度3', {'dimensions': [{'id': 3}]}, 'G1'),
            ('D30', '维度30', {'dimensions': [{'id': 30}]}, 'G1'),
            ('D300', '维度300', {'dimensions': [{'id': 300}]}, 'G2'),
        ])
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository

        list_ids = _query_ids(3)
        assert list_ids == {'D3'}

        fetch_ids = set(testcase_repository.fetch_case_ids(dimension_id=3))
        assert fetch_ids == list_ids

        stats = testcase_repository.get_testcase_stats(dimension_id=3)
        assert stats['total'] == len(list_ids)

        groups = testcase_repository.list_groups(dimension_id=3)
        by_id = {g['id']: g for g in groups}
        assert set(by_id) == {'G1'}
        assert by_id['G1']['test_case_count'] == 1
