# -*- coding: utf-8 -*-
"""INT-1752 守卫：报告原始响应按需展开 + 加权聚合不静默降级。

覆盖：
1. 加权策略（weighted_sum_ratio / weighted_wer）带 api_raw_response 时数值 ≠ 简单平均；
2. 缺 api_raw_response 时降级为简单平均，且两条链都产出降级说明（不再静默）：
   - 报告主生成链 core_metrics['aggregation_degraded']
   - 查询链 summary['aggregation_degraded']
3. evaluation_service servicer 透传 include_body（不再恒 False）；
4. report_service ACL 把 include_body 写进 gRPC 请求；
5. 报告详情按需读取 API 原始响应：分页 / 截断 / 非 API 用例不可用 / 跨报告用例拒绝；
6. evaluation_service.update_task_case_status 不再保留未使用的 test_type 参数。
"""
import inspect
import os
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.models.common_enums import TaskStatus
from report_service.domain.services.aggregation_strategies import (
    WeightedSumRatioStrategy,
    explain_degradation,
    simple_average_of_items,
)
import report_service.application.services.report_aggregation.stats_mixin as stats_mod
from report_service.application.services.report_aggregation.stats_mixin import _AggregationStatsMixin
import report_service.application.services.report_utils.metrics_mixin as metrics_mod
from report_service.application.services.report_utils.metrics_mixin import MetricsMixin
import report_service.application.services.report_utils.resource_mixin as resource_mod


# ---------------- 合成数据 ----------------

def _dims():
    return [
        {'id': 1, 'name': '准确率', 'statistic_method': 'average', 'agg_denominator': 'case', 'exclude_rounds': []},
        {'id': 9, 'name': 'WER', 'statistic_method': 'weighted_sum_ratio', 'agg_denominator': 'case', 'exclude_rounds': []},
    ]


def _output_params():
    return [
        {'dim_id': 9, 'param_code': 'errors', 'field_path': 'errors', 'param_direction': 'output', 'agg_role': 'numerator'},
        {'dim_id': 9, 'param_code': 'length', 'field_path': 'length', 'param_direction': 'output', 'agg_role': 'denominator'},
    ]


def _raw(errors, length):
    return {'code': 0, 'data': {'result': {'errors': errors, 'length': length}}}


def _dim_results_map(with_raw=True):
    """两条结果：WER 加权值 = (1+9)/(100+100)*100 = 5.0；简单平均 = (10+20)/2 = 15.0。"""
    def _item(errors, length, rid):
        return {
            'dimension_id': 9,
            'dimension_value': 10.0 if rid == 1 else 20.0,
            'round_number': None,
            'test_result_id': rid,
            'api_raw_response': _raw(errors, length) if with_raw else None,
        }

    return {
        1: [
            {'dimension_id': 1, 'dimension_value': 90.0, 'round_number': None, 'test_result_id': 1},
            _item(1, 100, 1),
        ],
        2: [
            {'dimension_id': 1, 'dimension_value': 70.0, 'round_number': None, 'test_result_id': 2},
            _item(9, 100, 2),
        ],
    }


def _results():
    return [
        {'id': 1, 'task_id': 7, 'test_case_id': 101, 'execution_status': TaskStatus.COMPLETED.value, 'device_id': 1},
        {'id': 2, 'task_id': 7, 'test_case_id': 102, 'execution_status': TaskStatus.COMPLETED.value, 'device_id': 1},
    ]


def _patch_grpc():
    test_cases_map = {
        '101': {'group': {'id': 1, 'name': 'g1'}, 'tags': []},
        '102': {'group': {'id': 1, 'name': 'g1'}, 'tags': []},
    }
    device = {'id': 1, 'name': 'DevA', 'app_version': None}
    return [
        patch.object(stats_mod, '_grpc_get_dimension_params', side_effect=lambda dim_id: _output_params() if dim_id == 9 else []),
        patch.object(metrics_mod, '_grpc_get_dimension_params', side_effect=lambda dim_id: _output_params() if dim_id == 9 else []),
        patch.object(metrics_mod, '_grpc_list_testcases_by_ids', return_value=test_cases_map),
        patch.object(resource_mod, '_grpc_get_device', return_value=device),
    ]


