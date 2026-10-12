# -*- coding: utf-8 -*-
"""INT-152 分组 cascade 删除假成功回归。

- task_service：delete_group_and_commit(cascade=True) 真实级联软删组内
  用例并软删分组本身（修复前 Query.update(synchronize=...) 必抛
  TypeError，分组与用例均未删、同名重建被「已存在」拦截）。
- api_gateway：删除写操作失败必须可见——_grpc_call 支持 reraise，
  delete_testcase_group 失败抛出而非吞成 {}；GroupService.delete 在
  gRPC 失败 / 空结果时返回错误响应，而非 200「分组已删除」假成功。
"""
import os
import uuid

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from types import SimpleNamespace
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles

from shared.models.database import init_db, get_db_session, get_engine, remove_db_session
from api_gateway.infrastructure.request_adapter import set_current_request


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    return 'INTEGER'


_RUN = uuid.uuid4().hex[:8]

_API_CONFIG = {'rounds': [{'round_number': 1,
                           'audios': [{'audio_id': 1, 'audio_name': 'a.wav'}]}]}


def _fake_request(json_body=None, query=None):
    state = SimpleNamespace(_json_body=json_body, _files={}, _form_data={})
    return SimpleNamespace(state=state, query_params=query or {},
                           method='GET', is_json=False, headers={})


# ==================== task_service：级联软删持久化 ====================

@pytest.fixture(scope='module')
def group_db():
    """真实文件型 sqlite：test_case_groups + test_cases 两表。"""
    init_db(pool_size=3)
    remove_db_session()
    from shared.models.database import Base
    from task_service.infrastructure.persistence.models import TestCase, TestCaseGroup
    engine = get_engine()
    Base.metadata.create_all(
        bind=engine, tables=[TestCaseGroup.__table__, TestCase.__table__])

    session = get_db_session()
    g = TestCaseGroup(id=f'g_{_RUN}', name=f'待删组_{_RUN}', algorithm_type='translation')
    session.add(g)
    session.flush()
    c1 = TestCase(id=f'c1_{_RUN}', name=f'用例1_{_RUN}', description='d',
                  config=_API_CONFIG, group_id=g.id, algorithm_type='translation')
    c2 = TestCase(id=f'c2_{_RUN}', name=f'用例2_{_RUN}', description='d',
                  config=_API_CONFIG, group_id=g.id, algorithm_type='translation')
    session.add_all([c1, c2])
    session.commit()
    ids = {'g': g.id, 'c1': c1.id, 'c2': c2.id, 'name': g.name}
    session.close()
    yield ids
    remove_db_session()


class TestCascadeDeletePersistence:
    """task_service：delete_group_and_commit(cascade=True) 真实生效。"""

    def test_cascade_soft_deletes_group_and_cases(self, group_db):
        from task_service.infrastructure.persistence._testcase_group_mixin import (
            TestCaseGroupMixin)
        from task_service.infrastructure.persistence.models import TestCase, TestCaseGroup

        result = TestCaseGroupMixin().delete_group_and_commit(
            group_db['g'], cascade=True)
        assert result == {'id': group_db['g'], 'cascade': True}

        session = get_db_session()
        try:
            g = session.get(TestCaseGroup, group_db['g'])
            assert g.deleted is True
            assert g.deleted_at is not None
            for cid in (group_db['c1'], group_db['c2']):
                c = session.get(TestCase, cid)
                assert c.deleted is True, f'组内用例 {cid} 应被级联软删'
                assert c.deleted_at is not None
        finally:
            session.close()

    def test_same_name_recreatable_after_cascade_delete(self, group_db):
        """删除真实生效后：按名查已删分组返回 None，同名分组可重建。"""
        from task_service.infrastructure.persistence._testcase_group_mixin import (
            TestCaseGroupMixin)

        repo = TestCaseGroupMixin()
        assert repo.get_group_by_name_as_dict(group_db['name']) is None

        recreated = repo.create_group_and_commit(
            f'g_recreated_{_RUN}', group_db['name'], algorithm_type='translation')
        assert recreated['id'] == f'g_recreated_{_RUN}'


# ==================== api_gateway：失败必须可见 ====================

