# -*- coding: utf-8 -*-
"""INT-1073 专项：报告用例日志文件列表与按选打包下载端点。

覆盖三层：
- report_service 文件清单构建器（INT-1056 审计 §四：三来源统一 arcname 命名空间）：
  handle_list_case_log_files / handle_download_selected_case_logs /
  handle_download_case_logs（缺省全量与 download-selected 空选字节一致）
- report_service gRPC servicer：ListCaseLogFiles / DownloadSelectedCaseLogs
  （错误经 code 透出 404/400）
- api_gateway：GET .../logs/files + POST .../logs/download-selected 路由、
  Blob Content-Disposition、旧端点补挂 report:download_log 后 guest 403

DB：不依赖（handler 以假仓储注入，gRPC/存储/日志读取以 monkeypatch 替换）。
"""
import base64
import io
import json
import os
import zipfile
from datetime import datetime, timezone

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.utils.grpc_json import loads as grpc_loads, dumps as grpc_dumps

TASK_ID = 100
OTHER_TASK_ID = 200
CASE_ID = 'CASE-1073'
# 统一测试时间（OSS lastModified / 业务日志 st_mtime 基准）
BASE_DT = datetime(2026, 10, 18, 4, 0, 0, tzinfo=timezone.utc)


def _agg(task_id=TASK_ID):
    """最小 ReportAggregate（domain 纯对象，无需 DB）。"""
    from report_service.domain.entities import ReportAggregate
    return ReportAggregate(id=1, task_id=task_id)


def _result(result_data=None, device_id=7):
    """构造 TestResult dict（_query_case_logs 消费形状）。"""
    return {
        'id': 1,
        'task_id': TASK_ID,
        'test_case_id': CASE_ID,
        'device_id': device_id,
        'execution_status': 'completed',
        'result_data': result_data,
        'result_data_path': None,
    }


class _Repo:
    def __init__(self, aggregate):
        self._aggregate = aggregate

    def get_by_id(self, report_id):
        return self._aggregate


@pytest.fixture()
def plain_task(monkeypatch):
    """普通任务：cherry/merge 均为空，结果按 task_id 批量查询（无虚拟文件）。"""
    import report_service.infrastructure.clients.grpc_clients as grpc_clients

    monkeypatch.setattr(grpc_clients, '_grpc_get_cherry_pick_relations', lambda tid: [])
    monkeypatch.setattr(grpc_clients, '_grpc_get_task_merge_relations', lambda tid: [])
    monkeypatch.setattr(grpc_clients, '_grpc_get_test_results_by_ids', lambda ids: [])
    monkeypatch.setattr(
        grpc_clients, '_grpc_get_test_results_by_task_ids',
        lambda ids: [_result()] if TASK_ID in ids else [])
    return grpc_clients


@pytest.fixture()
def virtual_result(monkeypatch):
    """覆盖 gRPC 结果：result_data 含 adjusted_reference_params（虚拟文件来源）。"""
    import report_service.infrastructure.clients.grpc_clients as grpc_clients
    monkeypatch.setattr(
        grpc_clients, '_grpc_get_test_results_by_task_ids',
        lambda ids: [_result(result_data={'adjusted_reference_params': {'gain': 1.5}})]
        if TASK_ID in ids else [])


@pytest.fixture()
def handler(plain_task):
    """ReportQueryHandler + 假仓储（task_id=100）。"""
    from report_service.application.handlers.report_handlers import ReportQueryHandler
    return ReportQueryHandler(repository=_Repo(_agg()))


@pytest.fixture()
def mock_storage(monkeypatch):
    """storage 桩：objects_by_prefix / loads 字典驱动。"""
    from shared.infrastructure import storage as storage_mod

    state = {'objects_by_prefix': {}, 'loads': {}}

    def _list(category, prefix=''):
        return state['objects_by_prefix'].get(prefix, [])

    def _load(path):
        return state['loads'].get(path, b'')

    monkeypatch.setattr(storage_mod.storage, 'list_objects_with_meta', _list)
    monkeypatch.setattr(storage_mod.storage, 'load_bytes', _load)
    return state