def _report_chain(dim_results_map):
    resources = []
    core = MetricsMixin.calculate_core_metrics(
        results=_results(), all_dimensions=_dims(), resources=resources,
        dim_results_map=dim_results_map, tasks_map=None, use_time_prefix=False,
    )
    assert len(resources) == 1, f'fixture 应收敛到单资源，实际 {resources}'
    return core, resources[0]


# ---------------- 1. 策略层 ----------------

class TestWeightedStrategy:
    def test_weighted_value_differs_from_simple_average_with_raw_response(self):
        items = [
            {'dimension_value': 10.0, 'api_raw_response': _raw(1, 100), 'test_result_id': 1},
            {'dimension_value': 20.0, 'api_raw_response': _raw(9, 100), 'test_result_id': 2},
        ]
        params = _output_params()
        weighted = WeightedSumRatioStrategy().aggregate(items, output_params=params)
        simple = simple_average_of_items(items)
        assert weighted == pytest.approx(5.0)
        assert simple == pytest.approx(15.0)
        assert weighted != simple
        assert explain_degradation('weighted_sum_ratio', items, params) is None

    def test_strategy_returns_none_without_raw_response(self):
        items = [
            {'dimension_value': 10.0, 'api_raw_response': None, 'test_result_id': 1},
            {'dimension_value': 20.0, 'api_raw_response': None, 'test_result_id': 2},
        ]
        assert WeightedSumRatioStrategy().aggregate(items, output_params=_output_params()) is None


# ---------------- 2. 两条链的生效与降级 ----------------

class TestReportChainWeighted:
    def test_weighted_metric_applied_when_raw_response_present(self):
        p = _patch_grpc()
        with p[0], p[1], p[2], p[3]:
            core, resource = _report_chain(_dim_results_map(with_raw=True))
        value = core['metric_data'][resource]['WER']
        assert value == pytest.approx(5.0)
        assert value != pytest.approx(15.0)
        assert core['aggregation_degraded'] == {}

    def test_weighted_metric_degraded_and_marked_without_raw_response(self):
        p = _patch_grpc()
        with p[0], p[1], p[2], p[3]:
            core, resource = _report_chain(_dim_results_map(with_raw=False))
        # 不再静默：值退化为简单平均，同时给出降级说明
        assert core['metric_data'][resource]['WER'] == pytest.approx(15.0)
        degraded = core['aggregation_degraded']['WER']
        assert degraded['configured_method'] == 'weighted_sum_ratio'
        assert degraded['applied_method'] == 'average'
        assert degraded['reason'] == 'missing_api_raw_response'

    def test_mark_degraded_metrics_writes_flags_on_all_metrics(self):
        from report_service.application.services.report_task_generator import ReportTaskGenerator
        all_metrics = [{'id': 9, 'name': 'WER'}, {'id': 1, 'name': '准确率'}]
        degraded = {'WER': {'configured_method': 'weighted_sum_ratio', 'applied_method': 'average',
                            'reason': 'missing_api_raw_response', 'detail': 'x'}}
        ReportTaskGenerator._mark_degraded_metrics(all_metrics, degraded)
        assert all_metrics[0]['aggregation_degraded'] is True
        assert all_metrics[0]['degradation_reason'] == 'missing_api_raw_response'
        assert 'aggregation_degraded' not in all_metrics[1]


