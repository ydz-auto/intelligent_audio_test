# -*- coding: utf-8 -*-
"""INT-468 用例分组删除守卫被 UUID group_id int() 强转击穿回归。

缺陷链路（实测证据）：
- test_case_groups.id 为 String(50) UUID（隔离库实测 001e3511-... 等），而
  TestCaseAggStatsRequest.group_id 曾声明 int32；
- api_gateway 代理层 `group_id=int(group_id)` 对 UUID 抛
  ValueError: invalid literal for int()（网关日志实证
  "GetTestCaseStats gRPC 失败: invalid literal for int()..."）；
- group_service.delete 的 `except Exception: active_cases = 0` 把查询失败
  静默降级为「无用例」→ 含用例分组不带级联直接删除，守卫失效，
  用例 group_id 悬空指向已删分组（数据完整性缺陷）。

修复（INT-468）：
- proto TestCaseAggStatsRequest.group_id int32 → string，代理层字符串透传
  （group_id=str(group_id) if group_id else ''，与同文件
  delete_testcase_group / get_testcase_group_by_id 一致）；
- group_service.delete 对 stats 查询失败 fail-closed：拒绝删除并返回错误，
  不得把「查询失败」静默降级为「无用例」绕过守卫。

回归用例：
① 代理对 UUID group_id 字符串透传（proto string 字段原样承载，不 int 强转）；
② stats 查询失败时 delete 拒绝删除（fail-closed，不绕过守卫）；
③ 对照组：stats 返回 active_cases>0 且 cascade=false 时守卫拦截、不执行删除；
④ stats 返回 active_cases=0 时正常删除（空分组可删）；
⑤ cascade=true 且分组有用例时守卫放行（显式级联删除语义不变）。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import json
from types import SimpleNamespace

import pytest

from api_gateway.infrastructure.request_adapter import set_current_request

GROUP_UUID = '001e3511-8515-4b51-baad-b9739f28d04b'


def _fake_request(query=None):
    state = SimpleNamespace(_json_body={}, _files={}, _form_data={})
    return SimpleNamespace(state=state, query_params=query or {},
                           method='GET', is_json=False, headers={})


class TestGetTestcaseStatsGroupIdPassthrough:
    """代理 get_testcase_stats：group_id 字符串透传，不得 int 强转（INT-468）。"""

    def _proxy_with_stub(self, monkeypatch, success, message, data=''):
        from api_gateway.infrastructure.grpc_proxies import task_data_proxies
        captured = {}

        def _fake_stub_factory():
            def _call(req):
                captured['req'] = req
                return SimpleNamespace(success=success, message=message, data=data)
            return SimpleNamespace(GetTestCaseStats=_call)

        monkeypatch.setattr(task_data_proxies, 'get_task_data_service_stub',
                            _fake_stub_factory)
        return captured

    def test_uuid_group_id_passed_through_as_string(self, monkeypatch):
        """UUID group_id 不得 int 强转：proto string 字段原样承载，统计正常返回。"""
        from api_gateway.infrastructure.grpc_proxies.task_data_proxies import (
            task_data_service)
        captured = self._proxy_with_stub(
            monkeypatch, success=True, message='ok',
            data=json.dumps({'total': 3}))
        result = task_data_service.get_testcase_stats(group_id=GROUP_UUID)
        assert captured['req'].group_id == GROUP_UUID
        assert result == {'total': 3}

    def test_int_group_id_coerced_to_str(self, monkeypatch):
        """兼容旧整型 group_id：仍字符串化透传（不回归既有调用方）。"""
        from api_gateway.infrastructure.grpc_proxies.task_data_proxies import (
            task_data_service)
        captured = self._proxy_with_stub(
            monkeypatch, success=True, message='ok',
            data=json.dumps({'total': 0}))
        result = task_data_service.get_testcase_stats(group_id=42)
        assert captured['req'].group_id == '42'
        assert result == {'total': 0}


class TestGroupServiceDeleteGuard:
    """网关 GroupService.delete：守卫不可被 stats 查询失败绕过（INT-468）。"""

    def _run(self, monkeypatch, stats_result=None, stats_error=None,
             query=None, delete_result={'id': GROUP_UUID}):
        import api_gateway.application.services.group_service as group_mod
        import api_gateway.infrastructure.grpc_proxies as proxies_pkg

        calls = {'delete': 0}

        class _StubTds:
            def get_testcase_stats(self, group_id=None, **kwargs):
                if stats_error is not None:
                    raise stats_error
                return stats_result or {}

            def delete_testcase_group(self, group_id, cascade=False):
                calls['delete'] += 1
                return delete_result

        monkeypatch.setattr(proxies_pkg, 'task_data_service', _StubTds())
        set_current_request(_fake_request(query=query or {}))
        try:
            payload, http_code = group_mod.GroupService.delete(GROUP_UUID)
            return payload, http_code, calls
        finally:
            set_current_request(None)

    def test_stats_query_failure_blocks_delete(self, monkeypatch):
        """stats 查询失败（fail-closed）：拒绝删除，不得静默降级为无用例绕过守卫。"""
        payload, http_code, calls = self._run(
            monkeypatch, stats_error=RuntimeError('GetTestCaseStats gRPC 失败: 下游不可用'))
        assert http_code != 200
        assert payload['success'] is False
        assert '无法查询分组用例统计' in payload['message']
        assert calls['delete'] == 0, 'stats 查询失败时不得执行删除'

    def test_guard_blocks_when_cases_exist_without_cascade(self, monkeypatch):
        """对照组：stats 返回 active_cases>0 且 cascade=false → 守卫拦截、不删除。"""
        payload, http_code, calls = self._run(
            monkeypatch, stats_result={'total': 3})
        assert http_code == 400
        assert payload['success'] is False
        assert payload['message'] == '该分组下存在测试用例，无法删除'
        assert calls['delete'] == 0, '含用例分组不带级联时不得执行删除'

    def test_empty_group_deletes_normally(self, monkeypatch):
        """stats 返回 active_cases=0：空分组正常删除（守卫放行）。"""
        payload, http_code, calls = self._run(
            monkeypatch, stats_result={'total': 0})
        assert http_code == 200
        assert payload['success'] is True
        assert payload['message'] == '分组已删除'
        assert calls['delete'] == 1

    def test_cascade_bypasses_guard(self, monkeypatch):
        """cascade=true 且分组有用例：显式级联删除，守卫放行。"""
        payload, http_code, calls = self._run(
            monkeypatch, stats_result={'total': 3}, query={'cascade': 'true'})
        assert http_code == 200
        assert payload['success'] is True
        assert calls['delete'] == 1
