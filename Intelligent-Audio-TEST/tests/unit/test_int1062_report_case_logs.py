# -*- coding: utf-8 -*-
"""INT-1062 专项：报告具体用例日志文件列表端点 + 下载 ?files= 筛选。

覆盖三层（对齐 test_int971_report_share.py 先例）：
- report_service ReportStatsQueryMixin：handle_list_case_logs 枚举逻辑名、
  handle_download_case_logs 按 files 筛选打包（命名一致性/整包兼容/缺文件 404）
- report_service gRPC servicer：ListCaseLogs / DownloadCaseLogs（files 透传 + code 透出）
- api_gateway：GET /reports/{id}/cases/{cid}/logs 列表路由 + GET .../logs/download
  ?files= 编解码 + RBAC（列表 report:read / 下载 report:download_log）

存储 monkeypatch 对齐 test_int408_report_cherry_resolution.py:315 先例
（list_objects_with_meta / load_bytes）；业务日志 reader 直接 monkeypatch
BusinessLogReader 类方法，不依赖本地日志目录。
"""
import base64
import io
import os
import zipfile
from datetime import datetime, timezone

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.utils.grpc_json import loads as grpc_loads, dumps as grpc_dumps

TASK_ID = 7001
CASE_ID = 'ACC1062-C1'


class _Agg:
    task_id = TASK_ID


class _Repo:
    def get_by_id(self, report_id):
        return _Agg()


def _make_test_result(include_params=True):
    data = {}
    if include_params:
        data['adjusted_reference_params'] = {'ref': 'x', 'threshold': 0.5}
    return {
        'id': 101,
        'task_id': TASK_ID,
        'test_case_id': CASE_ID,
        'device_id': 7,
        'result_data': data,
        'result_data_path': None,
    }


def _make_mixin(monkeypatch, test_result=None, source_task_ids=None):
    """构建 ReportStatsQueryMixin，gRPC 结果/合并解析全部 monkeypatch。"""
    from report_service.application.handlers._report_stats_query_mixin import (
        ReportStatsQueryMixin,
    )
    import report_service.infrastructure.clients.grpc_clients as grpc_clients
    import report_service.application.services.task_result_resolver as resolver

    tr = test_result if test_result is not None else _make_test_result()
    monkeypatch.setattr(grpc_clients, '_grpc_get_test_results_by_task_ids',
                        lambda ids: [tr])
    monkeypatch.setattr(resolver, 'resolve_cherry_pick_sources', lambda tid: None)
    if source_task_ids:
        monkeypatch.setattr(resolver, 'resolve_merge_source_task_ids',
                            lambda tid: list(source_task_ids))
    else:
        monkeypatch.setattr(resolver, 'resolve_merge_source_task_ids', lambda tid: [])

    m = ReportStatsQueryMixin.__new__(ReportStatsQueryMixin)
    m.repository = _Repo()
    return m


def _install_storage(monkeypatch, case_metas=None):
    """mock storage.list_objects_with_meta / load_bytes（对齐 INT-408 先例）。"""
    from shared.infrastructure import storage as storage_mod
    case_metas = case_metas or []
    monkeypatch.setattr(storage_mod.storage, 'list_objects_with_meta',
                        lambda category, prefix='': list(case_metas))
    monkeypatch.setattr(storage_mod.storage, 'load_bytes',
                        lambda path: b'CASE-DATA')
    return storage_mod


def _install_business_logs(monkeypatch, metas=None, contents=None):
    """mock BusinessLogReader 列表/打包两方法（避免依赖本地日志目录）。"""
    from shared.logging import business_reader
    metas = metas or []
    contents = contents or []
    monkeypatch.setattr(business_reader.BusinessLogReader, 'list_log_files_with_meta',
                        lambda self, **kw: list(metas))
    monkeypatch.setattr(business_reader.BusinessLogReader, 'load_file_bytes',
                        lambda self, **kw: list(contents))


def _zip_names(base64_content):
    return zipfile.ZipFile(io.BytesIO(base64.b64decode(base64_content))).namelist()


# ======================================================================
# report_service handler（ReportStatsQueryMixin）
# ======================================================================