class TestQueryChainWeighted:
    def _run(self, with_raw):
        dim_strategy_info = _AggregationStatsMixin._build_dim_strategy_info(_dims())
        metric_name_to_id = {str(d['name']): int(d['id']) for d in _dims()}
        degraded = {}
        with _patch_grpc()[0]:
            averages_map, _overall = _AggregationStatsMixin._compute_weighted_averages(
                _results(), _dims(), metric_name_to_id, dim_strategy_info,
                _dim_results_map(with_raw=with_raw), degraded_out=degraded)
        return averages_map, degraded

    def test_weighted_average_uses_raw_response(self):
        averages_map, degraded = self._run(with_raw=True)
        assert averages_map['WER'] == pytest.approx(5.0)
        assert degraded == {}

    def test_weighted_average_degrades_with_explanation(self):
        averages_map, degraded = self._run(with_raw=False)
        assert averages_map['WER'] == pytest.approx(15.0)   # 降级为简单平均，不再丢值
        assert degraded['WER']['reason'] == 'missing_api_raw_response'


# ---------------- 3. include_body 透传链 ----------------

class TestIncludeBodyPlumbing:
    def test_evaluation_servicer_passes_include_body(self):
        from evaluation_service.interfaces.grpc import evaluation_data_servicer as mod
        captured = {}
        servicer = mod.EvaluationDataServiceServicer()

        def _fake_query(result_ids, include_body=False):
            captured['result_ids'] = result_ids
            captured['include_body'] = include_body
            return {'success': True, 'message': '', 'data': {'items': []}}

        from evaluation_service.application.queries import evaluation_query_service as qs_mod
        with patch.object(qs_mod.evaluation_query_service, 'get_dimension_results_by_result_ids',
                          side_effect=_fake_query):
            from shared.proto import evaluation_service_pb2 as eval_pb
            servicer.GetDimensionResultsByResultIds(
                eval_pb.GetDimensionResultsByResultIdsRequest(result_ids='[1,2]', include_body=True))
        assert captured == {'result_ids': [1, 2], 'include_body': True}

    def test_report_acl_sends_include_body_flag(self):
        from report_service.infrastructure.acl.evaluation_acl_repository import EvaluationDataAclRepositoryImpl
        seen = {}

        class _Resp:
            success = True
            data = '{"items": []}'

        class _Stub:
            def GetDimensionResultsByResultIds(self, req):
                seen['include_body'] = req.include_body
                return _Resp()

        with patch('shared.clients.grpc_clients.get_evaluation_data_service_stub', return_value=_Stub()):
            EvaluationDataAclRepositoryImpl().get_dimension_results_by_result_ids([1], include_body=True)
        assert seen['include_body'] is True

    def test_report_acl_default_is_false(self):
        from report_service.infrastructure.acl.evaluation_acl_repository import EvaluationDataAclRepositoryImpl
        seen = {}

        class _Resp:
            success = True
            data = '{"items": []}'

        class _Stub:
            def GetDimensionResultsByResultIds(self, req):
                seen['include_body'] = req.include_body
                return _Resp()

        with patch('shared.clients.grpc_clients.get_evaluation_data_service_stub', return_value=_Stub()):
            EvaluationDataAclRepositoryImpl().get_dimension_results_by_result_ids([1])
        assert seen['include_body'] is False


# ---------------- 4. 报告详情按需读取原始响应 ----------------

class _Case:
    def __init__(self, case_id):
        self.test_case_id = case_id


class _Summary:
    def __init__(self, task_ids):
        self.metadata = {'task_ids': task_ids}


class _Aggregate:
    def __init__(self, task_id=7):
        self.task_id = task_id


class _FakeRepo:
    def __init__(self, cases=('c1',), summaries=()):
        self._cases = [_Case(c) for c in cases]
        self._summaries = [_Summary(t) for t in summaries]

    def get_by_id(self, report_id):
        return _Aggregate()

    def load_cases(self, report_id):
        return self._cases

    def load_summaries(self, report_id):
        return self._summaries


class _Result:
    def __init__(self, rid, api_id):
        self.id = rid
        self.api_id = api_id


def _handler(repo):
    from report_service.application.handlers.report_handlers import ReportQueryHandler
    return ReportQueryHandler(repository=repo)


def _big_body(size):
    return {'code': 0, 'data': {'result': {'errors': 1, 'length': 100, 'blob': 'x' * size}}}


