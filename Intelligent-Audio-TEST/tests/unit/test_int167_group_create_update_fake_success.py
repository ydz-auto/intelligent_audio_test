# -*- coding: utf-8 -*-
"""INT-167 分组 create/update 假成功回归（INT-152 同型吞错）。

- api_gateway：写操作 gRPC 失败必须可见——create_testcase_group /
  update_testcase_group 与 delete 同待遇（_grpc_call reraise=True），
  失败抛出而非吞成 {}；GroupService.create / update 对返回结果做
  成功校验，gRPC 失败 / 空结果（未确认持久化）时返回错误响应，
  不做 `.get('id', group_id)` 本地 uuid 兜底假成功。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import json
from types import SimpleNamespace

import pytest

from api_gateway.infrastructure.request_adapter import set_current_request


def _fake_request(json_body=None, query=None):
    state = SimpleNamespace(_json_body=json_body, _files={}, _form_data={})
    return SimpleNamespace(state=state, query_params=query or {},
                           method='GET', is_json=False, headers={})


# ==================== 代理层：失败必须抛出 ====================

class _ProxyFailureBase:
    """gRPC success=False / 调用异常 必须从代理抛出（与 delete 同待遇）。"""

    rpc_attr = ''
    proxy_method = ''
    proxy_args = ()
    proxy_kwargs = {}
    error_prefix = ''

    def _proxy_with_stub(self, monkeypatch, success, message, data=''):
        from api_gateway.infrastructure.grpc_proxies import task_data_proxies
        captured = {}

        def _fake_stub_factory():
            def _call(req):
                captured['req'] = req
                return SimpleNamespace(success=success, message=message, data=data)
            return SimpleNamespace(**{self.rpc_attr: _call})

        monkeypatch.setattr(task_data_proxies, 'get_task_data_service_stub',
                            _fake_stub_factory)
        return captured

    def test_grpc_failure_raises(self, monkeypatch):
        from api_gateway.infrastructure.grpc_proxies.task_data_proxies import (
            task_data_service)
        self._proxy_with_stub(monkeypatch, success=False, message='下游存储不可用')
        with pytest.raises(RuntimeError, match=self.error_prefix):
            getattr(task_data_service, self.proxy_method)(*self.proxy_args,
                                                          **self.proxy_kwargs)

    def test_grpc_failure_carries_task_message(self, monkeypatch):
        from api_gateway.infrastructure.grpc_proxies.task_data_proxies import (
            task_data_service)
        self._proxy_with_stub(monkeypatch, success=False, message='下游存储不可用')
        with pytest.raises(RuntimeError, match='下游存储不可用'):
            getattr(task_data_service, self.proxy_method)(*self.proxy_args,
                                                          **self.proxy_kwargs)

    def test_success_returns_data(self, monkeypatch):
        from api_gateway.infrastructure.grpc_proxies.task_data_proxies import (
            task_data_service)
        self._proxy_with_stub(monkeypatch, success=True, message='ok',
                              data=json.dumps({'id': 'g1', 'name': '组1'}))
        result = getattr(task_data_service, self.proxy_method)(*self.proxy_args,
                                                               **self.proxy_kwargs)
        assert result == {'id': 'g1', 'name': '组1'}


class TestCreateTestcaseGroupProxy(_ProxyFailureBase):
    rpc_attr = 'CreateTestCaseGroup'
    proxy_method = 'create_testcase_group'
    proxy_args = ('新组', '描述', 'translation', 'g_req')
    proxy_kwargs = {}
    error_prefix = 'CreateTestCaseGroup gRPC 失败'


class TestUpdateTestcaseGroupProxy(_ProxyFailureBase):
    rpc_attr = 'UpdateTestCaseGroup'
    proxy_method = 'update_testcase_group'
    proxy_args = ('g_1', '新名', '新描述', 'translation')
    proxy_kwargs = {}
    error_prefix = 'UpdateTestCaseGroup gRPC 失败'


# ==================== 服务层：失败返回错误响应 ====================

class TestGroupServiceCreate:
    """网关 GroupService.create：失败/空结果返回错误响应，仅确认成功才 201。"""

    def _run(self, monkeypatch, create_result=None, create_error=None):
        import api_gateway.application.services.group_service as group_mod
        import api_gateway.infrastructure.grpc_proxies as proxies_pkg

        class _StubTds:
            def get_testcase_group_by_name(self, name):
                return None

            def create_testcase_group(self, name, description='',
                                      algorithm_type='', group_id=None):
                if create_error is not None:
                    raise create_error
                return create_result

        monkeypatch.setattr(proxies_pkg, 'task_data_service', _StubTds())
        set_current_request(_fake_request(
            json_body={'groupName': '新组', 'id': 'g_req_1'}))
        try:
            return group_mod.GroupService.create()
        finally:
            set_current_request(None)

    def test_grpc_failure_returns_error_not_201(self, monkeypatch):
        payload, http_code = self._run(
            monkeypatch, create_error=RuntimeError(
                'CreateTestCaseGroup gRPC 失败: 下游存储不可用'))
        assert http_code != 201, 'gRPC 失败不得返回 201 假成功'
        assert payload['success'] is False
        assert '下游存储不可用' in payload['message']

    def test_empty_result_returns_error_no_ghost_id(self, monkeypatch):
        """gRPC 成功但未确认创建结果（空返回）时不得以本地 uuid 兜底假成功。"""
        payload, http_code = self._run(monkeypatch, create_result={})
        assert http_code != 201
        assert payload['success'] is False
        assert '未确认' in payload['message']

    def test_success_returns_201_with_task_id(self, monkeypatch):
        payload, http_code = self._run(
            monkeypatch, create_result={'id': 'g_task_confirmed', 'name': '新组'})
        assert http_code == 201
        assert payload['success'] is True
        assert payload['message'] == '分组创建成功'
        assert payload['data']['id'] == 'g_task_confirmed'


class TestGroupServiceUpdate:
    """网关 GroupService.update：失败/空结果返回错误响应，仅确认成功才 200。"""

    def _run(self, monkeypatch, update_result=None, update_error=None):
        import api_gateway.application.services.group_service as group_mod
        import api_gateway.infrastructure.grpc_proxies as proxies_pkg

        class _StubTds:
            def update_testcase_group(self, group_id, name='', description='',
                                      algorithm_type=''):
                if update_error is not None:
                    raise update_error
                return update_result

        monkeypatch.setattr(proxies_pkg, 'task_data_service', _StubTds())
        set_current_request(_fake_request(json_body={'name': '改名'}))
        try:
            return group_mod.GroupService.update('g_404')
        finally:
            set_current_request(None)

    def test_grpc_failure_returns_error_not_200(self, monkeypatch):
        payload, http_code = self._run(
            monkeypatch, update_error=RuntimeError(
                'UpdateTestCaseGroup gRPC 失败: 下游存储不可用'))
        assert http_code != 200, 'gRPC 失败不得返回 200 假成功'
        assert payload['success'] is False
        assert '下游存储不可用' in payload['message']

    def test_empty_result_returns_error(self, monkeypatch):
        """gRPC 成功但未确认更新结果（空返回）时不得报成功。"""
        payload, http_code = self._run(monkeypatch, update_result={})
        assert http_code != 200
        assert payload['success'] is False
        assert '未确认' in payload['message']

    def test_success_returns_200_with_task_id(self, monkeypatch):
        payload, http_code = self._run(
            monkeypatch, update_result={'id': 'g_404', 'name': '改名'})
        assert http_code == 200
        assert payload['success'] is True
        assert payload['message'] == '分组信息更新成功'
        assert payload['data']['id'] == 'g_404'
