# -*- coding: utf-8 -*-
"""INT-1572 返工回归（INT-1482 复测 P2/P3）：

1. 用例查询完整性口径（partial / missing_case_ids）必须从 ACL 一路传到
   case-averages 响应，页面据此显示「数据不完整」而不是拿部分用例算错均值；
2. 报告资源元数据（设备 / API 配置）按 id 走 TTL 缓存：case-averages 单次会按
   「每条测试结果」重复取同一批资源，不缓存就是几百次重复 gRPC；
3. result_type 优先取 DB 轻量载荷，取不到才回落 OSS 结果文件（138 条结果每条
   一次 head 请求会叠成几十秒）。
"""
import json
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from report_service.application.handlers._report_stats_query_mixin import (  # noqa: E402
    ReportStatsQueryMixin,
)
from report_service.application.services.report_utils.resource_mixin import (  # noqa: E402
    result_type_from_db_payload,
)
from report_service.infrastructure.acl import (  # noqa: E402
    apitest_acl_repository as api_acl_mod,
)
from report_service.infrastructure.acl import (  # noqa: E402
    device_acl_repository as dev_acl_mod,
)
from report_service.infrastructure.acl.apitest_acl_repository import (  # noqa: E402
    ApiTestAclRepositoryImpl,
)
from report_service.infrastructure.acl.device_acl_repository import (  # noqa: E402
    DeviceConfigAclRepositoryImpl,
)


@pytest.fixture(autouse=True)
def _clean_resource_cache():
    dev_acl_mod._device_cache.clear()
    api_acl_mod._api_cache.clear()
    yield
    dev_acl_mod._device_cache.clear()
    api_acl_mod._api_cache.clear()


# ==================== 1. result_type 从 DB 载荷取 ====================

class TestResultTypeFromDbPayload:
    def test_dict_payload_hit(self):
        assert result_type_from_db_payload({'result_type': 'e2e'}) == 'e2e'

    def test_json_string_payload_hit(self):
        assert result_type_from_db_payload(json.dumps({'result_type': 'api'})) == 'api'

    def test_missing_key_falls_back_to_none(self):
        """载荷里没有该键时返回 None，调用方才回落结果文件。"""
        assert result_type_from_db_payload({'foo': 1}) is None
        assert result_type_from_db_payload(json.dumps({'foo': 1})) is None
        assert result_type_from_db_payload(None) is None
        assert result_type_from_db_payload('') is None

    def test_invalid_json_falls_back_to_none(self):
        assert result_type_from_db_payload('{not-json') is None


# ==================== 2. 资源元数据 TTL 缓存 ====================

def _stub(monkeypatch, module, factory_name, resp, calls):
    def _get_stub():
        return SimpleNamespace(
            GetDevice=lambda req: (calls.append(('device', req)), resp)[1],
            GetAPIConfig=lambda req: (calls.append(('api', req)), resp)[1],
        )
    monkeypatch.setattr(module, factory_name, _get_stub)


class TestResourceAclCache:
    def test_device_lookup_is_cached(self, monkeypatch):
        import shared.clients.grpc_clients as shared_clients

        calls = []
        resp = SimpleNamespace(success=True, data=json.dumps(
            {'id': 7, 'name': '设备7', 'device_type': 'phone'}))
        _stub(monkeypatch, shared_clients, 'get_device_config_service_stub', resp, calls)
        repo = DeviceConfigAclRepositoryImpl()

        first = repo.get_device(7)
        second = repo.get_device(7)

        assert first is not None and second is not None
        assert second.name == '设备7'
        assert len(calls) == 1  # 第二次命中缓存，不再发 gRPC

    def test_device_cache_returns_isolated_copy(self, monkeypatch):
        """调用方改返回对象不得污染缓存（缓存读写深拷贝）。"""
        import shared.clients.grpc_clients as shared_clients

        calls = []
        resp = SimpleNamespace(success=True, data=json.dumps(
            {'id': 7, 'name': '设备7', 'result_types': ['api']}))
        _stub(monkeypatch, shared_clients, 'get_device_config_service_stub', resp, calls)
        repo = DeviceConfigAclRepositoryImpl()

        first = repo.get_device(7)
        first.name = 'mutated-by-caller'
        second = repo.get_device(7)

        assert second.name == '设备7'

    def test_device_failure_is_not_cached(self, monkeypatch):
        """取不到的设备不缓存：新建 / 恢复的设备立即可见。"""
        import shared.clients.grpc_clients as shared_clients

        calls = []
        resp = SimpleNamespace(success=False, data='')
        _stub(monkeypatch, shared_clients, 'get_device_config_service_stub', resp, calls)
        repo = DeviceConfigAclRepositoryImpl()

        assert repo.get_device(8) is None
        assert repo.get_device(8) is None
        assert len(calls) == 2

    def test_api_lookup_is_cached(self, monkeypatch):
        import shared.clients.grpc_clients as shared_clients

        calls = []
        resp = SimpleNamespace(success=True, data=json.dumps(
            {'id': 9, 'name': '接口9'}))
        _stub(monkeypatch, shared_clients, 'get_api_test_service_stub', resp, calls)
        repo = ApiTestAclRepositoryImpl()

        repo.get_api(9)
        repo.get_api(9)

        assert len(calls) == 1

    def test_resource_cache_can_be_disabled(self, monkeypatch):
        import shared.clients.grpc_clients as shared_clients

        calls = []
        resp = SimpleNamespace(success=True, data=json.dumps({'id': 7, 'name': '设备7'}))
        _stub(monkeypatch, shared_clients, 'get_device_config_service_stub', resp, calls)
        dev_acl_mod._device_cache._ttl = 0

        repo = DeviceConfigAclRepositoryImpl()
        repo.get_device(7)
        repo.get_device(7)

        assert len(calls) == 2


