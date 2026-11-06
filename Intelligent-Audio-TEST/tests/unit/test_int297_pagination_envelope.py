# -*- coding: utf-8 -*-
"""INT-297 专项：列表接口分页信封统一（{items, page, pages, per_page, total}）。

背景：INT-261 全站 UX 审计发现列表信封 4 种形态并存——
1. {items, page, pages, per_page, total}（多数）
2. {items, page, page_size}（/reports 缺 total 与 pages，HistoryReports 无法显示总数）
3. {items, total}（tags / 评估分类 / 设备状态等）
4. {data, total}、{parameters, total}、{mappings, total}（algorithm 系列）

本文件按信封唯一性口径锁定（不改分页语义，只锁响应组装）：

- report_service ListReports（gRPC + HTTP）返回完整五字段（最小必须修复项）
- report_service 用例列表/搜索 perPage → per_page 归一
- task_service tag_crud 列表（分类/标签/标签名/按分类分组）返回五字段
- task_service algorithm 系列（定义/分组/参数/用例参数/参考参数/映射）返回五字段
- evaluation_service 分类列表、device_service 状态/校准历史/按设备列表返回五字段
- auth_service ListUsers 列表键 items（原 users）
- 网关组装层（tags / 评估分类 / 用户 / 音频标签 / 日志）透出统一信封
- report_service 仓储 count_reports 与 list_reports 过滤口径一致

DB：进程级 SQLite（tests/conftest.py 注入），报告相关用例按需 create_all，
用例内自行清理，对齐 test_int219 / test_int262 口径。
"""
import os
import sys

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)
from shared.utils.grpc_json import loads as grpc_loads, dumps as grpc_dumps

# 统一信封五字段（形态 1）
ENVELOPE_KEYS = {'items', 'page', 'pages', 'per_page', 'total'}


def _assert_envelope(data):
    """断言 data 为统一分页信封（五字段齐全、类型正确、非空集时页计算一致）。"""
    assert isinstance(data, dict), f'信封非 dict: {type(data)}'
    missing = ENVELOPE_KEYS - set(data.keys())
    assert not missing, f'信封缺字段: {missing}，实际: {sorted(data.keys())}'
    assert isinstance(data['items'], list)
    for key in ('page', 'pages', 'per_page', 'total'):
        assert isinstance(data[key], int), f'{key} 非整数: {data[key]!r}'
    if data['total'] > 0 and data['per_page'] > 0:
        assert data['pages'] == (data['total'] + data['per_page'] - 1) // data['per_page'], \
            f'pages 计算不一致: pages={data["pages"]} total={data["total"]} per_page={data["per_page"]}'


# =====================================================================
# report_service：/reports 最小必须修复项（total + pages）
# =====================================================================

_REPORT_TABLES = None