@pytest.fixture()
def business_log(monkeypatch, tmp_path):
    """在临时日志根下创建一条业务日志文件（INT-81 路径体系），返回相对路径信息。"""
    from shared.infrastructure.config import BaseConfig
    from shared.logging.config import reset_log_settings

    monkeypatch.setattr(BaseConfig, 'LOG_ROOT_DIR', str(tmp_path))
    reset_log_settings()
    try:
        # 第二段 = 被测设备 ID（结果 device_id=7，与 _result() 对齐）
        log_rel = os.path.join('business', str(TASK_ID), '7', 'shared', 'app.log')
        log_path = os.path.join(str(tmp_path), log_rel)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        content = b'{"level":"info","content":"hello"}\n'
        with open(log_path, 'wb') as fh:
            fh.write(content)
        # 相对 task 目录路径（与 BusinessLogReader.load_file_bytes 的 rel 口径一致）
        task_dir = os.path.join(str(tmp_path), 'business', str(TASK_ID))
        rel = os.path.relpath(log_path, task_dir).replace(os.sep, '/')
        yield {'rel': rel, 'abs_path': log_path, 'content': content}
    finally:
        monkeypatch.undo()
        reset_log_settings()


def _case_entry(prefix, name, size, offset_days=0):
    """构造 storage.list_objects_with_meta 对象条目。"""
    from datetime import timedelta
    return {
        'key': f'{prefix}{name}',
        'sizeBytes': size,
        'lastModified': BASE_DT - timedelta(days=offset_days),
    }


def _zip_entries(content_base64):
    """解包 handler 返回的 zip base64 → {arcname: bytes}。"""
    raw = base64.b64decode(content_base64)
    with zipfile.ZipFile(io.BytesIO(raw), 'r') as zf:
        return {name: zf.read(name) for name in zf.namelist()}


# ======================================================================
# report_service：文件清单构建器 + 两个新 handler
# ======================================================================

class TestListHandler:
    """handle_list_case_log_files：清单元数据 / 空态 / 三来源命名空间。"""

    def test_metadata_correct_for_case_files(self, handler, mock_storage):
        mock_storage['objects_by_prefix'][f'{TASK_ID}/{CASE_ID}/'] = [
            _case_entry(f'{TASK_ID}/{CASE_ID}/', 'out.wav', 4, offset_days=0),
            _case_entry(f'{TASK_ID}/{CASE_ID}/', 'ref.json', 10, offset_days=1),
        ]
        result = handler.handle_list_case_log_files(1, CASE_ID)
        files = result['files']
        assert [f['filename'] for f in files] == ['out.wav', 'ref.json']
        assert files[0]['size_bytes'] == 4
        # lastModified(BASE_DT) → ISO8601 UTC 'Z'
        assert files[0]['updated_at'] == '2026-10-18T04:00:00Z'
        assert files[1]['updated_at'] == '2026-10-17T04:00:00Z'

    def test_empty_case_returns_empty_list(self, handler, mock_storage):
        result = handler.handle_list_case_log_files(1, CASE_ID)
        assert result['files'] == []

    def test_business_and_virtual_included(self, handler, mock_storage, business_log,
                                           virtual_result):
        """业务日志 business_logs/{rel} + 虚拟文件 adjusted_reference_params.json。"""
        result = handler.handle_list_case_log_files(1, CASE_ID)
        filenames = [f['filename'] for f in result['files']]

        assert f"business_logs/{business_log['rel']}" in filenames
        assert 'adjusted_reference_params.json' in filenames

        biz = next(f for f in result['files']
                   if f['filename'] == f"business_logs/{business_log['rel']}")
        assert biz['size_bytes'] == len(business_log['content'])
        assert biz['updated_at'].endswith('Z')

        virt = next(f for f in result['files']
                    if f['filename'] == 'adjusted_reference_params.json')
        expected = json.dumps({'gain': 1.5}, ensure_ascii=False, indent=2).encode('utf-8')
        assert virt['size_bytes'] == len(expected)
        assert virt['updated_at'] is None

    def test_multi_task_prefix(self, handler, mock_storage, monkeypatch):
        """多任务/合并源：arcname 加 task_{task_id}/ 前缀（与现全量下载规则一致）。"""
        import report_service.infrastructure.clients.grpc_clients as grpc_clients
        monkeypatch.setattr(
            grpc_clients, '_grpc_get_test_results_by_task_ids',
            lambda ids: [_result()])
        handler.repository = _Repo(_agg())
        # 合并源展开为两个任务
        monkeypatch.setattr(
            'report_service.application.services.task_result_resolver.resolve_merge_source_task_ids',
            lambda tid: [TASK_ID, OTHER_TASK_ID])

        mock_storage['objects_by_prefix'][f'{TASK_ID}/{CASE_ID}/'] = [
            _case_entry(f'{TASK_ID}/{CASE_ID}/', 'out.wav', 4)]
        mock_storage['objects_by_prefix'][f'{OTHER_TASK_ID}/{CASE_ID}/'] = [
            _case_entry(f'{OTHER_TASK_ID}/{CASE_ID}/', 'ref.json', 8)]

        result = handler.handle_list_case_log_files(1, CASE_ID)
        filenames = [f['filename'] for f in result['files']]
        # 现 _write_case_log_files 用 os.path.join 拼 task_ 前缀：Windows 产生
        # 反斜杠（字节级一致契约保留此既有行为），断言按正斜杠归一化
        normalized = [fn.replace('\\', '/') for fn in filenames]
        assert f"task_{TASK_ID}/out.wav" in normalized
        assert f"task_{OTHER_TASK_ID}/ref.json" in normalized

    def test_report_not_found_404(self, handler):
        handler.repository = _Repo(None)
        result = handler.handle_list_case_log_files(999, CASE_ID)
        assert result['success'] is False
        assert result['message'] == '未找到测试报告'
        assert result['code'] == 404

    def test_report_no_task_404(self, handler):
        handler.repository = _Repo(_agg(task_id=None))
        result = handler.handle_list_case_log_files(1, CASE_ID)
        assert result['success'] is False
        assert result['message'] == '该报告没有关联的任务ID'
        assert result['code'] == 404


