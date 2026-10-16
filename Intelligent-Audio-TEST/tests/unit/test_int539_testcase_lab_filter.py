# -*- coding: utf-8 -*-
"""INT-539 专项：用例 lab 归属透出 + 按实验室过滤（含通用用例）。

覆盖：
- lab_id 解析（config JSONB 顶层键）：int / 字符串数字 / float / bool /
  缺失 / 显式 null → None（通用用例）
- 过滤正反例：通用用例（无 lab_id）任意实验室可见；专属用例命中已选实验室；
  越域排除（lab_id=5 在过滤 lab=3 时不可见）
- 顶层语义：嵌套在 rounds 音频项里的 lab_id 不误命中（->> 只取顶层键）
- 全链：servicer/handler → 门面 → 查询服务 → 仓储透传 lab_ids，
  列表项透出 lab_id/lab_name（laboratories 表 join，软删实验室 lab_name=None）
- 回归：不传 lab_ids 的既有列表行为不变（新字段/参数均可选）

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表，
laboratories 表用原生 SQL 建（task_service 不定义该 PO，避免跨服务同表冲突）。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)

# ---------------- 工具 ----------------

_TABLE_CACHE = None
_LAB_CREATED = False


def _ensure_db():
    init_db(pool_size=2)


def _ensure_case_tables():
    """创建用例列表链涉及的表（TestCase/Group/Tag/Favorite + laboratories）。"""
    _ensure_db()
    global _TABLE_CACHE, _LAB_CREATED
    if _TABLE_CACHE is None:
        from task_service.infrastructure.persistence.models import (
            Tag, TagCategory, TestCaseGroup, TestCase, TestCaseTag, Favorite,
        )
        _TABLE_CACHE = [t.__table__ for t in (
            TagCategory, Tag, TestCaseGroup, TestCase, TestCaseTag, Favorite,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLE_CACHE)
    _ensure_lab_table()
    return _TABLE_CACHE


def _ensure_lab_table():
    """laboratories 表（共享库实验室域，task_service 仅读，原生 SQL 建表）。"""
    global _LAB_CREATED
    if _LAB_CREATED:
        return
    from sqlalchemy import text

    session = get_db_session()
    try:
        session.execute(text(
            """
            CREATE TABLE IF NOT EXISTS laboratories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                building VARCHAR(50),
                floor VARCHAR(20),
                room_number VARCHAR(50),
                description TEXT,
                status VARCHAR(20) DEFAULT 'active',
                deleted BOOLEAN DEFAULT FALSE,
                deleted_at TIMESTAMP,
                created_by_user_id BIGINT,
                updated_by_user_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ))
        session.commit()
        _LAB_CREATED = True
    finally:
        remove_db_session()


def _cleanup(tables):
    from sqlalchemy import text

    session = get_db_session()
    try:
        for table in tables:
            session.execute(table.delete())
        session.execute(text('DELETE FROM laboratories'))
        session.commit()
    finally:
        remove_db_session()


def _seed_cases(rows):
    """插入用例行。rows: [(id, name, config_dict), ...]"""
    from task_service.infrastructure.persistence.models import TestCase

    session = get_db_session()
    try:
        session.add_all([
            TestCase(id=cid, name=name, config=config)
            for cid, name, config in rows
        ])
        session.commit()
    finally:
        remove_db_session()


def _seed_labs(rows):
    """插入实验室行。rows: [(id, code, name, deleted), ...]"""
    from sqlalchemy import text

    session = get_db_session()
    try:
        for lid, code, name, deleted in rows:
            session.execute(
                text(
                    "INSERT INTO laboratories (id, code, name, deleted) "
                    "VALUES (:id, :code, :name, :deleted)"
                ),
                {'id': lid, 'code': code, 'name': name, 'deleted': bool(deleted)},
            )
        session.commit()
    finally:
        remove_db_session()


# ---------------- lab_id 解析 ----------------