def _patch_raw_grpc(results, dim_items):
    from report_service.infrastructure.clients import grpc_clients as gc
    return [
        patch.object(gc, '_grpc_get_test_results_by_task_and_case', return_value=results),
        patch.object(gc, '_grpc_get_dimension_results_by_result_ids', return_value=dim_items),
        patch.object(gc, '_grpc_get_dimension_by_ids', return_value={}),
    ]


class TestRawResponseHandler:
    def test_unavailable_for_non_api_case(self):
        repo = _FakeRepo()
        patches = _patch_raw_grpc([_Result(11, None)], {})
        with patches[0], patches[1], patches[2]:
            data = _handler(repo).handle_get_case_dimension_raw_response(
                3, {'case_id': 'c1', 'dimension_id': 9})
        assert data['available'] is False
        assert '非 API' in data['message']

    def test_case_not_in_report_rejected(self):
        repo = _FakeRepo(cases=('other',))
        patches = _patch_raw_grpc([_Result(11, 5)], {})
        with patches[0], patches[1], patches[2]:
            data = _handler(repo).handle_get_case_dimension_raw_response(
                3, {'case_id': 'c1', 'dimension_id': 9})
        assert data['available'] is False
        assert '不属于' in data['message']

    def test_paginates_content(self):
        import json

        body = _big_body(0)
        item = {'test_result_id': 11, 'dimension_id': 9, 'round_number': None, 'api_raw_response': body}
        expected = json.dumps(body, ensure_ascii=False, default=str)
        repo = _FakeRepo()
        patches = _patch_raw_grpc([_Result(11, 5)], {11: [item]})
        with patches[0], patches[1], patches[2]:
            first = _handler(repo).handle_get_case_dimension_raw_response(
                3, {'case_id': 'c1', 'dimension_id': 9, 'offset': 0, 'limit': 17})
            second = _handler(repo).handle_get_case_dimension_raw_response(
                3, {'case_id': 'c1', 'dimension_id': 9, 'offset': 17, 'limit': 17})
        assert first['available'] is True
        assert first['content'] == expected[:17]
        assert len(first['content']) == 17
        assert first['has_more'] is True
        assert first['next_offset'] == 17
        assert second['offset'] == 17
        assert second['content'] == expected[17:34]
        assert first['total_chars'] == len(expected) == second['total_chars']

    def test_large_response_truncated_and_fast(self):
        body = _big_body(2 * 1024 * 1024)   # ~2MB 原始响应
        item = {'test_result_id': 11, 'dimension_id': 9, 'round_number': None, 'api_raw_response': body}
        repo = _FakeRepo()
        patches = _patch_raw_grpc([_Result(11, 5)], {11: [item]})
        with patches[0], patches[1], patches[2]:
            data = _handler(repo).handle_get_case_dimension_raw_response(
                3, {'case_id': 'c1', 'dimension_id': 9, 'limit': 1000})
        assert data['available'] is True
        assert len(data['content']) == 1000         # HTTP 载荷恒定单页大小
        assert data['total_chars'] > 1000000
        assert data['has_more'] is True
        assert data['elapsed_ms'] >= 0

    def test_limit_capped(self):
        item = {'test_result_id': 11, 'dimension_id': 9, 'round_number': None,
                'api_raw_response': {'a': 'y' * 10}}
        repo = _FakeRepo()
        patches = _patch_raw_grpc([_Result(11, 5)], {11: [item]})
        with patches[0], patches[1], patches[2]:
            data = _handler(repo).handle_get_case_dimension_raw_response(
                3, {'case_id': 'c1', 'dimension_id': 9, 'limit': 10 ** 9})
        assert data['limit'] == 200000

    def test_no_raw_response_stored(self):
        item = {'test_result_id': 11, 'dimension_id': 9, 'round_number': None, 'api_raw_response': None}
        repo = _FakeRepo()
        patches = _patch_raw_grpc([_Result(11, 5)], {11: [item]})
        with patches[0], patches[1], patches[2]:
            data = _handler(repo).handle_get_case_dimension_raw_response(
                3, {'case_id': 'c1', 'dimension_id': 9})
        assert data['available'] is False
        assert '未留存' in data['message']


