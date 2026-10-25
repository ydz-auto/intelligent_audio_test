# -*- coding: utf-8 -*-
"""INT-1469 专项：执行口径派生列 derived_test_type 写时物化 + 查询侧 SQL 过滤。

背景：用例不存储类型（INT-79/差异#2 收尾删 test_type），执行口径由 config
形态（+上传双变体 _api/_e2e 名后缀，INT-129）派生。列表/统计/取 ID 原先
「物化全量候选行（id/name/config）后 Python 过滤」，万级用例下每请求
~500ms。改为写时物化 derive_case_test_type(config, name) 到
test_cases.derived_test_type，查询侧 SQL 等值过滤（走索引）。

覆盖：
- 写时物化：ORM 新建（含非仓储直建）、改 config、改名、批量改配置四条写入
  路径刷新列值；口径与 derive_case_test_type 一致
- 查询侧：query_testcases / query_testcases_by_tag_ids / get_testcase_stats /
  fetch_case_ids 的 type 过滤与 Python 派生逐行一致（含双变体名后缀）
- 未命中 test_type 原样返回全量（非法值不过滤）

DB：进程级 SQLite（tests/conftest.py 注入），对齐 test_int193 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from datetime import datetime, timedelta, timezone

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)
from shared.utils.testcase_helpers import derive_case_test_type

_TABLES = None

# e2e 形态：任一音频携带 playback_device_id；双变体（INT-129）形态同为 e2e，
# 仅名后缀定口径，恰好区分"配置形态派生"与"名后缀优先"两条分支
_E2E_CONFIG = {'rounds': [{'roundNumber': 1,
                           'audios': [{'audio_id': 1, 'playback_device_id': 3}]}]}
_API_CONFIG = {'rounds': [{'roundNumber': 1,
                           'audios': [{'audio_id': 1}]}]}
_VARIANT_CONFIG = dict(_E2E_CONFIG, auto_generated=True)


def _ensure_tables():
    init_db(pool_size=2)
    global _TABLES
    if _TABLES is None:
        from task_service.infrastructure.persistence.models import (
            TestCase, Tag, TagCategory, TestCaseGroup, TestCaseTag, Favorite,
        )
        _TABLES = [t.__table__ for t in (
            TagCategory, Tag, TestCaseGroup, TestCase, TestCaseTag, Favorite,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLES)
    return _TABLES


def _cleanup_tables():
    session = get_db_session()
    try:
        for table in _TABLES:
            session.execute(table.delete())
        session.commit()
    finally:
        remove_db_session()


@pytest.fixture(autouse=True)
def _int1469_db():
    _ensure_tables()
    _cleanup_tables()
    yield
    _cleanup_tables()


def _add_cases(*cases):
    """直建 TestCase（不经仓储），验证 before_insert 事件覆盖所有写入路径。"""
    from task_service.infrastructure.persistence.models import TestCase
    session = get_db_session()
    try:
        base = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=8)))
        for i, (tc_id, name, config) in enumerate(cases):
            session.add(TestCase(id=tc_id, name=name, config=config,
                                 created_at=base + timedelta(minutes=i)))
        session.commit()
    finally:
        remove_db_session()


def _repo():
    from task_service.infrastructure.persistence.testcase_repository import (
        testcase_repository,
    )
    return testcase_repository


def _read_rows():
    from task_service.infrastructure.persistence.models import TestCase
    session = get_db_session()
    try:
        return {r.id: (r.name, r.config, r.derived_test_type)
                for r in session.query(TestCase).all()}
    finally:
        remove_db_session()


class TestWriteTimeMaterialization:
    """写入路径刷新派生列，口径 = derive_case_test_type(config, name)。"""

    def test_insert_materializes_all_shapes(self):
        _add_cases(
            ('I1469_E', '纯e2e形态', _E2E_CONFIG),
            ('I1469_A', '纯api形态', _API_CONFIG),
            ('I1469_VA', '样例_api', _VARIANT_CONFIG),
            ('I1469_VE', '样例_e2e', _VARIANT_CONFIG),
            ('I1469_VT', '样例_api_023604', _VARIANT_CONFIG),
        )
        rows = _read_rows()
        for tc_id, (name, config, got) in rows.items():
            assert got == derive_case_test_type(config, name), tc_id
        assert rows['I1469_E'][2] == 'e2e'
        assert rows['I1469_A'][2] == 'api'
        assert rows['I1469_VA'][2] == 'api'   # 名后缀优先
        assert rows['I1469_VE'][2] == 'e2e'
        assert rows['I1469_VT'][2] == 'api'   # 重名冲突时间戳后缀

    def test_repository_create_materializes(self):
        repo = _repo()
        repo.create_testcase({'id': 'I1469_RC', 'name': '仓储建例',
                              'config': dict(_API_CONFIG)})
        get_db_session().commit()
        assert _read_rows()['I1469_RC'][2] == 'api'
        remove_db_session()

    def test_config_update_flips_column(self):
        _add_cases(('I1469_U', '改配置用例', _E2E_CONFIG))
        from task_service.infrastructure.persistence.models import TestCase
        session = get_db_session()
        try:
            tc = session.query(TestCase).filter_by(id='I1469_U').one()
            tc.config = dict(_API_CONFIG)
        finally:
            session.commit()
            remove_db_session()
        assert _read_rows()['I1469_U'][2] == 'api'

    def test_rename_flips_column(self):
        """auto_generated 用例改名带 _api 后缀 → 口径翻为 api（事件按当前名刷新）。"""
        _add_cases(('I1469_N', '上传用例_e2e', _VARIANT_CONFIG))
        from task_service.infrastructure.persistence.models import TestCase
        session = get_db_session()
        try:
            tc = session.query(TestCase).filter_by(id='I1469_N').one()
            tc.name = '上传用例_api'
        finally:
            session.commit()
            remove_db_session()
        assert _read_rows()['I1469_N'][2] == 'api'

    def test_batch_config_update_flips_column(self):
        """批量改配置路径（_update_config_flagged）同样刷新。"""
        from task_service.application.testcase.testcase_batch_config_update_mixin import (
            TestCaseConfigUpdateMixin,
        )
        _add_cases(('I1469_B', '批量改用例', _E2E_CONFIG))
        from task_service.infrastructure.persistence.models import TestCase
        session = get_db_session()
        try:
            tc = session.query(TestCase).filter_by(id='I1469_B').one()
            TestCaseConfigUpdateMixin._update_config_flagged(
                tc, dict(_API_CONFIG))
        finally:
            session.commit()
            remove_db_session()
        assert _read_rows()['I1469_B'][2] == 'api'


class TestSqlSideFilter:
    """查询侧 SQL 过滤与 Python 派生逐行一致。"""

    _CASES = (
        ('S1469_1', 'e2e一', _E2E_CONFIG),
        ('S1469_2', 'e2e二', _E2E_CONFIG),
        ('S1469_3', 'api一', _API_CONFIG),
        ('S1469_4', 'api二', _API_CONFIG),
        ('S1469_5', '样例_api', _VARIANT_CONFIG),
        ('S1469_6', '样例_e2e', _VARIANT_CONFIG),
    )

    def _expected(self, test_type):
        return {cid for cid, name, cfg in self._CASES
                if derive_case_test_type(cfg, name) == test_type}

    def test_list_filter_matches_python_derivation(self):
        _add_cases(*self._CASES)
        repo = _repo()
        for tt in ('api', 'e2e'):
            page = repo.query_testcases(test_type=tt, per_page=50)
            assert {tc.id for tc in page.items} == self._expected(tt)
            assert page.total == len(self._expected(tt))

    def test_list_filter_pagination_after_filter(self):
        """过滤必须发生在分页之前：total/pages 按过滤后集合计。"""
        _add_cases(*self._CASES)
        page = _repo().query_testcases(test_type='api', page=1, per_page=2)
        assert page.total == len(self._expected('api'))
        assert page.pages == (page.total + 1) // 2
        assert all(tc.id not in self._expected('e2e') for tc in page.items)

    def test_invalid_test_type_does_not_filter(self):
        _add_cases(*self._CASES)
        assert _repo().query_testcases(test_type='nonsense').total == len(self._CASES)
        assert _repo().query_testcases(test_type=None).total == len(self._CASES)

    def test_stats_filter_matches_python_derivation(self):
        _add_cases(*self._CASES)
        repo = _repo()
        for tt in ('api', 'e2e'):
            assert repo.get_testcase_stats(test_type=tt)['total'] == len(self._expected(tt))
        grouped = repo.get_testcase_stats(test_type='e2e', group_by='algorithm_type')
        assert sum(i['count'] for i in grouped['items']) == len(self._expected('e2e'))

    def test_fetch_case_ids_filter_matches_python_derivation(self):
        """取 ID 与列表同口径（名后缀生效）——E2E 起跑圈定与列表可见集一致。"""
        _add_cases(*self._CASES)
        for tt in ('api', 'e2e'):
            assert set(_repo().fetch_case_ids(test_type=tt)) == self._expected(tt)

    def test_tag_view_filter_matches_python_derivation(self):
        from task_service.infrastructure.persistence.models import (
            Tag, TestCaseTag, TestCase,
        )
        _add_cases(*self._CASES)
        session = get_db_session()
        try:
            session.add(Tag(id=1469, name='INT1469标签'))
            session.flush()
            for tc_id, _name, _cfg in self._CASES:
                session.add(TestCaseTag(test_case_id=tc_id, tag_id=1469))
            session.commit()
        finally:
            remove_db_session()
        for tt in ('api', 'e2e'):
            items = _repo().query_testcases_by_tag_ids(['1469'], test_type=tt)
            assert {tc.id for tc in items} == self._expected(tt)
        _ = (Tag, TestCaseTag, TestCase)