def _ensure_report_tables():
    init_db(pool_size=2)
    global _REPORT_TABLES
    if _REPORT_TABLES is None:
        from report_service.infrastructure.persistence.models import (
            Report, ReportSummary, ReportSummaryMeta, ReportRawData,
            ReportCase, ReportMetricStats, ReportComparisonMatrix, ReportFavorite,
        )
        _REPORT_TABLES = [t.__table__ for t in (
            Report, ReportSummary, ReportSummaryMeta, ReportRawData,
            ReportCase, ReportMetricStats, ReportComparisonMatrix, ReportFavorite,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_REPORT_TABLES)
    return _REPORT_TABLES


def _cleanup_tables(tables):
    session = get_db_session()
    try:
        for table in tables:
            session.execute(table.delete())
        session.commit()
    finally:
        remove_db_session()


def _make_reports(n, name_prefix='INT297_报告', base_task_id=2900):
    from report_service.infrastructure.persistence.models import Report
    ids = []
    session = get_db_session()
    try:
        for i in range(n):
            po = Report(name=f'{name_prefix}_{i}', type='task', status='completed',
                        task_id=base_task_id + i)
            session.add(po)
            session.flush()
            ids.append(po.id)
        session.commit()
        return ids
    finally:
        remove_db_session()


class TestReportListEnvelope:
    """report_service /reports 信封统一（最小必须：total + pages）。"""

    def setup_method(self):
        _ensure_report_tables()

    def teardown_method(self):
        _cleanup_tables(_REPORT_TABLES)

    def test_grpc_list_reports_full_envelope(self):
        """gRPC ListReports 返回 {items, page, pages, per_page, total}。"""
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        _make_reports(5)

        resp = ReportServicer().ListReports(
            report_pb.ListReportsRequest(page=1, per_page=3), context=None)
        assert resp.success is True
        data = grpc_loads(resp.data, {}) or {}
        _assert_envelope(data)
        assert data['total'] == 5
        assert data['page'] == 1
        assert data['per_page'] == 3
        assert data['pages'] == 2
        assert len(data['items']) == 3

    def test_grpc_list_reports_task_filter_count_matches(self):
        """task_id 过滤下 total/pages 与过滤后集合一致（INT-262 口径不回归）。"""
        from shared.proto import report_service_pb2 as report_pb
        from report_service.interfaces.grpc.servicers import ReportServicer

        _make_reports(3, name_prefix='INT297_T601')
        _make_reports(1, name_prefix='INT297_T602')

        resp = ReportServicer().ListReports(
            report_pb.ListReportsRequest(page=1, per_page=2, task_id=2902), context=None)
        data = grpc_loads(resp.data, {}) or {}
        _assert_envelope(data)
        assert data['total'] == 1
        assert data['pages'] == 1
        assert {i['task_id'] for i in data['items']} == {2902}

    def test_http_route_list_reports_full_envelope(self):
        """report_service HTTP 路由 list_reports 同样返回五字段信封。"""
        from report_service.interfaces.api.routes import list_reports

        _make_reports(2, name_prefix='INT297_HTTP')

        resp = list_reports(status=None, task_id=None, page=1, page_size=1)
        assert resp['success'] is True
        data = resp['data']
        _assert_envelope(data)
        assert data['per_page'] == 1
        assert data['total'] >= 2
        assert data['pages'] == data['total']

    def test_repo_count_reports_matches_list_filters(self):
        """仓储 count_reports 与 list_reports 过滤口径一致。"""
        from report_service.infrastructure.persistence.report_repository import (
            report_repository,
        )

        _make_reports(4, name_prefix='INT297_CNT')          # task_id 2900..2903
        _make_reports(1, name_prefix='INT297_CNT_T601', base_task_id=2904)
        # task_id 过滤
        total = report_repository.count_reports(task_id=2904)
        listed = report_repository.list_reports(task_id=2904, page=1, page_size=10)
        assert total == len(listed) == 1
        # 无过滤总数 = 列表全量页大小之外的口径：count ≥ 列表任一页大小
        assert report_repository.count_reports() >= 5
        assert report_repository.count_reports() >= len(
            report_repository.list_reports(page=1, page_size=2))

    def test_report_cases_envelope_per_page_key(self):
        """报告用例列表/搜索 perPage 归一为 per_page。"""
        from report_service.application.handlers.report_handlers import ReportQueryHandler

        handler = ReportQueryHandler()
        empty = handler._empty_paged_response()
        _assert_envelope(empty)
        assert 'perPage' not in empty


# =====================================================================
# task_service：tags / algorithm 系列
# =====================================================================

class _FakePagination:
    """query.paginate() 返回的 _Pagination 同构桩。"""

    def __init__(self, items, total, page=1, per_page=20):
        self.items = items
        self.total = total
        self.page = page
        self.per_page = per_page

    @property
    def pages(self):
        return (self.total + self.per_page - 1) // self.per_page if self.per_page else 0


class _FakeTagRepo:
    """tag_crud_service 读侧桩：只提供列表查询。"""

    def list_tag_categories_paginated(self, page, per_page, keyword=None):
        cat = SimpleNamespace(id=1, name='声学', description=None,
                              color=None, sort_order=0,
                              created_at=None, updated_at=None)
        return _FakePagination([(cat, 3)], total=11, page=page, per_page=per_page)

    def list_tags_paginated_with_filter(self, page, per_page, category_id=None, keyword=None):
        return _FakePagination([SimpleNamespace(id=2, name='清晰度', description=None,
                                                color=None, category_id=1, category=None,
                                                created_at=None, updated_at=None)],
                               total=25, page=page, per_page=per_page)

    def list_tag_names_paginated(self, page, per_page, keyword=None):
        return _FakePagination([SimpleNamespace(name='tag_a'), SimpleNamespace(name='tag_b')],
                               total=9, page=page, per_page=per_page)

    def get_category_name_map(self, cat_ids):
        return {1: '声学'}

    def get_category_name_by_id(self, category_id):
        return '声学'

    def list_tag_categories_ordered(self):
        return []

    def list_all_tags_ordered_by_name(self):
        return []


class TestTagListEnvelope:
    """task_service tag_crud 列表信封统一（形态 3 → 形态 1）。"""

    def _svc(self):
        from task_service.application.testcase.tag_crud_service import TagCrudService
        return TagCrudService(repo=_FakeTagRepo())

    def test_list_categories_envelope(self):
        data = self._svc().list_categories(page=2, per_page=20).get('data')
        _assert_envelope(data)
        assert data['total'] == 11 and data['page'] == 2 and data['pages'] == 1

    def test_list_tags_envelope(self):
        data = self._svc().list_tags(page=3, per_page=10).get('data')
        _assert_envelope(data)
        assert data['total'] == 25 and data['page'] == 3 and data['per_page'] == 10

    def test_list_tag_names_envelope(self):
        data = self._svc().list_tag_names(page=1, per_page=100).get('data')
        _assert_envelope(data)
        assert data['items'] == ['tag_a', 'tag_b'] and data['total'] == 9

    def test_get_testcase_tags_envelope(self):
        """testcase 标签名列表（原 {items} 无 total）补齐五字段。"""
        from task_service.application.testcase.testcase_query_service import TestCaseQueryService

        svc = TestCaseQueryService.__new__(TestCaseQueryService)
        svc.repo = SimpleNamespace(
            list_tags_ordered_by_updated_at=lambda: [SimpleNamespace(name='x'), SimpleNamespace(name='y')])
        data = svc.get_testcase_tags().get('data')
        _assert_envelope(data)
        assert data['items'] == ['x', 'y'] and data['total'] == 2


class _FakeAlgoRepo:
    """algorithm 系列读侧桩（真实 DTO dataclass，序列化走 asdict 分支）。"""

    def _def(self, algo_type):
        from task_service.domain.dto.task_acl_dto import AlgorithmDefinitionDTO
        return AlgorithmDefinitionDTO(id=1, type=algo_type, name='语音理解',
                                      group_id=1, group_name='默认组',
                                      description=None, status='online',
                                      icon=None, display_order=0)

    def find_algorithm_by_type(self, algo_type):
        return self._def(algo_type)

    def list_device_params(self, algorithm_type=None):
        from task_service.domain.dto.task_acl_dto import DeviceParamDTO
        return [DeviceParamDTO(id=1, algorithm_type=algorithm_type,
                               param_code='c', param_name='n', param_type='text',
                               direction='input', required=False)]

    def list_api_params(self, algorithm_type=None):
        from task_service.domain.dto.task_acl_dto import ApiParamDTO
        return [ApiParamDTO(id=2, algorithm_type=algorithm_type,
                            param_code='a', param_name='n', param_type='text',
                            direction='output', required=False)]

    def list_case_params(self, algorithm_type=None, scope=None):
        from task_service.domain.dto.task_acl_dto import CaseParamDTO
        return [CaseParamDTO(id=1, algorithm_type=algorithm_type),
                CaseParamDTO(id=2, algorithm_type=algorithm_type)]

    def list_reference_params(self, algorithm_type=None):
        from task_service.domain.dto.task_acl_dto import ReferenceParamDTO
        return [ReferenceParamDTO(id=1, algorithm_type=algorithm_type)]

    def list_mappings(self, algorithm_type=None, source_type=None, dimension_id=None):
        from task_service.domain.dto.task_acl_dto import ParamMappingDTO
        return [ParamMappingDTO(id=1, algorithm_type='voice_llm', source='ref',
                                source_param='text', source_direction='input',
                                dimension_id=1, target_param='x', transform_type='none')]

    def list_dimension_relations(self, algo_type):
        from task_service.domain.dto.task_acl_dto import DimensionRelationDTO
        return [DimensionRelationDTO(id=1, algorithm_type=algo_type, dimension_id=1)]

    def list_dimension_names_map_by_ids(self, ids):
        return {1: 'WER'}

    def list_algorithm_definitions(self, status=None, group_id=None):
        return [self._def('voice_llm'), self._def('tts')]

    def count_algorithms_in_group_for_group(self, group):
        return 0


class TestAlgorithmListEnvelope:
    """task_service algorithm 系列信封统一（形态 4 → 形态 1）。"""

    def test_list_algorithms_envelope(self):
        from task_service.application.algorithm.algorithm_crud_service import AlgorithmCrudService

        svc = AlgorithmCrudService.__new__(AlgorithmCrudService)
        svc.repo = _FakeAlgoRepo()
        data = svc.list_algorithms().get('data')
        _assert_envelope(data)
        assert data['total'] == 2
        assert {a['type'] for a in data['items']} == {'voice_llm', 'tts'}

    def test_list_groups_envelope(self):
        from task_service.application.algorithm.algorithm_group_crud_service import AlgorithmGroupCrudService

        svc = AlgorithmGroupCrudService.__new__(AlgorithmGroupCrudService)
        svc.repo = SimpleNamespace(
            list_groups=lambda: [{'id': 1, 'name': '默认组', 'description': None,
                                  'icon': None, 'display_order': 0,
                                  'created_at': None, 'updated_at': None}],
            count_algorithms_in_group_for_group=lambda g: 0,
        )
        data = svc.list_groups().get('data')
        _assert_envelope(data)
        assert data['total'] == 1

    def test_list_params_envelope(self):
        from task_service.application.algorithm.algorithm_param_query_service import AlgorithmParamQueryService

        svc = AlgorithmParamQueryService.__new__(AlgorithmParamQueryService)
        svc.repo = _FakeAlgoRepo()
        data = svc.list_params(algorithm_type='voice_llm').get('data')
        _assert_envelope(data)
        assert 'parameters' not in data  # 旧键不再出现

    def test_list_case_params_envelope(self):
        from task_service.application.algorithm.algorithm_param_query_service import AlgorithmParamQueryService

        svc = AlgorithmParamQueryService.__new__(AlgorithmParamQueryService)
        svc.repo = _FakeAlgoRepo()
        data = svc.list_case_params(algorithm_type='voice_llm').get('data')
        _assert_envelope(data)
        assert data['total'] == 2

    def test_list_reference_params_envelope(self):
        from task_service.application.algorithm.algorithm_param_query_service import AlgorithmParamQueryService

        svc = AlgorithmParamQueryService.__new__(AlgorithmParamQueryService)
        svc.repo = _FakeAlgoRepo()
        data = svc.list_reference_params(algorithm_type='voice_llm').get('data')
        _assert_envelope(data)
        assert 'parameters' not in data

    def test_list_mappings_envelope(self):
        from task_service.application.algorithm.algorithm_param_query_service import AlgorithmParamQueryService

        svc = AlgorithmParamQueryService.__new__(AlgorithmParamQueryService)
        svc.repo = _FakeAlgoRepo()
        data = svc.list_mappings(algorithm_type='voice_llm').get('data')
        _assert_envelope(data)
        assert 'mappings' not in data
        assert data['items'][0]['dimension_name'] == 'WER'


# =====================================================================
# evaluation / device / auth / benchmark：无分页语义列表补齐五字段
# =====================================================================

class TestUnpagedListEnvelope:
    """无分页语义列表（单页全量）补齐 page=1 / pages=1 / per_page=total。"""

    def test_evaluation_categories_envelope(self):
        """evaluation_service 分类列表（原 {items, total}）补齐五字段。"""
        from evaluation_service.application.queries.evaluation_query_service import EvaluationQueryService

        created = SimpleNamespace(isoformat=lambda: '2026-10-13T00:00:00')
        cat = SimpleNamespace(id=1, name='准确率', description=None, icon=None,
                              created_at=created, updated_at=created)
        svc = EvaluationQueryService.__new__(EvaluationQueryService)
        svc.repo = SimpleNamespace(list_categories=lambda: [cat])
        data = svc.list_categories().get('data')
        _assert_envelope(data)
        assert data['total'] == 1 and data['pages'] == 1

    def test_device_statuses_envelope(self):
        from device_service.application.queries.device_query_service import DeviceQueryService

        svc = DeviceQueryService.__new__(DeviceQueryService)
        svc.repo = SimpleNamespace(get_device_statuses=lambda ids: [{'id': 1}])
        data = svc.get_statuses([1]).get('data')
        _assert_envelope(data)
        assert data['total'] == 1

    def test_spl_history_envelope(self):
        from device_service.application.queries.spl_query_service import SPLQueryService

        svc = SPLQueryService.__new__(SPLQueryService)
        svc.repo = SimpleNamespace(
            get_calibration_history=lambda mid: [{'id': 1}, {'id': 2}],
            get_spl_mapping=lambda mid: SimpleNamespace(id=mid, deleted=False),
            get_spl_by_device=lambda did: [{'id': 1}],
        )
        data = svc.get_history(7).get('data')
        _assert_envelope(data)
        assert data['total'] == 2 and data['pages'] == 1

    def test_spl_by_device_envelope(self):
        from device_service.application.queries.spl_query_service import SPLQueryService

        svc = SPLQueryService.__new__(SPLQueryService)
        svc.repo = SimpleNamespace(get_spl_by_device=lambda did: [{'id': 1}])
        data = svc.get_by_device(5).get('data')
        _assert_envelope(data)

    def test_benchmark_ranking_envelope(self):
        from report_service.application.handlers.benchmark_handlers import BenchmarkQueryHandler

        handler = BenchmarkQueryHandler(repo=SimpleNamespace(
            query_rankings=lambda f: [{'id': 1}, {'id': 2}, {'id': 3}]))
        from report_service.application.queries.benchmark_queries import GetBenchmarkRankingQuery
        data = handler.handle_get_ranking(GetBenchmarkRankingQuery()).get('data')
        _assert_envelope(data)
        assert data['total'] == 3

    def test_auth_list_users_envelope(self):
        """auth_service ListUsers：items 键 + 五字段（原 {total, users}）。"""
        import json
        from auth_service.interfaces.grpc.servicers import AuthServicer

        from auth_service.domain.entities.user import UserAggregate

        class _FakeQueryHandler:
            def handle_list_users(self, q):
                user = UserAggregate(id=1, username='u1', email='u1@x.com',
                                     role_id=1, status='active', role_name='admin')
                return (7, [user])

        servicer = AuthServicer.__new__(AuthServicer)
        servicer._query_handler = _FakeQueryHandler()
        from shared.proto import auth_service_pb2 as auth_pb
        resp = servicer.ListUsers(auth_pb.ListUsersRequest(page=2, page_size=3))
        assert resp.success is True
        data = json.loads(resp.data)
        _assert_envelope(data)
        assert data['total'] == 7 and data['page'] == 2 and data['per_page'] == 3
        assert data['pages'] == 3
        assert 'users' not in data

    def test_rms_spl_by_api_envelope(self):
        from api_test_service.application.api_rms_spl_config_service import ApiRmsSplConfigService

        mapping = SimpleNamespace(
            id=1, api_id=9, name='m', vendor='v', protocol='http',
            reference_spl=94.0, reference_gain_linear=1.0,
            min_gain_linear=0.0, max_gain_linear=2.0,
            calibration_status='calibrated',
            calibration_points=[SimpleNamespace(target_spl=94.0, gain_linear=1.0,
                                                rms_dbfs=-20.0)],
            is_calibrated=lambda: True)
        svc = ApiRmsSplConfigService(repository=SimpleNamespace(
            list_by_api=lambda api_id: [mapping]))
        data = svc.get_by_api(9).get('data')
        _assert_envelope(data)


# =====================================================================
# 网关组装层：tags / 评估分类 / 用户列表
# =====================================================================

class TestGatewayAssemblyEnvelope:
    """网关 BFF 组装层透出统一信封（ACL 结果 → schema → 前端零感知）。"""

    @staticmethod
    def _result(items, total, **extra):
        payload = {'items': items, 'total': total}
        payload.update(extra)
        return {'success': True, 'message': '', 'data': payload}

    def test_gateway_tag_categories_envelope(self, monkeypatch):
        from api_gateway.application.services import tag as tag_module
        from api_gateway.application.services.tag import tag_query_service

        monkeypatch.setattr(tag_query_service, '_tag_acl',
                            SimpleNamespace(list_categories=lambda **kw: self._result(
                                [], 11, page=2, per_page=20, pages=1)))
        resp = tag_query_service.TagCategoryQueryService.get_all()
        body, _code = resp
        _assert_envelope(body['data'])

    def test_gateway_tag_names_envelope(self, monkeypatch):
        from api_gateway.application.services.tag import tag_query_service

        monkeypatch.setattr(tag_query_service, '_tag_acl',
                            SimpleNamespace(list_tag_names=lambda **kw: self._result(
                                ['a', 'b'], 9, page=1, per_page=100, pages=1)))
        resp = tag_query_service.TagQueryService.get_all_names()
        body, _code = resp
        _assert_envelope(body['data'])
        assert body['data']['items'] == ['a', 'b']

    def test_gateway_evaluation_categories_envelope(self, monkeypatch):
        from api_gateway.application.services.evaluation import evaluation_query_service as eqs

        monkeypatch.setattr(eqs, '_evaluation_acl',
                            SimpleNamespace(list_categories=lambda: self._result(
                                [{'id': 1, 'name': '准确率', 'description': None,
                                  'icon': None, 'created_at': None, 'updated_at': None}],
                                1, page=1, per_page=1, pages=1)))
        resp = eqs.EvaluationQueryService.get_categories()
        body, _code = resp
        _assert_envelope(body['data'])

    def test_gateway_user_list_envelope(self, monkeypatch):
        """网关用户列表：users 键 → items 键 + 五字段。"""
        from api_gateway.application.services.auth import user_management_service as ums

        monkeypatch.setattr(ums, 'call_auth_rpc', lambda name, req, default_error='': (
            {'items': [{'id': 1, 'username': 'u1'}], 'total': 7,
             'page': req.page, 'per_page': req.page_size, 'pages': 3}, None))
        from api_gateway.infrastructure import request_adapter
        monkeypatch.setattr(request_adapter, 'request',
                            SimpleNamespace(args=SimpleNamespace(
                                get=lambda k, d=None: {'page': '2', 'page_size': '3'}.get(k, d))))
        body, _code = ums.UserManagementService.list_users()
        _assert_envelope(body['data'])
        assert 'users' not in body['data']
        assert body['data']['total'] == 7

    def test_gateway_audio_tags_envelope(self, monkeypatch):
        from api_gateway.application.services.audio import audio_query_service as aqs

        monkeypatch.setattr(aqs, '_audio_acl',
                            SimpleNamespace(get_all_tags=lambda: self._result(['m', 'f'], 2)))
        resp = aqs.AudioQueryService.get_all_tags()
        body, _code = resp
        _assert_envelope(body['data'])
        assert body['data']['items'] == ['m', 'f'] and body['data']['total'] == 2

    def test_gateway_logs_envelope_uses_upstream_pages(self, monkeypatch):
        """网关日志列表读取上游 pages（task_service log_repository 已补齐）。"""
        from api_gateway.application.services.log import log_query_service as lqs
        from api_gateway.schemas.log import LogListQuery

        upstream = {'items': [{'id': 1, 'time': '', 'level': 'INFO', 'category': '',
                               'module': '', 'source': '', 'content': ''}], 'total': 21,
                    'page': 2, 'per_page': 10, 'pages': 3}

        class _FakeProxy:
            @staticmethod
            def list_logs(**kw):
                return upstream

        monkeypatch.setitem(sys.modules, 'api_gateway.infrastructure.grpc_proxies',
                            SimpleNamespace(task_data_service=_FakeProxy()))
        monkeypatch.setattr(lqs, '_parse_query_params',
                            lambda cls: LogListQuery.model_validate({'page': 2, 'per_page': 10}))
        resp = lqs.LogQueryService.get_logs()
        body, _code = resp
        _assert_envelope(body['data'])
        assert body['data']['pages'] == 3 and body['data']['page'] == 2


# =====================================================================
# task_service 日志仓储：pages 字段
# =====================================================================

_LOG_TABLES = None


def _ensure_log_tables():
    init_db(pool_size=2)
    global _LOG_TABLES
    if _LOG_TABLES is None:
        from task_service.infrastructure.persistence.models.system_models import Log
        _LOG_TABLES = [Log.__table__]
        Base.metadata.create_all(bind=get_engine(), tables=_LOG_TABLES)
    return _LOG_TABLES


class TestLogRepoEnvelope:
    """task_service log_repository.list_logs 补 pages（原 {items,total,page,per_page}）。"""

    def setup_method(self):
        _ensure_log_tables()

    def teardown_method(self):
        _cleanup_tables(_LOG_TABLES)

    def test_list_logs_envelope(self):
        from task_service.infrastructure.persistence.log_repository import log_repository

        session = get_db_session()
        try:
            from task_service.infrastructure.persistence.models.system_models import Log
            from datetime import datetime
            for i in range(3):
                session.add(Log(time=datetime(2026, 10, 13, 10, 0, 0), level='INFO',
                                category='System', module='m', source='t',
                                content=f'INT297 log {i}'))
            session.commit()
        finally:
            remove_db_session()

        resp = log_repository.list_logs(page=1, per_page=2)
        _assert_envelope(resp)
        assert resp['total'] == 3 and resp['pages'] == 2