class TestRawResponseRealClientContract:
    """真实 gRPC 客户端契约：_grpc_get_test_results_by_task_and_case 返回 list[dict]
    （report_service/infrastructure/clients/grpc_clients.py:129-135 经 _dto_to_dict），
    _grpc_get_dimension_by_ids 返回 {id_str: dict}（:170-176）。

    handler 必须按 dict 取字段；按对象属性取（getattr）会让真实 API 用例恒判为
    「非 API 用例」——INT-1752 实测（主库 task 598 / 结果 6952，api_id=285）。
    """

    _CASE = '8f5fe088-6a42-4dd2-a1dc-7972de135283'

    def _repo(self):
        return _FakeRepo(cases=(self._CASE,))

    def test_api_case_available_with_dict_results(self):
        import json
        raw = {'code': 0, 'data': {'result': {'errors': 1, 'length': 100}}}
        dict_results = [{'id': 11, 'api_id': 285, 'test_case_id': self._CASE}]
        dim_items = {11: [{'test_result_id': 11, 'dimension_id': 9, 'round_number': None,
                           'api_raw_response': raw}]}
        from report_service.infrastructure.clients import grpc_clients as gc
        with patch.object(gc, '_grpc_get_test_results_by_task_and_case', return_value=dict_results), \
             patch.object(gc, '_grpc_get_dimension_results_by_result_ids', return_value=dim_items), \
             patch.object(gc, '_grpc_get_dimension_by_ids', return_value={}):
            data = _handler(self._repo()).handle_get_case_dimension_raw_response(
                3, {'case_id': self._CASE, 'dimension_id': 9})
        assert data['available'] is True, data.get('message')
        assert json.loads(data['content']) == raw
        assert data['source_result_id'] == 11

    def test_dimension_name_resolved_from_dict_payload(self):
        raw = {'code': 0, 'data': {'result': {'errors': 1, 'length': 100}}}
        dict_results = [{'id': 11, 'api_id': 285, 'test_case_id': self._CASE}]
        dim_items = {11: [{'test_result_id': 11, 'dimension_id': 9, 'round_number': None,
                           'api_raw_response': raw}]}
        # 真实 _grpc_get_dimension_by_ids 返回 {dim_id_str: dict}
        from report_service.infrastructure.clients import grpc_clients as gc
        with patch.object(gc, '_grpc_get_test_results_by_task_and_case', return_value=dict_results), \
             patch.object(gc, '_grpc_get_dimension_results_by_result_ids', return_value=dim_items), \
             patch.object(gc, '_grpc_get_dimension_by_ids', return_value={'9': {'id': 9, 'name': 'WER'}}):
            data = _handler(self._repo()).handle_get_case_dimension_raw_response(
                3, {'case_id': self._CASE, 'dimension_id': 9})
        assert data.get('dimension_name') == 'WER'


# ---------------- 5. update_task_case_status 参数收敛 ----------------

def test_update_task_case_status_has_no_unused_test_type_param():
    from evaluation_service.infrastructure.persistence._result_status_mixin import ResultStatusMixin
    params = inspect.signature(ResultStatusMixin.update_task_case_status).parameters
    assert 'test_type' not in params
    assert list(params) == ['self', 'result_id', 'current_result_all_completed', 'task_id', 'test_case_id']


# ---------------- 6. api_gateway 路由层 ----------------

class _FakeStub:
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    def GetCaseDimensionRawResponse(self, req):
        self.calls.append(req)
        return self._resp


def _install_fake_stub(monkeypatch, resp):
    import api_gateway.application.services.report.report_query_sevice as gw_mod
    fake = _FakeStub(resp)
    monkeypatch.setattr(gw_mod, 'report_config_service', type('P', (), {'stub': fake})())
    return fake


