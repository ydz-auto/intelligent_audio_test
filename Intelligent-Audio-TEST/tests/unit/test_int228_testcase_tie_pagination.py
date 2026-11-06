# -*- coding: utf-8 -*-
"""INT-228 专项：testcases 列表排序补 id 次级键 + 网关 page>=1 边界校验。

缺陷（INT-193 审计问题2）：
- 列表 ORDER BY 仅 created_at DESC（SQL 路径 query_testcases），同事务/一次
  flush 批量创建的用例 created_at 全同（生产 Postgres now() 为事务级时间戳），
  平局序由引擎平局行为决定——跨页边界条目重复或漏行，分页正确性无保证。
- 网关 TestCaseListQuery.page 无 ge=1：page=0 时 start=(page-1)*per_page 负切片
  返回移位内容。

覆盖：
- SQL 路径：同 created_at 批量插入 >1 页，逐页拉取无重复、无遗漏，
  拼接顺序 = created_at DESC + id ASC 确定序且跨调用稳定
- 主键 created_at 仍占优：次级键只在平局内生效，不改变新旧先序
- 网关 schema：page=0/-1 校验失败，缺省 page=1 与合法值不受影响
- 网关服务层 get_all：ValidationError → 422 结构化错误，校验失败不触达 ACL

DB：进程级 SQLite（tests/conftest.py 注入），对齐 test_int193 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)


_TABLES = None

# e2e 形态（同 test_int193 口径）：任一音频携带 playback_device_id
_E2E_CONFIG = {'rounds': [{'roundNumber': 1,
                           'audios': [{'audio_id': 1, 'playback_device_id': 3}]}]}


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
def _int228_db():
    _ensure_tables()
    # 前后都清：进程级共享 SQLite，前序套件可能残留 TestCase 行
    _cleanup_tables()
    yield
    _cleanup_tables()


def _add_batch(cases):
    """批量插入。3 元组 (tc_id, name, config)：全部行显式同一 created_at——
    生产 Postgres now() 为事务级时间戳，同一事务/一次 flush 批量创建
    created_at 必全同，确定性复现平局（与 test_int193 的显式单调 created_at
    反向对齐）。4 元组追加 offset_minutes（基于同一 base 偏移），构造非平局
    对照例。"""
    from task_service.infrastructure.persistence.models import TestCase
    session = get_db_session()
    try:
        base = datetime(2026, 1, 1, 0, 0, 0,
                        tzinfo=timezone(timedelta(hours=8)))
        for case in cases:
            tc_id, name, config = case[:3]
            offset = case[3] if len(case) > 3 else 0
            session.add(TestCase(id=tc_id, name=name, config=config,
                                 created_at=base + timedelta(minutes=offset)))
        session.commit()
    finally:
        remove_db_session()


def _tie_ids(n, prefix='INT228_C'):
    return [f'{prefix}{i:02d}' for i in range(1, n + 1)]


def _walk_pages(fetch_page, total, per_page):
    """逐页拉取至取尽，返回拼接 id 列表（每页断言 total 口径一致）。"""
    all_ids = []
    page = 1
    while True:
        pg = fetch_page(page)
        assert pg.total == total
        all_ids.extend(tc.id for tc in pg.items)
        if page == (total + per_page - 1) // per_page:
            break
        page += 1
    return all_ids


class TestRepoTiePagination:
    """同 created_at 批量创建的跨页完整性（INT-228 核心验收）。"""

    def test_sql_path_tie_pagination_no_dup_no_miss_stable(self):
        """SQL 路径：平局批量 >1 页，逐页拉取无重复/无遗漏/序稳定。"""
        from task_service.infrastructure.persistence.testcase_repository import (
            testcase_repository,
        )

        ids = _tie_ids(12)
        _add_batch([(cid, f'用例{cid}', {}) for cid in ids])

        per_page = 5
        walk1 = _walk_pages(
            lambda p: testcase_repository.query_testcases(page=p, per_page=per_page),
            total=12, per_page=per_page)
        assert len(walk1) == 12 and set(walk1) == set(ids)
        # created_at 全同 → 平局强定序 = id ASC（created_at DESC 内的次级键）
        assert walk1 == sorted(ids)
        # 跨调用页间拼接顺序稳定
        walk2 = _walk_pages(
            lambda p: testcase_repository.query_testcases(page=p, per_page=per_page),
            total=12, per_page=per_page)
        assert walk1 == walk2

    def test_created_at_desc_still_dominates_tie_break(self):
        """主键序不回归：非平局条目仍 created_at DESC 在前，id 只破平局。"""
        from task_service.infrastructure.persistence.testcase_repository import (
            testcase_repository,
        )

        ids = _tie_ids(3)
        _add_batch([('INT228_NEW', '更新的用例', dict(_E2E_CONFIG), 60),
                    *[(cid, f'用例{cid}', dict(_E2E_CONFIG)) for cid in ids]])

        per_page = 2
        walk = _walk_pages(
            lambda p: testcase_repository.query_testcases(page=p, per_page=per_page),
            total=4, per_page=per_page)
        # created_at DESC：更新的 NEW 领先，平局三例按 id ASC 跟随
        assert walk == ['INT228_NEW', 'INT228_C01', 'INT228_C02', 'INT228_C03']


class TestGatewayPageValidation:
    """网关 TestCaseListQuery.page ge=1 + get_all 校验失败转 422。"""

    @pytest.fixture
    def gateway_request(self):
        from api_gateway.infrastructure import request_adapter

        def _set(query: dict):
            request_adapter.set_current_request(
                type('R', (), {'query_params': dict(query)})())

        yield _set
        request_adapter.set_current_request(None)

    def test_schema_page_zero_and_negative_rejected(self):
        from api_gateway.schemas.testcase import TestCaseListQuery
        with pytest.raises(ValidationError):
            TestCaseListQuery.model_validate({'page': '0'})
        with pytest.raises(ValidationError):
            TestCaseListQuery.model_validate({'page': '-1'})

    def test_schema_default_and_legal_values_preserved(self):
        from api_gateway.schemas.testcase import TestCaseListQuery
        assert TestCaseListQuery.model_validate({}).page == 1
        assert TestCaseListQuery.model_validate({'page': '3'}).page == 3
        assert TestCaseListQuery.model_validate({'per_page': '10'}).page == 1

    def test_get_all_page_zero_returns_422_structured(self, monkeypatch,
                                                      gateway_request):
        from api_gateway.utils.error_codes import ErrorCode
        from api_gateway.application.services.testcase import (
            testcase_query_service as svc_mod,
        )

        class _AclStub:
            def __init__(self):
                self.calls = []

            def list_testcases(self, **kwargs):
                self.calls.append(kwargs)
                return {'success': True, 'data': {}}

        stub = _AclStub()
        monkeypatch.setattr(svc_mod, '_testcase_acl', stub)
        gateway_request({'page': '0'})

        payload, http_code = svc_mod.TestCaseQueryService.get_all()

        assert http_code == 422
        assert payload['success'] is False
        assert payload['code'] == int(ErrorCode.INVALID_PARAMS)
        assert 'page' in payload['message']
        assert stub.calls == []  # 校验失败不得触达 ACL/gRPC

    def test_get_all_negative_page_returns_422(self, monkeypatch,
                                               gateway_request):
        from api_gateway.application.services.testcase import (
            testcase_query_service as svc_mod,
        )

        monkeypatch.setattr(
            svc_mod, '_testcase_acl',
            type('_Acl', (), {'list_testcases': lambda self, **kw: (
                {'success': True, 'data': {}})})())
        gateway_request({'page': '-2'})

        payload, http_code = svc_mod.TestCaseQueryService.get_all()
        assert http_code == 422
