# -*- coding: utf-8 -*-
"""INT-193 专项：testcases 列表 type/test_type/dimension_id 过滤贯通。

缺陷：TestCaseListQuery（网关）不含 type/test_type/dimension_id 字段，
base extra="ignore" 静默丢弃——GET /testcases?type=e2e 返回 200 但 total
与无过滤一致；前端只能对首屏 50 条内存过滤，第 2 页起 E2E 用例永不显示。

覆盖：
- 仓储层 query_testcases(test_type=...) 派生口径过滤（e2e/api/双变体名后缀）
- 派生口径下的内存分页（total/pages/page 切片与 SQL 过滤口径一致）
- gRPC servicer（proto type/dimension_id → Query）→ handler → 查询服务全链
- 标签视图 query_testcases_by_tag_ids(test_type=...) 同口径过滤

DB：进程级 SQLite（tests/conftest.py 注入），对齐 test_int141 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from datetime import datetime, timedelta, timezone

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)


_TABLES = None

# e2e 形态：任一音频携带 playback_device_id（INT-129：api 变体形态相同，
# 仅名后缀可区分，故"形态即 e2e"与"名后缀优先"两个口径都要测）
_E2E_CONFIG = {'rounds': [{'roundNumber': 1,
                           'audios': [{'audio_id': 1, 'playback_device_id': 3}]}]}
_API_CONFIG = {'rounds': [{'roundNumber': 1,
                           'audios': [{'audio_id': 1}]}]}


def _ensure_db():
    init_db(pool_size=2)


def _ensure_tables():
    _ensure_db()
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
def _int193_db():
    _ensure_tables()
    # 前后都清：进程级共享 SQLite，前序套件可能残留 TestCase 行
    _cleanup_tables()
    yield
    _cleanup_tables()


def _add_cases(*cases):
    from task_service.infrastructure.persistence.models import TestCase
    session = get_db_session()
    try:
        # 显式单调 created_at（东八区对齐 utc8now 形态）：默认 utc8now() 同 flush
        # 批量插入在 Windows 毫秒时钟粒度下会全同，created_at DESC 平局序由
        # SQLite 插入序兜底、跨时钟 tick 即漂移，页切片精确顺序断言会假红
        base = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=8)))
        for i, (tc_id, name, config) in enumerate(cases):
            session.add(TestCase(id=tc_id, name=name, config=config,
                                 created_at=base + timedelta(minutes=i)))
        session.commit()
    finally:
        remove_db_session()


class TestRepoTypeFilter:
    """仓储层 query_testcases 派生口径过滤。"""

    def test_type_filter_e2e_and_api(self):
        from task_service.infrastructure.persistence.testcase_repository import (
            testcase_repository,
        )

        _add_cases(
            ('INT193_E1', '纯e2e形态', _E2E_CONFIG),
            ('INT193_A1', '纯api形态', _API_CONFIG),
            # INT-129 双变体：上传生成，config 形态均为 e2e，名后缀定口径
            ('INT193_V1', '样例_api', dict(_E2E_CONFIG, auto_generated=True)),
            ('INT193_V2', '样例_e2e', dict(_E2E_CONFIG, auto_generated=True)),
        )

        e2e_page = testcase_repository.query_testcases(test_type='e2e')
        assert {tc.id for tc in e2e_page.items} == {'INT193_E1', 'INT193_V2'}
        assert e2e_page.total == 2

        api_page = testcase_repository.query_testcases(test_type='api')
        assert {tc.id for tc in api_page.items} == {'INT193_A1', 'INT193_V1'}
        assert api_page.total == 2

        # 非法/空值不过滤，回原全量行为
        all_page = testcase_repository.query_testcases()
        assert all_page.total == 4
        nofilter = testcase_repository.query_testcases(test_type=' nonsense ')
        assert nofilter.total == 4

    def test_type_filter_pagination_slices_matched_subset(self):
        """分页必须发生在派生过滤之后：total/pages 按过滤后集合计。"""
        from task_service.infrastructure.persistence.testcase_repository import (
            testcase_repository,
        )

        _add_cases(
            ('INT193_P1', 'e2e一', _E2E_CONFIG),
            ('INT193_P2', 'e2e二', _E2E_CONFIG),
            ('INT193_P3', 'e2e三', _E2E_CONFIG),
            ('INT193_P4', 'api一', _API_CONFIG),
            ('INT193_P5', 'api二', _API_CONFIG),
        )

        page1 = testcase_repository.query_testcases(test_type='e2e', page=1, per_page=2)
        assert page1.total == 3
        assert page1.pages == 2
        # created_at 单调递增（P1→P3），列表 created_at DESC = 新者在前
        assert [tc.id for tc in page1.items] == ['INT193_P3', 'INT193_P2']

        page2 = testcase_repository.query_testcases(test_type='e2e', page=2, per_page=2)
        assert [tc.id for tc in page2.items] == ['INT193_P1']
        # api 用例任何页都不出现
        for page in (page1, page2):
            assert all(tc.id.startswith('INT193_P') and tc.id not in ('INT193_P4', 'INT193_P5')
                       for tc in page.items)

    def test_type_filter_with_other_filters_combined(self):
        from task_service.infrastructure.persistence.testcase_repository import (
            testcase_repository,
        )

        _add_cases(
            ('INT193_C1', '组合e2e命中', _E2E_CONFIG),
            ('INT193_C2', '组合e2e另词', _E2E_CONFIG),
            ('INT193_C3', '组合api', _API_CONFIG),
        )
        page = testcase_repository.query_testcases(
            test_type='e2e', keyword='命中')
        assert {tc.id for tc in page.items} == {'INT193_C1'}


class TestTagViewTypeFilter:
    """标签视图 query_testcases_by_tag_ids 派生口径过滤。"""

    def test_tag_cases_filtered_by_type(self):
        from task_service.infrastructure.persistence.testcase_repository import (
            testcase_repository,
        )
        from task_service.infrastructure.persistence.models import TestCase, Tag, TestCaseTag

        _add_cases(
            ('INT193_T1', '标签e2e', _E2E_CONFIG),
            ('INT193_T2', '标签api', _API_CONFIG),
        )
        # 关联表主键为 BigInteger，SQLite 不自增，显式赋 id
        session = get_db_session()
        try:
            session.add(Tag(name='INT193标签'))
            session.commit()
            tag = session.query(Tag).filter_by(name='INT193标签').one()
            session.add_all([
                TestCaseTag(id=1, test_case_id='INT193_T1', tag_id=tag.id),
                TestCaseTag(id=2, test_case_id='INT193_T2', tag_id=tag.id),
            ])
            session.commit()
            tag_id = tag.id
        finally:
            remove_db_session()

        e2e = testcase_repository.query_testcases_by_tag_ids(
            [tag_id], test_type='e2e')
        assert [tc.id for tc in e2e] == ['INT193_T1']

        api = testcase_repository.query_testcases_by_tag_ids(
            [tag_id], test_type='api')
        assert [tc.id for tc in api] == ['INT193_T2']

        all_cases = testcase_repository.query_testcases_by_tag_ids([tag_id])
        assert {tc.id for tc in all_cases} == {'INT193_T1', 'INT193_T2'}


class TestGrpcChain:
    """gRPC servicer → handler → 查询服务全链（签名回归）。"""

    def test_handler_chain_accepts_test_type_and_dimension(self):
        """回归：handler 链透传 test_type/dimension_id（此前 handler 漏传
        dimension_id、全链丢弃 test_type——INT-141 同款签名回归点）。"""
        from task_service.application.queries.task_queries import ListTestCasesQuery
        from task_service.application.handlers import task_query_handler

        _add_cases(
            ('INT193_G1', '链e2e', dict(_E2E_CONFIG, dimensions=[{'id': 4}])),
            ('INT193_G2', '链e2e无维度', _E2E_CONFIG),
            ('INT193_G3', '链api', _API_CONFIG),
        )

        result = task_query_handler.handle_list_testcases(ListTestCasesQuery(
            page=1, per_page=10, test_type='e2e'))
        assert result.get('success') is True
        items = result.get('data', {}).get('items') or []
        assert {tc['id'] for tc in items} == {'INT193_G1', 'INT193_G2'}
        # 展示口径与过滤口径一致（派生 type 字段）
        assert all(tc['type'] == 'e2e' for tc in items)

        result_api = task_query_handler.handle_list_testcases(ListTestCasesQuery(
            page=1, per_page=10, test_type='api'))
        items_api = result_api.get('data', {}).get('items') or []
        assert {tc['id'] for tc in items_api} == {'INT193_G3'}
        assert all(tc['type'] == 'api' for tc in items_api)

        result_dim = task_query_handler.handle_list_testcases(ListTestCasesQuery(
            page=1, per_page=10, dimension_id=4))
        items_dim = result_dim.get('data', {}).get('items') or []
        assert {tc['id'] for tc in items_dim} == {'INT193_G1'}

        # 组合：type + dimension
        result_both = task_query_handler.handle_list_testcases(ListTestCasesQuery(
            page=1, per_page=10, test_type='e2e', dimension_id=4))
        items_both = result_both.get('data', {}).get('items') or []
        assert [tc['id'] for tc in items_both] == ['INT193_G1']

    def test_servicer_maps_proto_type_and_dimension_id(self):
        """servicer 从 proto 读 request.type / request.dimension_id
        （此前 proto 字段存在但 servicer 未读取）。"""
        from shared.proto import task_service_pb2 as task_pb
        from task_service.interfaces.grpc.testcase_config import (
            TestCaseConfigServiceServicer,
        )

        _add_cases(
            ('INT193_S1', 'servE2e', _E2E_CONFIG),
            ('INT193_S2', 'servApi', _API_CONFIG),
        )

        servicer = TestCaseConfigServiceServicer()
        resp = servicer.ListTestCases(task_pb.ListTestCasesRequest(
            page=1, per_page=10, type='e2e'))
        assert resp.success is True, resp.message
        data = __import__('json').loads(resp.data)
        assert {tc['id'] for tc in data['items']} == {'INT193_S1'}
        assert data['total'] == 1

        resp_api = servicer.ListTestCases(task_pb.ListTestCasesRequest(
            page=1, per_page=10, type='api'))
        data_api = __import__('json').loads(resp_api.data)
        assert {tc['id'] for tc in data_api['items']} == {'INT193_S2'}

        # view=tag + type 组合走通
        resp_tag = servicer.ListTestCases(task_pb.ListTestCasesRequest(
            page=1, per_page=10, view='tag', type='e2e'))
        assert resp_tag.success is True, resp_tag.message