class TestMixinListCaseLogs:
    """handle_list_case_logs：枚举逻辑名 / 空列表 / snake_case 字段。"""

    def test_list_enumerates_case_business_and_root_params(self, monkeypatch):
        m = _make_mixin(monkeypatch)
        _install_storage(monkeypatch, [
            {'key': f'{TASK_ID}/{CASE_ID}/out.wav', 'sizeBytes': 4,
             'lastModified': None},
        ])
        _install_business_logs(monkeypatch, metas=[
            {'rel': 'device_7/shared/run.log', 'size': 5,
             'mtime': datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)},
        ])

        result = m.handle_list_case_logs(1, CASE_ID)

        assert 'items' in result
        items = result['items']
        names = [it['name'] for it in items]
        # 三类逻辑名与 ZIP arcname / files= 同一套
        assert 'out.wav' in names
        assert 'business_logs/device_7/shared/run.log' in names
        assert 'adjusted_reference_params.json' in names

        out = next(it for it in items if it['name'] == 'out.wav')
        assert out['size'] == 4
        # 无 mtime → updated_at 省略（字段可选）
        assert 'updated_at' not in out

        biz = next(it for it in items if it['name'].startswith('business_logs/'))
        assert biz['size'] == 5
        assert biz['updated_at'].startswith('2026-10-20')

        params = next(it for it in items if it['name'] == 'adjusted_reference_params.json')
        assert params['size'] > 0 and 'updated_at' not in params

    def test_list_empty_items(self, monkeypatch):
        m = _make_mixin(monkeypatch, test_result=_make_test_result(include_params=False))
        _install_storage(monkeypatch, [])
        _install_business_logs(monkeypatch, metas=[])

        result = m.handle_list_case_logs(1, CASE_ID)

        assert result == {'items': []}

    def test_list_report_not_found(self, monkeypatch):
        from report_service.application.handlers._report_stats_query_mixin import (
            ReportStatsQueryMixin,
        )

        class _EmptyRepo:
            def get_by_id(self, report_id):
                return None

        m = ReportStatsQueryMixin.__new__(ReportStatsQueryMixin)
        m.repository = _EmptyRepo()

        result = m.handle_list_case_logs(999999, CASE_ID)

        assert result['success'] is False
        assert '未找到测试报告' in result['message']


class TestMixinDownloadCaseLogs:
    """handle_download_case_logs：files 筛选 / 整包兼容 / 缺文件 404。"""

    def test_download_without_files_whole_package(self, monkeypatch):
        m = _make_mixin(monkeypatch)
        _install_storage(monkeypatch, [
            {'key': f'{TASK_ID}/{CASE_ID}/out.wav', 'sizeBytes': 4,
             'lastModified': None},
        ])
        _install_business_logs(monkeypatch, contents=[
            ('device_7/shared/run.log', b'BIZ'),
        ])

        result = m.handle_download_case_logs(1, CASE_ID)

        assert result.get('content_base64')
        names = _zip_names(result['content_base64'])
        assert 'out.wav' in names
        assert 'business_logs/device_7/shared/run.log' in names
        assert 'adjusted_reference_params.json' in names

    def test_download_with_files_only_selected(self, monkeypatch):
        m = _make_mixin(monkeypatch)
        _install_storage(monkeypatch, [
            {'key': f'{TASK_ID}/{CASE_ID}/out.wav', 'sizeBytes': 4,
             'lastModified': None},
            {'key': f'{TASK_ID}/{CASE_ID}/debug.log', 'sizeBytes': 9,
             'lastModified': None},
        ])
        _install_business_logs(monkeypatch, contents=[
            ('device_7/shared/run.log', b'BIZ'),
        ])

        result = m.handle_download_case_logs(1, CASE_ID, files=['out.wav'])

        assert result.get('content_base64')
        assert _zip_names(result['content_base64']) == ['out.wav']

    def test_download_select_only_root_params(self, monkeypatch):
        m = _make_mixin(monkeypatch)
        _install_storage(monkeypatch, [])
        _install_business_logs(monkeypatch, contents=[])

        result = m.handle_download_case_logs(
            1, CASE_ID, files=['adjusted_reference_params.json'])

        assert result.get('content_base64')
        assert _zip_names(result['content_base64']) == ['adjusted_reference_params.json']

    def test_download_missing_selected_file_404(self, monkeypatch):
        m = _make_mixin(monkeypatch)
        _install_storage(monkeypatch, [])
        _install_business_logs(monkeypatch, contents=[])

        result = m.handle_download_case_logs(1, CASE_ID, files=['no_such.txt'])

        assert result['success'] is False and result['code'] == 404
        assert 'no_such.txt' in result['message']

    def test_download_no_files_at_all_400(self, monkeypatch):
        m = _make_mixin(monkeypatch, test_result=_make_test_result(include_params=False))
        _install_storage(monkeypatch, [])
        _install_business_logs(monkeypatch, contents=[])

        result = m.handle_download_case_logs(1, CASE_ID)

        assert result['success'] is False and result.get('code') is None
        assert '未找到用例日志目录' in result['message']

    def test_multi_source_names_match_list_and_zip(self, monkeypatch):
        """命名一致性关键点：multi-source 前缀下列表 name = ZIP arcname。"""
        m = _make_mixin(monkeypatch, source_task_ids=[7001, 7002],
                        test_result=_make_test_result(include_params=False))
        _install_storage(monkeypatch, [
            {'key': '7001/ACC1062-C1/a.log', 'sizeBytes': 3, 'lastModified': None},
            {'key': '7002/ACC1062-C1/b.log', 'sizeBytes': 4, 'lastModified': None},
        ])
        _install_business_logs(monkeypatch, contents=[])

        # 逻辑名统一 '/' 分隔（对齐 ZIP namelist 归一化，跨平台一致）
        expected = ['task_7001/a.log', 'task_7002/b.log']

        listed = m.handle_list_case_logs(1, CASE_ID)
        list_names = [it['name'] for it in listed['items']]
        assert sorted(list_names) == sorted(expected)

        dl = m.handle_download_case_logs(1, CASE_ID)
        assert sorted(_zip_names(dl['content_base64'])) == sorted(expected)