class TestParseConfigLabId:
    """config JSONB 顶层 lab_id 解析（空/缺失 = 通用用例 → None）。"""

    def test_missing_key_is_generic(self):
        from shared.utils.testcase_helpers import parse_config_lab_id
        assert parse_config_lab_id({}) is None
        assert parse_config_lab_id({'rounds': [], 'name': 'x'}) is None
        assert parse_config_lab_id(None) is None

    def test_explicit_null_is_generic(self):
        from shared.utils.testcase_helpers import parse_config_lab_id
        assert parse_config_lab_id({'lab_id': None}) is None

    def test_numeric_forms(self):
        from shared.utils.testcase_helpers import parse_config_lab_id
        assert parse_config_lab_id({'lab_id': 3}) == 3
        assert parse_config_lab_id({'lab_id': '3'}) == 3
        assert parse_config_lab_id({'lab_id': 3.0}) == 3
        assert parse_config_lab_id({'lab_id': True}) == 1

    def test_non_numeric_is_none(self):
        from shared.utils.testcase_helpers import parse_config_lab_id
        assert parse_config_lab_id({'lab_id': 'abc'}) is None
        assert parse_config_lab_id({'lab_id': 3.5}) is None
        assert parse_config_lab_id({'lab_id': ''}) is None


# ---------------- 过滤正反例 ----------------

class TestLabFilterRepository:
    """仓储层过滤：通用用例包含 / 专属命中 / 越域排除 / 顶层语义。"""

    def setup_method(self):
        _ensure_case_tables()
        from task_service.infrastructure.persistence.models import TestCase
        _cleanup([TestCase.__table__])

    def _ids_for(self, lab_ids):
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository
        page = testcase_repository.query_testcases(lab_ids=lab_ids)
        return {tc.id for tc in page.items}

    def test_generic_visible_any_lab_and_exclusive_hit(self):
        _seed_cases([
            ('G1', '通用用例', {}),
            ('G2', '通用显式空', {'lab_id': None}),
            ('L3', '专属3号实验室', {'lab_id': 3}),
            ('L5', '专属5号实验室', {'lab_id': 5}),
        ])
        ids = self._ids_for([3])
        assert 'G1' in ids          # 通用用例：任意实验室可见
        assert 'G2' in ids          # 显式 null 同通用
        assert 'L3' in ids          # 专属命中
        assert 'L5' not in ids      # 越域排除

    def test_multiple_lab_ids(self):
        _seed_cases([
            ('G1', '通用', {}),
            ('L3', '专属3', {'lab_id': 3}),
            ('L5', '专属5', {'lab_id': 5}),
            ('L7', '专属7', {'lab_id': 7}),
        ])
        ids = self._ids_for([3, 5])
        assert {'G1', 'L3', 'L5'} <= ids
        assert 'L7' not in ids

    def test_nested_lab_id_does_not_count(self):
        """->> 只取顶层键：嵌套在 rounds 音频项的 lab_id 不误命中为专属。"""
        _seed_cases([
            ('NESTED', '嵌套lab_id', {
                'rounds': [{'audios': [{'audio_id': 1, 'lab_id': 3}]}],
            }),
        ])
        # 过滤 lab=3 时嵌套用例无顶层 lab_id → 通用 → 可见
        assert 'NESTED' in self._ids_for([3])
        # 未过滤（None/空）时也可见（回归）
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository
        page = testcase_repository.query_testcases()
        assert 'NESTED' in {tc.id for tc in page.items}

    def test_no_lab_ids_returns_all(self):
        """回归：不传 lab_ids（None）或空列表 = 不过滤。"""
        _seed_cases([
            ('A', '普通', {'lab_id': 3}),
            ('B', '通用', {}),
        ])
        from task_service.infrastructure.persistence.testcase_repository import testcase_repository
        page = testcase_repository.query_testcases(lab_ids=None)
        assert {'A', 'B'} <= {tc.id for tc in page.items}
        page2 = testcase_repository.query_testcases(lab_ids=[])
        assert {'A', 'B'} <= {tc.id for tc in page2.items}


# ---------------- 全链 + lab_name join ----------------