class TestGrpcCallReraise:
    """_grpc_call(reraise=True)：记录日志后重新抛出。"""

    def test_reraise_propagates_exception(self, caplog):
        from api_gateway.infrastructure.grpc_proxies._common import _grpc_call

        def _boom():
            raise RuntimeError('下游失败')

        with caplog.at_level('ERROR'):
            with pytest.raises(RuntimeError, match='下游失败'):
                _grpc_call(_boom, default_return={}, error_msg_prefix='XX 失败',
                           reraise=True)
        assert 'XX 失败' in caplog.text, 'reraise 时仍应记录错误日志'

    def test_default_swallows_unchanged(self):
        """不传 reraise 时行为不变（向后兼容）。"""
        from api_gateway.infrastructure.grpc_proxies._common import _grpc_call

        def _boom():
            raise RuntimeError('x')

        assert _grpc_call(_boom, default_return={'fallback': 1}) == {'fallback': 1}


class TestDeleteTestcaseGroupProxy:
    """delete_testcase_group：gRPC success=False 必须抛出。"""

    def _proxy_with_stub(self, monkeypatch, success, message, data=''):
        from api_gateway.infrastructure.grpc_proxies import task_data_proxies
        captured = {}

        def _fake_stub_factory():
            def _call(req):
                captured['req'] = req
                return SimpleNamespace(success=success, message=message, data=data)
            return SimpleNamespace(DeleteTestCaseGroup=_call)

        monkeypatch.setattr(task_data_proxies, 'get_task_data_service_stub',
                            _fake_stub_factory)
        return captured

    def test_grpc_failure_raises(self, monkeypatch):
        from api_gateway.infrastructure.grpc_proxies.task_data_proxies import (
            task_data_service)
        self._proxy_with_stub(monkeypatch, success=False, message='级联删除出错')
        with pytest.raises(RuntimeError, match='DeleteTestCaseGroup gRPC 失败'):
            task_data_service.delete_testcase_group('g1', cascade=True)

    def test_grpc_failure_carries_task_message(self, monkeypatch):
        from api_gateway.infrastructure.grpc_proxies.task_data_proxies import (
            task_data_service)
        self._proxy_with_stub(monkeypatch, success=False, message='级联删除出错')
        with pytest.raises(RuntimeError, match='级联删除出错'):
            task_data_service.delete_testcase_group('g1', cascade=True)

    def test_success_returns_data(self, monkeypatch):
        import json
        from api_gateway.infrastructure.grpc_proxies.task_data_proxies import (
            task_data_service)
        captured = self._proxy_with_stub(
            monkeypatch, success=True, message='分组已删除',
            data=json.dumps({'id': 'g1', 'cascade': True}))
        result = task_data_service.delete_testcase_group('g1', cascade=True)
        assert result == {'id': 'g1', 'cascade': True}
        assert captured['req'].cascade is True


class TestGroupServiceDelete:
    """网关 GroupService.delete：失败返回错误响应，成功才 200。"""

    def _run(self, monkeypatch, delete_result=None, delete_error=None):
        import api_gateway.application.services.group_service as group_mod
        import api_gateway.infrastructure.grpc_proxies as proxies_pkg

        class _StubTds:
            def get_testcase_stats(self, **kwargs):
                return {'total': 0}

            def delete_testcase_group(self, group_id, cascade=False):
                if delete_error is not None:
                    raise delete_error
                return delete_result

        monkeypatch.setattr(proxies_pkg, 'task_data_service', _StubTds())
        set_current_request(_fake_request(query={'cascade': 'true'}))
        try:
            return group_mod.GroupService.delete('g_404')
        finally:
            set_current_request(None)

    def test_grpc_failure_returns_error_not_200(self, monkeypatch):
        payload, http_code = self._run(
            monkeypatch, delete_error=RuntimeError(
                'DeleteTestCaseGroup gRPC 失败: 级联删除出错'))
        assert http_code != 200, 'gRPC 失败不得返回 200 假成功'
        assert payload['success'] is False
        assert '级联删除出错' in payload['message']

    def test_empty_result_returns_error(self, monkeypatch):
        """gRPC 成功但未确认删除结果（空返回）时不得报成功。"""
        payload, http_code = self._run(monkeypatch, delete_result={})
        assert http_code != 200
        assert payload['success'] is False

    def test_success_returns_200(self, monkeypatch):
        payload, http_code = self._run(
            monkeypatch, delete_result={'id': 'g_404', 'cascade': True})
        assert http_code == 200
        assert payload['success'] is True
        assert payload['message'] == '分组已删除'