# ======================================================================
# report_service gRPC servicer
# ======================================================================

class TestLogsServicer:
    """ListCaseLogs / DownloadCaseLogs：files 透传 + code 透出。"""

    def _servicer_with(self, fake_handler):
        from report_service.interfaces.grpc.servicers import ReportServicer
        servicer = ReportServicer.__new__(ReportServicer)
        servicer._query_handler = fake_handler
        return servicer

    def test_download_case_logs_passes_files(self):
        from shared.proto import report_service_pb2 as report_pb

        calls = []

        class _FakeHandler:
            def handle_download_case_logs(self, report_id, case_id, files=None):
                calls.append((report_id, case_id, files))
                return {'filename': 'case_x.zip', 'content_base64': 'AA==', 'size': 1}

        servicer = self._servicer_with(_FakeHandler())
        resp = servicer.DownloadCaseLogs(
            report_pb.DownloadCaseLogsRequest(
                report_id=1, case_id='x', files=['a.txt', 'b.log']))

        assert resp.success is True
        assert calls == [(1, 'x', ['a.txt', 'b.log'])]

    def test_download_case_logs_no_files_empty_list(self):
        from shared.proto import report_service_pb2 as report_pb

        calls = []

        class _FakeHandler:
            def handle_download_case_logs(self, report_id, case_id, files=None):
                calls.append((report_id, case_id, files))
                return {'filename': 'case_x.zip', 'content_base64': 'AA==', 'size': 1}

        servicer = self._servicer_with(_FakeHandler())
        resp = servicer.DownloadCaseLogs(
            report_pb.DownloadCaseLogsRequest(report_id=1, case_id='x'))

        assert resp.success is True
        # 未传 files → handler 收到 None（整包，向后兼容）
        assert calls == [(1, 'x', None)]

    def test_download_case_logs_error_code_passthrough(self):
        from shared.proto import report_service_pb2 as report_pb

        class _FakeHandler:
            def handle_download_case_logs(self, report_id, case_id, files=None):
                return {'success': False, 'message': '以下日志文件不存在: no_such.txt',
                        'code': 404}

        servicer = self._servicer_with(_FakeHandler())
        resp = servicer.DownloadCaseLogs(
            report_pb.DownloadCaseLogsRequest(report_id=1, case_id='x', files=['no_such.txt']))

        assert resp.success is False and resp.code == 404
        assert 'no_such.txt' in resp.message

    def test_list_case_logs_servicer(self):
        from shared.proto import report_service_pb2 as report_pb

        calls = []

        class _FakeHandler:
            def handle_list_case_logs(self, report_id, case_id):
                calls.append((report_id, case_id))
                return {'items': [{'name': 'a.txt', 'size': 1}]}

        servicer = self._servicer_with(_FakeHandler())
        resp = servicer.ListCaseLogs(
            report_pb.ListCaseLogsRequest(report_id=1, case_id='x'))

        assert resp.success is True
        assert calls == [(1, 'x')]
        assert grpc_loads(resp.data, {})['items'] == [{'name': 'a.txt', 'size': 1}]

    def test_list_case_logs_report_not_found(self):
        from shared.proto import report_service_pb2 as report_pb

        class _FakeHandler:
            def handle_list_case_logs(self, report_id, case_id):
                return {'success': False, 'message': '未找到测试报告', 'code': 404}

        servicer = self._servicer_with(_FakeHandler())
        resp = servicer.ListCaseLogs(
            report_pb.ListCaseLogsRequest(report_id=1, case_id='x'))

        assert resp.success is False and resp.code == 404
        assert '未找到测试报告' in resp.message


# ======================================================================
# api_gateway 路由
# ======================================================================