class TestLabFilterFullChain:
    """servicer/handler → 门面 → 查询服务 → 仓储全链透传 lab_ids，
    列表项透出 lab_id/lab_name（laboratories join，软删实验室 lab_name=None）。"""

    def setup_method(self):
        _ensure_case_tables()
        from task_service.infrastructure.persistence.models import TestCase
        _cleanup([TestCase.__table__])

    def test_chain_list_with_lab_filter_and_name(self):
        from task_service.application.queries.task_queries import ListTestCasesQuery
        from task_service.application.handlers import task_query_handler

        _seed_labs([
            (3, 'LAB03', '三号实验室', False),
            (5, 'LAB05', '五号实验室（软删）', True),
        ])
        _seed_cases([
            ('CHAIN1', '通用', {}),
            ('CHAIN2', '专属3', {'lab_id': 3}),
            ('CHAIN3', '专属5（软删实验室）', {'lab_id': 5}),
            ('CHAIN4', '专属9', {'lab_id': 9}),
        ])

        result = task_query_handler.handle_list_testcases(ListTestCasesQuery(
            page=1, per_page=10, lab_ids=[3]))
        assert result.get('success') is True
        items = result.get('data', {}).get('items') or []
        by_id = {tc['id']: tc for tc in items}

        # 过滤口径
        assert 'CHAIN1' in by_id      # 通用可见
        assert 'CHAIN2' in by_id      # 专属命中
        assert 'CHAIN3' not in by_id  # 越域排除
        assert 'CHAIN4' not in by_id  # 越域排除

        # lab 归属透出：通用 lab_id=null；专属带 lab_id + lab_name
        assert by_id['CHAIN1']['lab_id'] is None
        assert by_id['CHAIN1']['lab_name'] is None
        assert by_id['CHAIN2']['lab_id'] == 3
        assert by_id['CHAIN2']['lab_name'] == '三号实验室'

    def test_soft_deleted_lab_name_none(self):
        """软删实验室不映射 lab_name（lab_id 仍透出），同「空 lab 返回 null」。"""
        from task_service.application.queries.task_queries import ListTestCasesQuery
        from task_service.application.handlers import task_query_handler

        _seed_labs([
            (7, 'LAB07', '七号实验室', True),   # 软删
        ])
        _seed_cases([
            ('SD1', '专属软删实验室', {'lab_id': 7}),
        ])

        result = task_query_handler.handle_list_testcases(ListTestCasesQuery(
            page=1, per_page=10, lab_ids=[7]))
        assert result.get('success') is True
        items = result.get('data', {}).get('items') or []
        tc = items[0]
        assert tc['id'] == 'SD1'
        assert tc['lab_id'] == 7
        assert tc['lab_name'] is None

    def test_no_lab_filter_chain_regression(self):
        """回归：既有列表（不传 lab_ids）仍走通且透出 lab 字段（均可选）。"""
        from task_service.application.queries.task_queries import ListTestCasesQuery
        from task_service.application.handlers import task_query_handler

        _seed_labs([(3, 'LAB03', '三号实验室', False)])
        _seed_cases([
            ('R1', '通用', {}),
            ('R2', '专属', {'lab_id': 3}),
        ])

        result = task_query_handler.handle_list_testcases(ListTestCasesQuery(
            page=1, per_page=10))
        assert result.get('success') is True
        items = result.get('data', {}).get('items') or []
        by_id = {tc['id']: tc for tc in items}
        assert {'R1', 'R2'} <= set(by_id)
        assert by_id['R1']['lab_id'] is None
        assert by_id['R2']['lab_id'] == 3
        assert by_id['R2']['lab_name'] == '三号实验室'

    def test_tag_view_lab_filter(self):
        """标签聚合视图同口径过滤 + lab 字段透出（camelCase）。"""
        from task_service.application.queries.task_queries import ListTestCasesQuery
        from task_service.application.handlers import task_query_handler

        _seed_labs([(3, 'LAB03', '三号实验室', False)])
        from task_service.infrastructure.persistence.models import (
            Tag, TagCategory, TestCaseTag, TestCase,
        )
        session = get_db_session()
        try:
            cat = TagCategory(name='场景')
            tag = Tag(name='噪音', category=cat)
            tc1 = TestCase(id='TV1', name='通用-噪音', config={})
            tc2 = TestCase(id='TV2', name='专属3-噪音', config={'lab_id': 3})
            tc3 = TestCase(id='TV3', name='专属5-噪音', config={'lab_id': 5})
            session.add_all([cat, tag, tc1, tc2, tc3])
            session.commit()
            session.execute(
                TestCaseTag.__table__.insert(),
                [{'test_case_id': 'TV1', 'tag_id': tag.id},
                 {'test_case_id': 'TV2', 'tag_id': tag.id},
                 {'test_case_id': 'TV3', 'tag_id': tag.id}],
            )
            session.commit()
        finally:
            remove_db_session()

        result = task_query_handler.handle_list_testcases(ListTestCasesQuery(
            page=1, per_page=10, view='tag', lab_ids=[3]))
        assert result.get('success') is True
        items = result.get('data', {}).get('items') or []
        cases = items[0]['testCases'] if items else []
        by_id = {c['id']: c for c in cases}
        assert 'TV1' in by_id       # 通用可见
        assert 'TV2' in by_id       # 专属命中
        assert 'TV3' not in by_id   # 越域排除
        assert by_id['TV1']['labId'] is None
        assert by_id['TV2']['labId'] == 3
        assert by_id['TV2']['labName'] == '三号实验室'