def _make_gw_client(permissions):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api_gateway.routes.report_bp import router as report_router
    from api_gateway.middleware import RequestAdapterMiddleware

    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _inject_permissions(request, call_next):
        request.state.permissions = list(permissions)
        return await call_next(request)

    app.include_router(report_router, prefix='/api/v1/reports')
    return TestClient(app, raise_server_exceptions=False)


class TestGatewayRawResponseRoute:
    def test_route_forwards_paging_params(self, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb
        from shared.utils.grpc_json import dumps as grpc_dumps
        resp = report_pb.ReportConfigResponse(success=True, message='ok', data=grpc_dumps(
            {'available': True, 'content': '{"a":1}', 'total_chars': 7, 'has_more': False}))
        fake = _install_fake_stub(monkeypatch, resp)

        client = _make_gw_client(['report:read'])
        r = client.get(
            '/api/v1/reports/42/cases/C1/dimensions/9/raw-response',
            params={'offset': 5, 'limit': 100, 'round_number': 2})

        assert r.status_code == 200
        assert r.json()['data']['available'] is True
        req = fake.calls[0]
        assert (req.report_id, req.case_id, req.dimension_id) == (42, 'C1', 9)
        assert (req.offset, req.limit, req.round_number) == (5, 100, 2)

    def test_route_requires_report_read(self, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb
        _install_fake_stub(monkeypatch, report_pb.ReportConfigResponse(
            success=True, message='ok', data='{}'))
        client = _make_gw_client(['report:delete'])
        r = client.get('/api/v1/reports/42/cases/C1/dimensions/9/raw-response')
        assert r.status_code == 403


# ---------------- 7. report_service gRPC servicer ----------------

class TestReportServicerRawResponse:
    def test_servicer_wraps_handler_data(self):
        from shared.proto import report_service_pb2 as report_pb
        from shared.utils.grpc_json import loads as grpc_loads
        from report_service.interfaces.grpc.servicers import ReportServicer

        captured = {}

        class _H:
            def handle_get_case_dimension_raw_response(self, report_id, params):
                captured['report_id'] = report_id
                captured['params'] = params
                return {'available': True, 'content': '{}', 'total_chars': 2}

        servicer = ReportServicer()
        servicer._query_handler = _H()
        resp = servicer.GetCaseDimensionRawResponse(
            report_pb.GetCaseDimensionRawResponseRequest(
                report_id=5, case_id='c1', dimension_id=9, offset=10, limit=50, round_number=3))

        assert resp.success is True
        assert grpc_loads(resp.data, {})['content'] == '{}'
        assert captured == {'report_id': 5,
                            'params': {'case_id': 'c1', 'dimension_id': 9,
                                       'offset': 10, 'limit': 50, 'round_number': 3}}


# ---------------- 8. 对比报告：源任务解析 + 加权降级标注（终审 P2 返工） ----------------

class _Comparison:
    def __init__(self, task_ids):
        self.comparison_data = {'task_ids': list(task_ids)}


class _CompareAggregate:
    """对比报告聚合根：task_id 落 0（NULL 在实体层归一成 0）。"""

    def __init__(self, task_id=0):
        self.task_id = task_id


class _CompareRepo:
    def __init__(self, task_ids=(412, 390), with_matrix=True):
        self._comparison = _Comparison(task_ids) if with_matrix else None

    def get_by_id(self, report_id):
        return _CompareAggregate()

    def load_cases(self, report_id):
        return [_Case('c1')]

    def load_comparison(self, report_id):
        return self._comparison

    def load_summaries(self, report_id):
        return []


class TestComparisonReportRawResponse:
    """P2-1：对比报告 task_id=0，源任务只在对比矩阵里。"""

    def test_resolves_source_tasks_from_comparison_matrix(self):
        captured = {}
        raw = {'code': 0, 'data': {'result': {'errors': 1, 'length': 100}}}

        def _fake_results(case_ids, task_ids):
            captured['task_ids'] = task_ids
            return [{'id': 11, 'api_id': 285, 'test_case_id': 'c1'}]

        dim_items = {11: [{'test_result_id': 11, 'dimension_id': 9,
                           'round_number': None, 'api_raw_response': raw}]}
        from report_service.infrastructure.clients import grpc_clients as gc
        with patch.object(gc, '_grpc_get_test_results_by_task_and_case', side_effect=_fake_results), \
             patch.object(gc, '_grpc_get_dimension_results_by_result_ids', return_value=dim_items), \
             patch.object(gc, '_grpc_get_dimension_by_ids', return_value={}):
            data = _handler(_CompareRepo(task_ids=(412, 390))).handle_get_case_dimension_raw_response(
                567, {'case_id': 'c1', 'dimension_id': 9})

        assert captured['task_ids'] == [412, 390]      # 不是 [0]
        assert data['available'] is True, data.get('message')
        assert data['source_result_id'] == 11

    def test_task_id_zero_is_not_queried_as_real_task(self):
        captured = {}

        def _fake_results(case_ids, task_ids):
            captured['task_ids'] = task_ids
            return []

        from report_service.infrastructure.clients import grpc_clients as gc
        with patch.object(gc, '_grpc_get_test_results_by_task_and_case', side_effect=_fake_results):
            data = _handler(_CompareRepo(with_matrix=False)).handle_get_case_dimension_raw_response(
                567, {'case_id': 'c1', 'dimension_id': 9})

        assert 'task_ids' not in captured             # 0 视为未关联，不发无意义查询
        assert data['available'] is False
        assert '未关联任务' in data['message']


def _compare_task():
    return {'id': 412, 'name': 'T412', 'status': TaskStatus.COMPLETED.value,
            'total_cases': 2, 'completed_cases': 2, 'failed_cases': 0}


def _patch_compare_helpers():
    """屏蔽对比 / 二次对比链的 gRPC 辅助，只保留 core_metrics 的真实计算。"""
    from report_service.application.services.report_compare_helpers import ReportCompareHelpers
    from report_service.application.services.report_utils import ReportUtils
    import report_service.application.services.report_compare_generator_data_mixin as compare_mod
    import report_service.application.services.report_helpers as report_helpers_mod

    return [
        patch.object(ReportCompareHelpers, '_calculate_task_weighted_values', return_value={}),
        patch.object(ReportCompareHelpers, '_collect_resources_batch',
                     return_value=({'DevA'}, [{'id': 1, 'name': 'DevA'}], [])),
        patch.object(ReportCompareHelpers, '_build_case_data_compare', return_value=[]),
        patch.object(ReportCompareHelpers, '_get_source_cases', return_value=[]),
        patch.object(ReportCompareHelpers, '_build_comparison_matrix', return_value={}),
        patch.object(ReportUtils, 'build_resource_headers', return_value=[]),
        patch.object(ReportUtils, 'calculate_device_api_stats', return_value=({}, {})),
        patch.object(compare_mod, '_grpc_list_testcases_by_ids',
                     return_value={'101': {'group': {'id': 1, 'name': 'g1'}, 'tags': []},
                                   '102': {'group': {'id': 1, 'name': 'g1'}, 'tags': []}}),
        # 对比链 dim_results_map=None → extract_dimension_values 走 gRPC 兜底，
        # 用带维度值但不带原始响应的映射替代真实网络调用。
        patch.object(report_helpers_mod, '_grpc_get_dim_results',
                     side_effect=lambda ids: {rid: _dim_results_map(with_raw=False).get(rid, [])
                                              for rid in ids}),
    ]


def _patch_secondary_helpers(all_dimensions, all_metrics, batch):
    from report_service.application.services.report_compare_helpers import ReportCompareHelpers
    from report_service.application.services.report_data_builder import ReportDataBuilder

    return _patch_compare_helpers() + [
        patch.object(ReportCompareHelpers, '_collect_all_resources',
                     return_value=(_results(), ['DevA'], [], [], [1], [], None)),
        patch.object(ReportCompareHelpers, '_build_all_dimensions',
                     return_value=(all_dimensions, all_metrics, None)),
        patch.object(ReportDataBuilder, '_get_dimension_results_batch', side_effect=batch),
        patch.object(ReportDataBuilder, '_get_task_test_cases', return_value=([], [])),
        patch.object(ReportCompareHelpers, '_get_source_cases_from_reports', return_value=[{'name': 'c1'}]),
        patch.object(ReportCompareHelpers, '_build_comparison_matrix_secondary', return_value={}),
    ]


def _compare_metric(data_dict, name):
    return next(m for m in data_dict['all_metrics'] if m.get('name') == name)


class TestComparisonChainDegradationMarking:
    """P2-2：对比链不得静默降级，all_metrics 必须带降级标。"""

    def test_compare_chain_marks_weighted_degradation(self):
        from report_service.application.services.report_compare_generator_data_mixin import (
            ReportCompareDataMixin,
        )
        from report_service.application.services.report_compare_helpers import ReportCompareHelpers
        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in _patch_compare_helpers() + [
                patch.object(ReportCompareHelpers, '_get_all_dimensions_with_results', return_value=_dims()),
            ] + _patch_grpc():
                stack.enter_context(p)
            data_dict, error = ReportCompareDataMixin._prepare_compare_data(
                [_compare_task()], [412], _results())

        assert error is None
        wer = _compare_metric(data_dict, 'WER')
        # 对比链无维度结果映射 → 加权必然降级，但必须标注（不再静默）
        assert wer['aggregation_degraded'] is True
        assert wer['degradation_reason'] == 'missing_api_raw_response'
        assert wer['applied_method'] == 'average'
        assert 'aggregation_degraded' not in _compare_metric(data_dict, '准确率')

    def test_secondary_chain_requests_raw_body_when_weighted_dimension(self):
        from report_service.application.services.report_compare_generator_secondary_mixin import (
            ReportSecondaryDataMixin,
        )
        from contextlib import ExitStack

        captured = {}

        def _fake_batch(result_ids, include_body=False):
            captured['include_body'] = include_body
            return _dim_results_map(with_raw=False), {}

        metrics = [{'id': 1, 'name': '准确率'}, {'id': 9, 'name': 'WER'}]
        with ExitStack() as stack:
            for p in _patch_secondary_helpers(_dims(), metrics, _fake_batch) + _patch_grpc():
                stack.enter_context(p)
            data_dict, error = ReportSecondaryDataMixin._prepare_secondary_data(
                [1, 2], [], [_compare_task()], [412])

        assert error is None
        assert captured['include_body'] is True
        # 原始响应缺失 → 加权降级并打标
        wer = _compare_metric(data_dict, 'WER')
        assert wer['aggregation_degraded'] is True
        assert wer['degradation_reason'] == 'missing_api_raw_response'

    def test_secondary_chain_skips_raw_body_without_weighted_dimension(self):
        from report_service.application.services.report_compare_generator_secondary_mixin import (
            ReportSecondaryDataMixin,
        )
        from contextlib import ExitStack

        captured = {}

        def _fake_batch(result_ids, include_body=False):
            captured['include_body'] = include_body
            return {}, {}

        avg_only = [{'id': 1, 'name': '准确率', 'statistic_method': 'average',
                     'agg_denominator': 'case', 'exclude_rounds': []}]
        with ExitStack() as stack:
            for p in _patch_secondary_helpers(avg_only, [{'id': 1, 'name': '准确率'}],
                                              _fake_batch) + _patch_grpc():
                stack.enter_context(p)
            data_dict, error = ReportSecondaryDataMixin._prepare_secondary_data(
                [1, 2], [], [_compare_task()], [412])

        assert error is None
        assert captured['include_body'] is False       # 无加权维度时载荷不变
        assert all('aggregation_degraded' not in m for m in data_dict['all_metrics'])