class TestDownloadSelectedHandler:
    """handle_download_selected_case_logs：按选一致 / 未知名 400 / 缺省全量字节一致。"""

    def _seed(self, mock_storage, business_log=None):
        mock_storage['objects_by_prefix'][f'{TASK_ID}/{CASE_ID}/'] = [
            _case_entry(f'{TASK_ID}/{CASE_ID}/', 'out.wav', 4),
            _case_entry(f'{TASK_ID}/{CASE_ID}/', 'ref.json', 10),
        ]
        mock_storage['loads'][f'case_result/{TASK_ID}/{CASE_ID}/out.wav'] = b'WAVDATA'
        mock_storage['loads'][f'case_result/{TASK_ID}/{CASE_ID}/ref.json'] = b'REFDATA!'

    def test_selected_zip_matches_filenames(self, handler, mock_storage, business_log):
        self._seed(mock_storage, business_log)
        result = handler.handle_download_selected_case_logs(1, CASE_ID, ['out.wav'])
        assert result['filename'] == f'case_{CASE_ID}_logs_selected.zip'
        entries = _zip_entries(result['content_base64'])
        assert list(entries) == ['out.wav']
        assert entries['out.wav'] == b'WAVDATA'

    def test_selected_zip_keeps_request_order(self, handler, mock_storage, business_log):
        self._seed(mock_storage, business_log)
        result = handler.handle_download_selected_case_logs(
            1, CASE_ID, ['ref.json', 'out.wav', 'ref.json'])
        entries = _zip_entries(result['content_base64'])
        assert list(entries) == ['ref.json', 'out.wav']

    def test_selected_unknown_filename_400(self, handler, mock_storage):
        self._seed(mock_storage)
        result = handler.handle_download_selected_case_logs(
            1, CASE_ID, ['out.wav', 'nope.log'])
        assert result['success'] is False
        assert 'nope.log' in result['message']
        assert result.get('content_base64') is None

    def test_default_full_equals_download_case_logs(self, handler, mock_storage,
                                                    business_log, virtual_result):
        """缺省全量（空 filenames）与现 download_case_logs 输出一致（对比 zip 内容）。"""
        self._seed(mock_storage, business_log)

        selected = handler.handle_download_selected_case_logs(1, CASE_ID, [])
        full = handler.handle_download_case_logs(1, CASE_ID)

        assert selected['filename'] == f'case_{CASE_ID}_logs.zip'
        assert full['filename'] == f'case_{CASE_ID}_logs.zip'
        assert _zip_entries(selected['content_base64']) == _zip_entries(full['content_base64'])

    def test_default_full_no_logs_400(self, handler, mock_storage):
        """缺省全量且无任何 case/业务日志 → 400（与现行为一致；虚拟文件单独不算）。"""
        result = handler.handle_download_selected_case_logs(1, CASE_ID, [])
        assert result['success'] is False
        assert result['message'] == '未找到用例日志目录'

    def test_virtual_only_selected_ok(self, handler, mock_storage, virtual_result):
        """按选明确指定虚拟文件 → 200 zip（与缺省全量的 400 语义不同）。"""
        result = handler.handle_download_selected_case_logs(
            1, CASE_ID, ['adjusted_reference_params.json'])
        entries = _zip_entries(result['content_base64'])
        assert list(entries) == ['adjusted_reference_params.json']
        assert entries['adjusted_reference_params.json'].startswith(b'{')

    def test_report_not_found_404(self, handler):
        handler.repository = _Repo(None)
        result = handler.handle_download_selected_case_logs(999, CASE_ID, [])
        assert result['success'] is False and result['code'] == 404