# ==================== 3. partial 口径传到 case-averages 响应 ====================

class TestPartialPropagation:
    def test_query_test_cases_and_results_fills_lookup_status(self, monkeypatch):
        import report_service.application.services.report_query_builder as rqb
        import report_service.infrastructure.clients.grpc_clients as grpc_clients

        monkeypatch.setattr(
            rqb, '_grpc_get_task_case_ids',
            lambda tid: [{'test_case_id': 'c-1'}, {'test_case_id': 'c-2'}])
        monkeypatch.setattr(
            grpc_clients, '_grpc_lookup_testcases_by_ids',
            lambda ids: {
                'items': {'c-1': {'id': 'c-1', 'name': '用例1', 'group': {'name': 'g'}, 'tags': []}},
                'missing_ids': ['c-2'],
                'incomplete_ids': ['c-2'],
                'partial': True,
            }, raising=False)
        monkeypatch.setattr(
            grpc_clients, '_grpc_get_test_results_by_task_ids',
            lambda ids: [], raising=False)

        m = ReportStatsQueryMixin.__new__(ReportStatsQueryMixin)
        status = {}
        m._query_test_cases_and_results(
            1234, 1234, None, [], [], True, lookup_status=status)

        assert status['partial'] is True
        assert status['incomplete_ids'] == ['c-2']
        assert status['missing_ids'] == ['c-2']

    def test_case_averages_response_carries_partial_flag(self, monkeypatch):
        from report_service.application.services.report_utils import ReportUtils

        m = ReportStatsQueryMixin.__new__(ReportStatsQueryMixin)

        def _fake_query(task_id, category, categories, tags, include_untagged,
                        report_id=None, lookup_status=None):
            if lookup_status is not None:
                lookup_status.update({
                    'missing_ids': ['c-9'], 'incomplete_ids': ['c-9'], 'partial': True})
            return ({'id': task_id}, task_id, ['c-1'], [], {}, False)

        monkeypatch.setattr(m, '_query_cases_for_averages', _fake_query)
        monkeypatch.setattr(m, '_calculate_averages', lambda *a, **k: {
            'filtered_case_ids': ['c-1'],
            'test_results': [],
            'overall_averages': [],
            'averages_map': {},
            'metric_data': [],
            'metric_name_to_id': {},
            'tag_metric_data': [],
            'raw_data': [],
            'normal_distribution_data': {},
            'resources': [],
            'resource_headers': [],
        })
        for name in ('flatten_metric_data', 'flatten_tag_metric_data', 'flatten_raw_data'):
            monkeypatch.setattr(ReportUtils, name, staticmethod(lambda *a, **k: []))

        resp = m.handle_get_case_averages({'task_id': 1})

        assert resp['total_cases'] == 1
        assert resp['partial'] is True
        assert resp['missing_case_ids'] == ['c-9']

    def test_case_averages_without_gap_is_not_partial(self, monkeypatch):
        from report_service.application.services.report_utils import ReportUtils

        m = ReportStatsQueryMixin.__new__(ReportStatsQueryMixin)
        monkeypatch.setattr(m, '_query_cases_for_averages', lambda *a, **k: (
            {'id': 1}, 1, [], [], {}, False))
        monkeypatch.setattr(m, '_calculate_averages', lambda *a, **k: {
            'filtered_case_ids': [], 'test_results': [], 'overall_averages': [],
            'averages_map': {}, 'metric_data': [], 'metric_name_to_id': {},
            'tag_metric_data': [], 'raw_data': [], 'normal_distribution_data': {},
            'resources': [], 'resource_headers': [],
        })
        for name in ('flatten_metric_data', 'flatten_tag_metric_data', 'flatten_raw_data'):
            monkeypatch.setattr(ReportUtils, name, staticmethod(lambda *a, **k: []))

        resp = m.handle_get_case_averages({'task_id': 1})

        assert resp['partial'] is False
        assert resp['missing_case_ids'] == []