class _FakeStub:
    """report_config_service.stub 桩：记录请求并返回预设响应。"""

    def __init__(self, resp=None):
        self.resp = resp
        self.calls = []

    def DownloadCaseLogs(self, req):
        self.calls.append(req)
        return self.resp

    def ListCaseLogs(self, req):
        self.calls.append(req)
        return self.resp


def _install_fake_stub(monkeypatch, resp):
    from api_gateway.infrastructure.grpc_proxies import report_proxies
    fake = _FakeStub(resp)
    monkeypatch.setattr(report_proxies, 'get_report_config_service_stub',
                        lambda: fake)
    return fake


def _make_gw_client(permissions):
    """挂载真实 report_bp 路由的迷你网关（注入指定权限 + 请求适配中间件）。"""
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


@pytest.fixture()
def gw_client():
    return _make_gw_client(['*'])


class TestGatewayCaseLogs:
    """api_gateway：列表路由 / 下载 files 编解码 / RBAC。"""

    def test_list_case_logs_route(self, gw_client, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb

        resp = report_pb.ReportConfigResponse(
            success=True, message='ok', data=grpc_dumps(
                {'items': [{'name': 'out.wav', 'size': 4}]}))
        fake = _install_fake_stub(monkeypatch, resp)

        r = gw_client.get('/api/v1/reports/42/cases/ACC1062-C1/logs')

        assert r.status_code == 200
        assert r.json()['data']['items'][0]['name'] == 'out.wav'
        req = fake.calls[0]
        assert req.report_id == 42 and req.case_id == 'ACC1062-C1'

    def test_download_without_files_keeps_whole_package(self, gw_client, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb

        resp = report_pb.ReportConfigResponse(
            success=True, message='ok', data=grpc_dumps(
                {'filename': 'case_ACC1062-C1_logs.zip',
                 'content_base64': base64.b64encode(b'DATA').decode(),
                 'size': 4, 'mime_type': 'application/octet-stream'}))
        fake = _install_fake_stub(monkeypatch, resp)

        r = gw_client.get('/api/v1/reports/42/cases/ACC1062-C1/logs/download')

        assert r.status_code == 200
        assert list(fake.calls[0].files) == []

    def test_download_with_files_parses_json_array(self, gw_client, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb

        resp = report_pb.ReportConfigResponse(
            success=True, message='ok', data=grpc_dumps(
                {'filename': 'case_ACC1062-C1_logs.zip',
                 'content_base64': base64.b64encode(b'DATA').decode(),
                 'size': 4, 'mime_type': 'application/octet-stream'}))
        fake = _install_fake_stub(monkeypatch, resp)

        r = gw_client.get(
            '/api/v1/reports/42/cases/ACC1062-C1/logs/download',
            params={'files': '["a.txt","b.log"]'})

        assert r.status_code == 200
        assert list(fake.calls[0].files) == ['a.txt', 'b.log']

    def test_download_empty_files_400(self, gw_client, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb
        _install_fake_stub(monkeypatch, report_pb.ReportConfigResponse(
            success=True, message='ok', data='{}'))

        r = gw_client.get(
            '/api/v1/reports/42/cases/ACC1062-C1/logs/download',
            params={'files': '[]'})

        assert r.status_code == 400
        assert r.json()['success'] is False

    def test_download_invalid_files_json_400(self, gw_client, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb
        _install_fake_stub(monkeypatch, report_pb.ReportConfigResponse(
            success=True, message='ok', data='{}'))

        r = gw_client.get(
            '/api/v1/reports/42/cases/ACC1062-C1/logs/download',
            params={'files': 'not-a-json-array'})

        assert r.status_code == 400
        assert 'JSON' in r.json()['message']

    def test_download_not_found_code_404(self, gw_client, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb

        resp = report_pb.ReportConfigResponse(
            success=False, message='以下日志文件不存在: no_such.txt',
            data=grpc_dumps({'code': 404}), code=404)
        _install_fake_stub(monkeypatch, resp)

        r = gw_client.get(
            '/api/v1/reports/42/cases/ACC1062-C1/logs/download',
            params={'files': '["no_such.txt"]'})

        assert r.status_code == 404

    def test_list_route_requires_report_read(self, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb
        _install_fake_stub(monkeypatch, report_pb.ReportConfigResponse(
            success=True, message='ok', data='{}'))

        client = _make_gw_client(['report:download_log'])
        r = client.get('/api/v1/reports/42/cases/ACC1062-C1/logs')

        assert r.status_code == 403

    def test_download_route_requires_download_log(self, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb
        _install_fake_stub(monkeypatch, report_pb.ReportConfigResponse(
            success=True, message='ok', data='{}'))

        client = _make_gw_client(['report:read'])
        r = client.get('/api/v1/reports/42/cases/ACC1062-C1/logs/download')

        assert r.status_code == 403