# ======================================================================
# report_service gRPC servicer：ListCaseLogFiles / DownloadSelectedCaseLogs
# ======================================================================

class TestServicer:
    """servicer 层：code 透出 / content_base64 判定（handler 以假对象注入）。"""

    @pytest.fixture()
    def servicer(self):
        from report_service.interfaces.grpc.servicers import ReportServicer
        servicer = ReportServicer()
        servicer._query_handler = self._FakeHandler()
        return servicer

    class _FakeHandler:
        def __init__(self):
            self.list_result = {'files': [{'filename': 'out.wav', 'size_bytes': 4,
                                           'updated_at': '2026-10-18T04:00:00Z'}]}
            self.download_result = {
                'filename': f'case_{CASE_ID}_logs_selected.zip',
                'content_base64': base64.b64encode(b'ZIPDATA').decode('utf-8'),
                'size': 7,
            }

        def handle_list_case_log_files(self, report_id, case_id):
            return self.list_result

        def handle_download_selected_case_logs(self, report_id, case_id, filenames):
            return self.download_result

    def test_list_success(self, servicer):
        from shared.proto import report_service_pb2 as report_pb
        resp = servicer.ListCaseLogFiles(report_pb.ListCaseLogFilesRequest(
            report_id=1, case_id=CASE_ID))
        assert resp.success is True
        data = grpc_loads(resp.data, {})
        assert data['files'][0]['filename'] == 'out.wav'

    def test_list_report_not_found_404(self, servicer):
        from shared.proto import report_service_pb2 as report_pb
        servicer._query_handler.list_result = {
            'success': False, 'message': '未找到测试报告', 'code': 404}
        resp = servicer.ListCaseLogFiles(report_pb.ListCaseLogFilesRequest(
            report_id=999, case_id=CASE_ID))
        assert resp.success is False
        assert resp.code == 404

    def test_download_selected_success(self, servicer):
        from shared.proto import report_service_pb2 as report_pb
        resp = servicer.DownloadSelectedCaseLogs(report_pb.DownloadSelectedCaseLogsRequest(
            report_id=1, case_id=CASE_ID, filenames=['out.wav']))
        assert resp.success is True
        data = grpc_loads(resp.data, {})
        assert data['filename'] == f'case_{CASE_ID}_logs_selected.zip'

    def test_download_selected_unknown_400(self, servicer):
        from shared.proto import report_service_pb2 as report_pb
        servicer._query_handler.download_result = {
            'success': False, 'message': '未知的文件名: nope.log'}
        resp = servicer.DownloadSelectedCaseLogs(report_pb.DownloadSelectedCaseLogsRequest(
            report_id=1, case_id=CASE_ID, filenames=['nope.log']))
        assert resp.success is False
        assert resp.code == 0
        assert 'nope.log' in resp.message


# ======================================================================
# api_gateway：路由 + Blob + 权限
# ======================================================================

class _FakeStub:
    """report_config_service.stub 桩：记录请求并返回预设响应。"""

    def __init__(self, resp):
        self.resp = resp
        self.calls = []

    def ListCaseLogFiles(self, req):
        self.calls.append(req)
        return self.resp

    def DownloadSelectedCaseLogs(self, req):
        self.calls.append(req)
        return self.resp

    def DownloadCaseLogs(self, req):
        self.calls.append(req)
        return self.resp


def _install_fake_stub(monkeypatch, resp):
    from api_gateway.infrastructure.grpc_proxies import report_proxies
    fake = _FakeStub(resp)
    monkeypatch.setattr(report_proxies, 'get_report_config_service_stub',
                        lambda: fake)
    return fake


def _gw_client(permissions):
    """挂载真实 report_bp 路由的迷你网关，注入指定权限。"""
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
def gw_admin():
    return _gw_client(['*'])


@pytest.fixture()
def gw_guest():
    # guest：有 report:read 但无 report:download_log
    return _gw_client(['report:read'])


