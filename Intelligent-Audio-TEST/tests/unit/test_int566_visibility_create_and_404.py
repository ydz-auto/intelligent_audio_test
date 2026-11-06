# -*- coding: utf-8 -*-
"""INT-566（INT-981 漏合重交付）专项：新建用例/任务/分组 visibility 落库 + 私有详情非 owner 400→404。

按当前基线（github/V9.7.31 864356754）重交付，覆盖原卡 4 项修复：
- P0-1：testcase create 路径透传 visibility → repo.create_testcase 落库（含复制继承）
- P0-2：task create 路径透传 visibility → create_task_with_relations 落库
- P0-3：group create 路径透传 visibility → create_group(_and_commit) 落库
- P1-5：失败业务码经 data JSON 透传（服务侧 fold_business_code，网关代理按 data.code
  提升）→ 网关 testcase/tag/eval/report 详情私有非 owner 映射 HTTP 404

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表。
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


def _set_request(user_id=100, permissions=None, json_body=None):
    """构造网关 fake request（对齐 test_int466 的 _fake_request 形态）。"""
    from types import SimpleNamespace
    from api_gateway.infrastructure.request_adapter import set_current_request
    state = SimpleNamespace(
        user_id=user_id,
        permissions=list(permissions or []),
        username='dev_user',
        role_id=1,
        _json_body=json_body or {},
    )
    set_current_request(SimpleNamespace(state=state, query_params={}))
    return lambda: set_current_request(None)


def _make_group(group_id, name, visibility=None):
    from task_service.infrastructure.persistence.testcase_repository import testcase_repository
    return testcase_repository.create_group_and_commit(
        group_id, name, '', '', visibility=visibility)


# ---------------- 网关 schema 透传（P0-1/2/3 全链路） ----------------

class TestGatewayCreateVisibilityPassthrough:
    def test_task_create_request_carries_visibility(self, monkeypatch):
        _reset = _set_request(permissions=['task:create'],
                              json_body={'name': 't1', 'visibility': 'private'})
        try:
            from api_gateway.application.services.task import task_command_service as tc_mod
            class _FakeAcl:
                def create(self, data):
                    self.captured = dict(data)
                    return {'success': True, 'message': 'ok', 'data': {'id': 1}}
            fake = _FakeAcl()
            monkeypatch.setattr(tc_mod, '_task_acl', fake)
            payload, http_code = tc_mod.TaskCommandService.create()
            assert http_code == 201
            assert fake.captured.get('visibility') == 'private'
        finally:
            _reset()

    def test_testcase_create_request_carries_visibility(self, monkeypatch):
        _reset = _set_request(permissions=['testcase:create'],
                              json_body={'name': 'tc1', 'group_id': 'g1',
                                         'visibility': 'private'})
        try:
            from api_gateway.application.services.testcase import testcase_command_service as tc_mod
            class _FakeAcl:
                def create(self, data):
                    self.captured = dict(data)
                    return {'success': True, 'message': 'ok', 'data': {'id': 'tc-1'}}
            fake = _FakeAcl()
            monkeypatch.setattr(tc_mod, '_testcase_acl', fake)
            payload, http_code = tc_mod.TestCaseCommandService.create()
            assert http_code == 201
            assert fake.captured.get('visibility') == 'private'
        finally:
            _reset()

    def test_group_create_request_carries_visibility(self, monkeypatch):
        _reset = _set_request(permissions=['group:create'],
                              json_body={'groupName': 'grp1', 'visibility': 'private'})
        try:
            import api_gateway.infrastructure.grpc_proxies as proxies_pkg
            from api_gateway.application.services.group_service import GroupService
            class _StubTds:
                def __init__(self):
                    self.captured = None
                def get_testcase_group_by_name(self, name):
                    return None
                def create_testcase_group(self, name, description='',
                                          algorithm_type='', group_id=None,
                                          visibility=None):
                    self.captured = {'name': name, 'visibility': visibility}
                    return {'id': group_id, 'name': name}
            stub = _StubTds()
            monkeypatch.setattr(proxies_pkg, 'task_data_service', stub)
            payload, http_code = GroupService.create()
            assert http_code == 201
            assert stub.captured['visibility'] == 'private'
        finally:
            _reset()


# ---------------- P0-1：新建用例 visibility 落库 ----------------

class TestTestCaseCreateVisibility:
    def test_create_private_testcase_persists_visibility(self):
        from task_service.infrastructure.persistence.models import TestCase
        _set_user(100)
        group = _make_group('g-1', 'grp1')
        from task_service.application.testcase.testcase_crud_service import testcase_crud_service
        resp = testcase_crud_service.create({
            'name': 'tc-private',
            'group_id': group['id'],
            'visibility': 'private',
        })
        assert resp['success'] is True, resp
        session = get_db_session()
        try:
            row = session.query(TestCase).filter_by(id=resp['data']['id']).first()
            assert row.visibility == 'private'
            assert row.created_by_user_id == 100
        finally:
            session.close()

    def test_create_shared_testcase_defaults(self):
        from task_service.infrastructure.persistence.models import TestCase
        _set_user(100)
        group = _make_group('g-2', 'grp2')
        from task_service.application.testcase.testcase_crud_service import testcase_crud_service
        resp = testcase_crud_service.create({
            'name': 'tc-shared',
            'group_id': group['id'],
        })
        assert resp['success'] is True, resp
        session = get_db_session()
        try:
            row = session.query(TestCase).filter_by(id=resp['data']['id']).first()
            assert row.visibility == 'shared'
        finally:
            session.close()

    def test_create_auto_group_inherits_visibility(self):
        """自动建组（按 group 名）继承用例可见性。"""
        from task_service.infrastructure.persistence.models import TestCaseGroup
        _set_user(100)
        from task_service.application.testcase.testcase_crud_service import testcase_crud_service
        resp = testcase_crud_service.create({
            'name': 'tc-auto-grp',
            'group': '自动组',
            'visibility': 'private',
        })
        assert resp['success'] is True, resp
        session = get_db_session()
        try:
            row = session.query(TestCaseGroup).filter_by(name='自动组').first()
            assert row is not None
            assert row.visibility == 'private'
        finally:
            session.close()

    def test_copy_inherits_visibility(self):
        from task_service.infrastructure.persistence.models import TestCase
        _set_user(100)
        group = _make_group('g-3', 'grp3')
        from task_service.application.testcase.testcase_crud_service import testcase_crud_service
        created = testcase_crud_service.create({
            'name': 'tc-origin',
            'group_id': group['id'],
            'visibility': 'private',
        })
        copied = testcase_crud_service.copy(created['data']['id'])
        assert copied['success'] is True, copied
        session = get_db_session()
        try:
            row = session.query(TestCase).filter_by(id=copied['data']['id']).first()
            assert row.visibility == 'private'
        finally:
            session.close()


# ---------------- P0-2：新建任务 visibility 落库 ----------------

class TestTaskCreateVisibility:
    def test_create_private_task_persists_visibility(self):
        from task_service.infrastructure.persistence.models import Task
        _set_user(100)
        from task_service.application.task.task_crud_service import task_crud_service
        resp = task_crud_service.create({
            'name': 'task-private',
            'visibility': 'private',
        })
        assert resp['success'] is True, resp
        session = get_db_session()
        try:
            row = session.query(Task).filter_by(id=resp['data']['id']).first()
            assert row.visibility == 'private'
            assert row.created_by_user_id == 100
        finally:
            session.close()

    def test_create_shared_task_defaults(self):
        from task_service.infrastructure.persistence.models import Task
        _set_user(100)
        from task_service.application.task.task_crud_service import task_crud_service
        resp = task_crud_service.create({
            'name': 'task-shared',
        })
        assert resp['success'] is True, resp
        session = get_db_session()
        try:
            row = session.query(Task).filter_by(id=resp['data']['id']).first()
            assert row.visibility == 'shared'
        finally:
            session.close()


# ---------------- P0-3：新建分组 visibility 落库 ----------------

class TestGroupCreateVisibility:
    def test_create_private_group_persists_visibility(self):
        from task_service.infrastructure.persistence.models import TestCaseGroup
        _set_user(100)
        item = _make_group('g-p1', 'grp-private', visibility='private')
        assert item['id'] == 'g-p1', item
        session = get_db_session()
        try:
            row = session.query(TestCaseGroup).filter_by(id='g-p1').first()
            assert row.visibility == 'private'
            assert row.created_by_user_id == 100
        finally:
            session.close()

    def test_create_shared_group_defaults(self):
        from task_service.infrastructure.persistence.models import TestCaseGroup
        _set_user(100)
        item = _make_group('g-p2', 'grp-shared')
        assert item['id'] == 'g-p2', item
        session = get_db_session()
        try:
            row = session.query(TestCaseGroup).filter_by(id='g-p2').first()
            assert row.visibility == 'shared'
        finally:
            session.close()


# ---------------- P1-5：业务码透传 + 网关 404 映射 ----------------

class TestGrpcCodePropagation:
    def test_task_service_resp_folds_code_into_data(self):
        """task_service TestCaseConfigResponse 包装把顶层业务码折进 data JSON。"""
        from task_service.interfaces.grpc import testcase_config as tc_mod
        resp = tc_mod.TestCaseConfigServiceServicer._resp({
            'success': False, 'message': '未找到测试用例', 'data': None, 'code': 404,
        })
        assert resp.success is False
        import json
        assert json.loads(resp.data) == {'code': 404}

    def test_success_resp_not_polluted_by_code(self):
        """成功响应不折 code，避免污染成功载荷。"""
        from task_service.interfaces.grpc import testcase_config as tc_mod
        resp = tc_mod.TestCaseConfigServiceServicer._resp({
            'success': True, 'message': '', 'data': {'id': 'tc-1'}, 'code': 201,
        })
        import json
        assert json.loads(resp.data) == {'id': 'tc-1'}

    def test_gateway_proxy_extracts_code_from_data(self):
        """网关代理按 data.code 提升业务码到顶层 dict。"""
        from types import SimpleNamespace
        from api_gateway.infrastructure.grpc_proxies import task_testcase_config_proxies as prox
        proxy = prox._TestCaseConfigProxy()
        resp = SimpleNamespace(success=False, message='未找到测试用例',
                               data='{"code": 404}')
        result = proxy._resp(resp)
        assert result['success'] is False
        assert result['code'] == 404


class TestGatewayDetail404Mapping:
    def test_gateway_testcase_detail_maps_404(self, monkeypatch):
        """私有用例非 owner 详情 → 网关 HTTP 404（而非 400/203）。"""
        from api_gateway.infrastructure.request_adapter import set_current_request
        from types import SimpleNamespace
        state = SimpleNamespace(user_id=200, permissions=['testcase:read'],
                                username='userB', role_id=2, _json_body={})
        set_current_request(SimpleNamespace(state=state, query_params={}))

        from api_gateway.application.services.testcase import testcase_query_service as tc_mod
        fake_acl = SimpleNamespace(
            get_testcase_detail=lambda tc_id: {
                'success': False, 'message': '未找到测试用例', 'data': None, 'code': 404,
            },
        )
        monkeypatch.setattr(tc_mod, '_testcase_acl', fake_acl)
        payload, http_code = tc_mod.TestCaseQueryService.get_one('tc-private')
        assert http_code == 404
        assert payload.get('code') == 404

    def test_gateway_tag_detail_maps_404(self, monkeypatch):
        """私有标签非 owner 详情 → 网关 HTTP 404。"""
        from api_gateway.infrastructure.request_adapter import set_current_request
        from types import SimpleNamespace
        state = SimpleNamespace(user_id=200, permissions=['tag:read'],
                                username='userB', role_id=2, _json_body={})
        set_current_request(SimpleNamespace(state=state, query_params={}))

        from api_gateway.application.services.tag import tag_query_service as tag_mod
        fake_acl = SimpleNamespace(
            get_tag=lambda tag_id: {
                'success': False, 'message': '未找到标签', 'data': None, 'code': 404,
            },
        )
        monkeypatch.setattr(tag_mod, '_tag_acl', fake_acl)
        payload, http_code = tag_mod.TagQueryService.get_one(3)
        assert http_code == 404
        assert payload.get('code') == 404

    def test_gateway_task_detail_maps_404(self, monkeypatch):
        """私有任务非 owner 详情 → 网关 HTTP 404（业务码经 gRPC data JSON 透传）。"""
        from api_gateway.infrastructure.request_adapter import set_current_request
        from types import SimpleNamespace
        state = SimpleNamespace(user_id=200, permissions=['task:read'],
                                username='userB', role_id=2, _json_body={})
        set_current_request(SimpleNamespace(state=state, query_params={}))

        from api_gateway.application.services.task import task_query_service as tq_mod
        fake_acl = SimpleNamespace(
            get_task_detail=lambda task_id: {
                'success': False, 'message': '未找到任务', 'data': None, 'code': 404,
            },
        )
        monkeypatch.setattr(tq_mod, '_task_acl', fake_acl)
        payload, http_code = tq_mod.TaskQueryService.get_one(1)
        assert http_code == 404
        # 任务域业务码沿用 ErrorCode.NOT_FOUND（201）约定，HTTP 状态为 404
        from api_gateway.utils.error_codes import ErrorCode
        assert payload.get('code') == ErrorCode.NOT_FOUND

    def test_gateway_eval_dimension_detail_maps_404(self, monkeypatch):
        """私有评估维度非 owner 详情 → 网关 HTTP 404。"""
        from api_gateway.infrastructure.request_adapter import set_current_request
        from types import SimpleNamespace
        state = SimpleNamespace(user_id=200, permissions=['evaluation:read'],
                                username='userB', role_id=2, _json_body={})
        set_current_request(SimpleNamespace(state=state, query_params={}))

        from api_gateway.application.services.evaluation import evaluation_query_service as eva_mod
        fake_acl = SimpleNamespace(
            get_dimension=lambda dim_id: {
                'success': False, 'message': '未找到评估维度', 'data': None, 'code': 404,
            },
        )
        monkeypatch.setattr(eva_mod, '_evaluation_acl', fake_acl)
        payload, http_code = eva_mod.EvaluationQueryService.get_one(9)
        assert http_code == 404
        assert payload.get('code') == 404

    def test_gateway_report_detail_maps_404(self, monkeypatch):
        """私有报告非 owner 详情 → 网关 HTTP 404（业务码经 data JSON 透传）。"""
        import json as _json
        from api_gateway.application.services.report import report_query_sevice as rq_mod
        from api_gateway.infrastructure.grpc_proxies import report_proxies
        from shared.proto import report_service_pb2 as report_pb

        class _FakeStub:
            def GetReportDetail(self, req):
                return report_pb.ReportConfigResponse(
                    success=False, message='report not found',
                    data=_json.dumps({'code': 404}),
                )
        monkeypatch.setattr(report_proxies, 'get_report_config_service_stub',
                            lambda: _FakeStub())
        payload, http_code = rq_mod.ReportQueryService.get_one(999)
        assert http_code == 404
        assert payload.get('code') == 404