class TestGatewayRoutes:
    """api_gateway：HTTP 200/400/404 + Blob Content-Disposition + guest 403。"""

    def test_list_route_200(self, gw_admin, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb
        resp_pb = report_pb.ReportConfigResponse(
            success=True, message='ok',
            data=grpc_dumps({'files': [{'filename': 'out.wav', 'size_bytes': 4,
                                        'updated_at': '2026-10-18T04:00:00Z'}]}))
        _install_fake_stub(monkeypatch, resp_pb)

        res = gw_admin.get(f'/api/v1/reports/1/cases/{CASE_ID}/logs/files')
        assert res.status_code == 200
        body = res.json()
        assert body['code'] == 0
        assert body['data'][0]['filename'] == 'out.wav'

    def test_list_route_404(self, gw_admin, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb
        resp_pb = report_pb.ReportConfigResponse(
            success=False, message='未找到测试报告', code=404,
            data=grpc_dumps({'code': 404}))
        _install_fake_stub(monkeypatch, resp_pb)

        res = gw_admin.get(f'/api/v1/reports/999/cases/{CASE_ID}/logs/files')
        assert res.status_code == 404
        assert res.json()['message'] == '未找到测试报告'

    def test_list_route_403_guest(self, gw_guest):
        res = gw_guest.get(f'/api/v1/reports/1/cases/{CASE_ID}/logs/files')
        assert res.status_code == 403

    def test_download_selected_route_200_blob(self, gw_admin, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb
        zip_bytes = b'PK\x05\x06' + b'X' * 16  # 任意 zip 样字节
        resp_pb = report_pb.ReportConfigResponse(
            success=True, message='ok',
            data=grpc_dumps({'filename': f'case_{CASE_ID}_logs_selected.zip',
                             'content_base64': base64.b64encode(zip_bytes).decode('utf-8'),
                             'size': len(zip_bytes)}))
        _install_fake_stub(monkeypatch, resp_pb)

        res = gw_admin.post(
            f'/api/v1/reports/1/cases/{CASE_ID}/logs/download-selected',
            json={'filenames': ['out.wav']})
        assert res.status_code == 200
        assert res.headers['Content-Type'] == 'application/zip'
        assert f'attachment; filename="case_{CASE_ID}_logs_selected.zip"' in \
            res.headers['Content-Disposition']
        assert res.content == zip_bytes

    def test_download_selected_route_400_unknown(self, gw_admin, monkeypatch):
        from shared.proto import report_service_pb2 as report_pb
        resp_pb = report_pb.ReportConfigResponse(
            success=False, message='未知的文件名: nope.log', code=0,
            data=grpc_dumps({'code': 0}))
        _install_fake_stub(monkeypatch, resp_pb)

        res = gw_admin.post(
            f'/api/v1/reports/1/cases/{CASE_ID}/logs/download-selected',
            json={'filenames': ['nope.log']})
        assert res.status_code == 400
        assert 'nope.log' in res.json()['message']

    def test_download_selected_route_403_guest(self, gw_guest):
        res = gw_guest.post(
            f'/api/v1/reports/1/cases/{CASE_ID}/logs/download-selected',
            json={'filenames': ['out.wav']})
        assert res.status_code == 403

    def test_download_selected_empty_filenames_ok(self, gw_admin, monkeypatch):
        """filenames 缺省/空数组 = 全部（filename case_{case_id}_logs.zip）。"""
        from shared.proto import report_service_pb2 as report_pb
        resp_pb = report_pb.ReportConfigResponse(
            success=True, message='ok',
            data=grpc_dumps({'filename': f'case_{CASE_ID}_logs.zip',
                             'content_base64': base64.b64encode(b'ZIP').decode('utf-8'),
                             'size': 3}))
        fake = _install_fake_stub(monkeypatch, resp_pb)

        res = gw_admin.post(
            f'/api/v1/reports/1/cases/{CASE_ID}/logs/download-selected',
            json={})
        assert res.status_code == 200
        assert f'filename="case_{CASE_ID}_logs.zip"' in res.headers['Content-Disposition']
        # 空数组请求体也透传空 filenames
        gw_admin.post(f'/api/v1/reports/1/cases/{CASE_ID}/logs/download-selected',
                      json={'filenames': []})
        assert fake.calls[-1].filenames == []

    def test_old_download_route_403_guest(self, gw_guest):
        """旧端点补挂 report:download_log 后 guest → 403（契约 §二裁定）。"""
        res = gw_guest.get(f'/api/v1/reports/1/cases/{CASE_ID}/logs/download')
        assert res.status_code == 403

    def test_old_download_route_still_works_admin(self, gw_admin, monkeypatch):
        """旧端点行为不动（admin 仍可下载）。"""
        from shared.proto import report_service_pb2 as report_pb
        resp_pb = report_pb.ReportConfigResponse(
            success=True, message='ok',
            data=grpc_dumps({'filename': f'case_{CASE_ID}_logs.zip',
                             'content_base64': base64.b64encode(b'ZIP').decode('utf-8'),
                             'size': 3}))
        _install_fake_stub(monkeypatch, resp_pb)

        res = gw_admin.get(f'/api/v1/reports/1/cases/{CASE_ID}/logs/download')
        assert res.status_code == 200
        assert 'attachment; filename=' in res.headers['Content-Disposition']
