# -*- coding: utf-8 -*-
"""INT-1763 Report Studio 来源类型 + 文件型独立报告导入（3b）单测

覆盖（SQLite 文件库，服务层 + 网关 BFF 两层）：
- schema：source_type 默认 platform_report、report_id / chart_specs.report_id 可空
- 导入 md：正文进 markdown_content、source_type=uploaded_file、版本 1 快照
  snapshot_reason=import、report_id 为空（独立文档库）
- 导入 html/pptx：只记 source_file_path / source_format / source_file_size
- task_id 关联：有报告 → report_id 落关联值；无报告 → 404
- 列表：report_id / source_type / parent_doc_id 三个过滤维度
- 图表降级：chart_specs.report_id 为空 → 409「需重新绑定报告」，不抛 TypeError
- 网关：白名单 415、超限 413、空文件 400、Content-Type 不符 415、
  建档失败删除已上传对象、上传件下载带 nosniff + 沙箱 CSP

返工（审计 P2/P3）：
- md 正文 >4MiB 不再被 grpcio 默认 4MiB 收包上限拒成 HTTP 500：report_service
  服务端按 GRPC_MAX_MESSAGE_MB 放大（真实 in-process gRPC 往返 + 默认上限对照），
  网关对序列化后仍超限的请求回 413；
- 迁移脚本必须登记进引导链且带 --apply（合入 V9.7.31 时该文件必冲突，防解漏）。
"""
import importlib.util
import os

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from sqlalchemy import create_engine

import shared.models.database as database
from shared.infrastructure.user_context import (
    set_current_user_id,
    set_current_user_is_admin,
)
from report_service.infrastructure.persistence.models import Report
from report_service.application.services.report_studio_service import (
    report_studio_service,
)
from report_service.domain.entities.report_studio import ReportStudioChartSpec


@pytest.fixture()
def sqlite_db(monkeypatch, tmp_path):
    engine = create_engine(
        f'sqlite:///{tmp_path / "int1763.db"}', connect_args={'check_same_thread': False})
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(engine)
    set_current_user_id(None)
    set_current_user_is_admin(False)
    yield database
    database.remove_db_session()
    engine.dispose()


def _seed_report(session, task_id=12, name='测试报告'):
    report = Report(name=name, type='standard', status='completed', task_id=task_id)
    session.add(report)
    session.commit()
    return report.id


def _upload(svc, **overrides):
    data = {'title': '导入报告', 'source_format': 'md',
            'markdown_content': '# 导入正文'}
    data.update(overrides)
    return svc.create_upload_document(data)


class TestSourceTypeSchema:
    def test_platform_document_defaults(self, sqlite_db):
        session = database.get_db_session()
        report_id = _seed_report(session)
        session.close()
        r = report_studio_service.create_document(
            {'report_id': report_id, 'markdown_content': '# 草稿'})
        assert r['success'] is True, r
        assert r['data']['source_type'] == 'platform_report'
        assert r['data']['parent_doc_id'] is None
        assert r['data']['source_file_path'] is None

    def test_uploaded_document_has_null_report_id(self, sqlite_db):
        r = _upload(report_studio_service)
        assert r['success'] is True, r
        doc = r['data']
        assert doc['report_id'] is None
        assert doc['source_type'] == 'uploaded_file'
        assert doc['source_format'] == 'md'
        assert doc['markdown_content'] == '# 导入正文'
        assert doc['source_file_path'] is None, 'md 不落文件列'
        # 版本 1 快照存在且原因=import
        versions = report_studio_service.list_versions({'doc_id': doc['doc_id']})
        assert versions['data']['total'] == 1
        assert versions['data']['items'][0]['version'] == 1
        assert versions['data']['items'][0]['snapshot_reason'] == 'import'

    def test_uploaded_file_document_metadata(self, sqlite_db):
        r = _upload(report_studio_service, source_format='pptx',
                    markdown_content='', source_file_path='oss://reports/studio_uploads/a.pptx',
                    source_file_size=2048)
        assert r['success'] is True, r
        doc = r['data']
        assert doc['source_file_path'] == 'oss://reports/studio_uploads/a.pptx'
        assert doc['source_format'] == 'pptx'
        assert doc['source_file_size'] == 2048
        assert doc['markdown_content'] == ''
        assert doc['source_download_ref'].endswith('/source')


class TestUploadValidation:
    def test_unsupported_format_400(self, sqlite_db):
        r = _upload(report_studio_service, source_format='docx', markdown_content='x')
        assert r['success'] is False
        assert r['code'] == 400

    def test_empty_markdown_400(self, sqlite_db):
        r = _upload(report_studio_service, markdown_content='   ')
        assert r['success'] is False
        assert r['code'] == 400

    def test_html_without_file_path_400(self, sqlite_db):
        r = _upload(report_studio_service, source_format='html', markdown_content='')
        assert r['success'] is False
        assert r['code'] == 400

    def test_missing_parent_doc_404(self, sqlite_db):
        r = _upload(report_studio_service, parent_doc_id='no-such-parent')
        assert r['success'] is False
        assert r['code'] == 404

    def test_task_id_without_report_404(self, sqlite_db):
        r = _upload(report_studio_service, task_id=99999)
        assert r['success'] is False
        assert r['code'] == 404

    def test_task_id_resolves_report(self, sqlite_db):
        session = database.get_db_session()
        report_id = _seed_report(session, task_id=42)
        session.close()
        r = _upload(report_studio_service, task_id=42)
        assert r['success'] is True, r
        assert r['data']['report_id'] == report_id
        assert r['data']['source_type'] == 'uploaded_file'


class TestListDocuments:
    def test_filters(self, sqlite_db):
        session = database.get_db_session()
        report_id = _seed_report(session, task_id=7)
        session.close()
        svc = report_studio_service
        platform_doc = svc.create_document(
            {'report_id': report_id, 'markdown_content': '# 平台'})['data']['doc_id']
        linked_upload = _upload(svc, task_id=7)['data']['doc_id']
        library_upload = _upload(svc, title='独立文档')['data']['doc_id']

        # 按报告全量：平台文档 + 该报告关联的导入文档
        all_docs = svc.list_documents({'report_id': report_id})
        ids = {d['doc_id'] for d in all_docs['data']['items']}
        assert ids == {platform_doc, linked_upload}
        assert all_docs['data']['total'] == 2

        # 平台报告文档列表（报告详情页口径）：只出 platform_report，迁移前一致
        platform_only = svc.list_documents(
            {'report_id': report_id, 'source_type': 'platform_report'})
        assert [d['doc_id'] for d in platform_only['data']['items']] == [platform_doc]

        # 独立文档库：不关联平台报告的导入文档
        library = svc.list_documents({'source_type': 'uploaded_file', 'report_id': None})
        library_ids = {d['doc_id'] for d in library['data']['items']}
        assert library_ids == {linked_upload, library_upload}

    def test_unknown_source_type_400(self, sqlite_db):
        r = report_studio_service.list_documents({'source_type': 'bogus'})
        assert r['success'] is False
        assert r['code'] == 400

    def test_owner_scope_for_authenticated_user(self, sqlite_db):
        svc = report_studio_service
        set_current_user_id(101)
        mine = _upload(svc, title='我的文档')['data']['doc_id']
        mine_list = svc.list_documents({'source_type': 'uploaded_file'})
        assert [d['doc_id'] for d in mine_list['data']['items']] == [mine]

        set_current_user_id(202)
        others = _upload(svc, title='别人的文档')['data']['doc_id']
        others_list = svc.list_documents({'source_type': 'uploaded_file'})
        assert [d['doc_id'] for d in others_list['data']['items']] == [others]

        # 管理员看全部
        set_current_user_is_admin(True)
        all_docs = svc.list_documents({'source_type': 'uploaded_file'})
        assert {d['doc_id'] for d in all_docs['data']['items']} == {mine, others}
        set_current_user_is_admin(False)
        set_current_user_id(None)


class TestChartRebind:
    def test_null_report_id_returns_409(self, sqlite_db):
        svc = report_studio_service
        doc_id = _upload(svc)['data']['doc_id']
        svc.repo.create_chart_spec(ReportStudioChartSpec(
            chart_id='chart-null', doc_id=doc_id, report_id=None,
            metric_params={'metrics': ['overall']}))
        r = svc.get_chart_data({'doc_id': doc_id, 'chart_id': 'chart-null'})
        assert r['success'] is False
        assert r['code'] == 409
        assert r['data']['rebind_required'] is True


# ==================== 网关 BFF：上传 / 下载 ====================

class _FakeUpload:
    """模拟 FastAPI UploadFile 的最小接口。"""

    def __init__(self, content: bytes, filename: str, content_type: str):
        import io
        self.file = io.BytesIO(content)
        self.filename = filename
        self.content_type = content_type


class _Stub:
    """假 stub：记录 payload，按配置返回 StudioResponse。"""

    def __init__(self):
        self.calls = []
        self.responses = {}

    def _mk(self, method):
        def fn(req):
            import json as _json
            from shared.proto import report_service_pb2 as pb
            self.calls.append((method, _json.loads(req.data or '{}') or {}))
            ok, message, data, code = self.responses.get(method, (True, 'ok', {}, 0))
            return pb.StudioResponse(success=ok, message=message,
                                     data=_json.dumps(data), code=code)
        return fn

    def __getattr__(self, name):
        return self._mk(name)


@pytest.fixture()
def bff(monkeypatch):
    import api_gateway.application.services.report.report_studio_service as mod
    stub = _Stub()
    monkeypatch.setattr(mod, 'report_studio_service',
                        type('P', (), {'stub': stub})())
    uploaded, deleted = [], []

    class _FakeStorage:
        @staticmethod
        def upload_studio_upload(data, file_name, content_type='application/octet-stream'):
            path = f'oss://reports/studio_uploads/{len(uploaded) + 1}.{file_name.rsplit(".", 1)[-1]}'
            uploaded.append((path, data, file_name, content_type))
            return path

        @staticmethod
        def download_bytes(path):
            return b'<html>report</html>'

        @staticmethod
        def delete(path):
            deleted.append(path)

    monkeypatch.setattr(mod, 'ReportOSSStorage', _FakeStorage)
    return mod, stub, uploaded, deleted


class TestGatewayImport:
    def test_md_upload_goes_to_markdown_content(self, bff):
        mod, stub, uploaded, deleted = bff
        result = mod.ReportStudioCommandService.import_document(
            _FakeUpload('# 中文正文\n'.encode('utf-8-sig'), 'report.md', 'text/markdown'),
            title='对比报告', task_id='12')
        assert result[1] == 200, result
        method, payload = stub.calls[0]
        assert method == 'CreateStudioUploadDocument'
        assert payload['markdown_content'] == '# 中文正文\n'
        assert payload['source_format'] == 'md'
        assert payload['task_id'] == 12
        assert 'source_file_path' not in payload
        assert uploaded == [], 'md 不落文件'

    def test_html_upload_lands_in_storage(self, bff):
        mod, stub, uploaded, deleted = bff
        result = mod.ReportStudioCommandService.import_document(
            _FakeUpload(b'<html></html>', 'report.html', 'text/html'))
        assert result[1] == 200, result
        assert len(uploaded) == 1
        payload = stub.calls[0][1]
        assert payload['source_file_path'] == uploaded[0][0]
        assert payload['source_file_size'] == len(b'<html></html>')
        assert payload['source_format'] == 'html'

    def test_bad_extension_415(self, bff):
        mod, stub, uploaded, _ = bff
        result = mod.ReportStudioCommandService.import_document(
            _FakeUpload(b'x', 'report.exe', 'application/octet-stream'))
        assert result[1] == 415
        assert stub.calls == []

    def test_content_type_mismatch_415(self, bff):
        mod, stub, _, _ = bff
        result = mod.ReportStudioCommandService.import_document(
            _FakeUpload(b'<html></html>', 'report.html', 'image/png'))
        assert result[1] == 415
        assert stub.calls == []

    def test_oversize_413(self, bff, monkeypatch):
        mod, stub, uploaded, _ = bff
        import shared.infrastructure.config as cfg
        monkeypatch.setattr(cfg.BaseConfig, 'REPORT_STUDIO_UPLOAD_MAX_MB', 1)
        result = mod.ReportStudioCommandService.import_document(
            _FakeUpload(b'a' * (1024 * 1024 + 1), 'report.ppt'.replace('.ppt', '.pptx'),
                        'application/vnd.openxmlformats-officedocument.presentationml.presentation'))
        assert result[1] == 413
        assert uploaded == []

    def test_serialized_payload_over_grpc_limit_413(self, bff, monkeypatch):
        """文件没过上传闸门、但 JSON 序列化后超 gRPC 上限 → 413，不是 500。"""
        mod, stub, uploaded, _ = bff
        import shared.infrastructure.config as cfg
        monkeypatch.setattr(cfg.BaseConfig, 'GRPC_MAX_MESSAGE_MB', 1)
        # 400k 汉字 = 1.2MiB（< 50MB 文件上限），序列化后超 1MB 传输上限
        content = ('中' * (400 * 1024)).encode('utf-8')
        result = mod.ReportStudioCommandService.import_document(
            _FakeUpload(content, 'report.md', 'text/markdown'))
        assert result[1] == 413, result
        assert stub.calls == [], '超限请求不得发到 gRPC'

    def test_empty_upload_400(self, bff):
        mod, stub, _, _ = bff
        result = mod.ReportStudioCommandService.import_document(
            _FakeUpload(b'', 'report.md', 'text/markdown'))
        assert result[1] == 400

    def test_db_failure_deletes_uploaded_object(self, bff):
        mod, stub, uploaded, deleted = bff
        stub.responses['CreateStudioUploadDocument'] = (False, '创建文档失败', {}, 500)
        result = mod.ReportStudioCommandService.import_document(
            _FakeUpload(b'<html></html>', 'report.html', 'text/html'))
        assert result[1] == 500
        assert deleted == [uploaded[0][0]], '建档失败必须清理已上传对象'

    def test_download_source_headers(self, bff):
        mod, stub, _, _ = bff
        stub.responses['GetStudioDocument'] = (
            True, 'ok',
            {'doc_id': 'd1', 'title': '中文标题', 'source_format': 'html',
             'source_file_path': 'oss://reports/studio_uploads/1.html'}, 0)
        result = mod.ReportStudioQueryService.download_source('d1')
        assert result['binary'] is True
        assert result['content'] == b'<html>report</html>'
        headers = result['headers']
        assert headers['X-Content-Type-Options'] == 'nosniff'
        assert 'sandbox' in headers['Content-Security-Policy']
        assert headers['Content-Disposition'].startswith('attachment;')
        assert 'filename*=UTF-8' in headers['Content-Disposition']

    def test_download_source_without_file_400(self, bff):
        mod, stub, _, _ = bff
        stub.responses['GetStudioDocument'] = (
            True, 'ok', {'doc_id': 'd1', 'source_file_path': None}, 0)
        result = mod.ReportStudioQueryService.download_source('d1')
        assert result[1] == 400


# ==================== 网关路由：新增 3 端点 + 权限门 ====================

class TestGatewayRoutesInt1763:
    @staticmethod
    def _app(permissions):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import api_gateway.routes.report_studio_bp as bp_mod

        app = FastAPI()

        @app.middleware('http')
        async def _inject_perms(request, call_next):
            request.state.permissions = list(permissions)
            request.state.user_id = 1
            return await call_next(request)

        app.include_router(bp_mod.router, prefix='/api/v1/report-studio')
        return bp_mod, TestClient(app, raise_server_exceptions=False)

    def test_list_documents_delegates_filters(self, monkeypatch):
        from api_gateway.utils.response import success_response
        calls = []

        class _FakeQ:
            @staticmethod
            def list_documents(params):
                calls.append(params)
                return success_response({'items': [], 'total': 0})

        bp_mod, client = self._app(['report:read'])
        monkeypatch.setattr(bp_mod, 'ReportStudioQueryService', _FakeQ)
        resp = client.get('/api/v1/report-studio/documents',
                          params={'report_id': 5, 'source_type': 'platform_report',
                                  'parent_doc_id': 'p1', 'limit': 20, 'offset': 0})
        assert resp.status_code == 200
        assert calls[0]['report_id'] == 5
        assert calls[0]['source_type'] == 'platform_report'
        assert calls[0]['parent_doc_id'] == 'p1'

    def test_import_multipart_fields(self, monkeypatch):
        from api_gateway.utils.response import success_response
        captured = {}

        class _FakeC:
            @staticmethod
            def import_document(file, title=None, task_id=None, fmt=None):
                captured.update({'filename': file.filename, 'title': title,
                                 'task_id': task_id, 'fmt': fmt})
                return success_response({'doc_id': 'd1'})

        bp_mod, client = self._app(['report:studio:create'])
        monkeypatch.setattr(bp_mod, 'ReportStudioCommandService', _FakeC)
        resp = client.post('/api/v1/report-studio/import',
                           files={'file': ('report.md', b'# md', 'text/markdown')},
                           data={'title': '对比报告', 'task_id': '12', 'format': 'md'})
        assert resp.status_code == 200
        assert captured == {'filename': 'report.md', 'title': '对比报告',
                            'task_id': '12', 'fmt': 'md'}

    def test_import_requires_studio_create(self):
        bp_mod, client = self._app(['report:read'])
        resp = client.post('/api/v1/report-studio/import',
                           files={'file': ('report.md', b'# md', 'text/markdown')})
        assert resp.status_code == 403

    def test_source_download_endpoint(self, monkeypatch):
        bp_mod, client = self._app(['report:read'])

        class _FakeQ:
            @staticmethod
            def download_source(doc_id):
                return {'binary': True, 'content': b'<html></html>',
                        'mime_type': 'text/html', 'filename': 'doc.html',
                        'headers': {'X-Content-Type-Options': 'nosniff'}}

        monkeypatch.setattr(bp_mod, 'ReportStudioQueryService', _FakeQ)
        resp = client.get('/api/v1/report-studio/documents/d1/source')
        assert resp.status_code == 200
        assert resp.headers['x-content-type-options'] == 'nosniff'
        assert resp.headers['content-disposition'].startswith('attachment;')
        assert resp.content == b'<html></html>'


# ==================== 返工 P2：gRPC 单条消息上限 ====================

def _expected_grpc_limit():
    from shared.infrastructure.config import BaseConfig
    return max(int(BaseConfig.GRPC_MAX_MESSAGE_MB), 1) * 1024 * 1024


class TestGrpcMessageLimitRework:
    """审计 P2：md 正文 >4MiB 必须能过，而不是 RESOURCE_EXHAUSTED → HTTP 500。

    网关按 REPORT_STUDIO_UPLOAD_MAX_MB（50MB）放行后，markdown 正文整段进
    ``StudioDocumentRequest.data``；report_service 的 grpc.server 原先没传
    options，卡在 grpcio 默认 4MiB 收包上限。这里钉死三件事：
    - 服务端 options 与共享客户端 channel 同口径且不低于上传上限；
    - start_grpc_server 真的把 options 传给 grpc.server；
    - 真实 in-process 往返 5MiB 正文成功，并以「不带 options 的服务端」作对照，
      证明用例确实踩在 4MiB 边界上（否则对照不会报 RESOURCE_EXHAUSTED）。
    """

    def test_server_options_cover_upload_cap(self):
        from shared.infrastructure.config import BaseConfig
        from report_service.interfaces.grpc.server import _server_options

        opts = dict(_server_options())
        limit = opts['grpc.max_receive_message_length']
        assert opts['grpc.max_send_message_length'] == limit
        assert limit > 4 * 1024 * 1024, '未放大就还是 grpcio 默认 4MiB'
        assert limit >= BaseConfig.REPORT_STUDIO_UPLOAD_MAX_MB * 1024 * 1024, \
            'gRPC 上限低于上传上限 → 大 md 过网关仍被服务端拒收'
        assert limit == _expected_grpc_limit()

    def test_start_grpc_server_passes_options(self, monkeypatch):
        import shared.models.database as database
        import report_service.interfaces.grpc.server as server_mod

        captured = {}

        class _FakeServer:
            def __getattr__(self, name):
                return lambda *a, **k: None

        def _fake_grpc_server(*args, **kwargs):
            captured['options'] = kwargs.get('options')
            return _FakeServer()

        monkeypatch.setattr(database, 'init_db', lambda **kwargs: None, raising=False)
        monkeypatch.setattr(server_mod.grpc, 'server', _fake_grpc_server)
        server_mod.start_grpc_server(port=1)

        opts = dict(captured.get('options') or [])
        assert opts.get('grpc.max_receive_message_length') == _expected_grpc_limit()
        assert opts.get('grpc.max_send_message_length') == _expected_grpc_limit()
        assert opts['grpc.max_receive_message_length'] > 4 * 1024 * 1024

    # -- 真实 in-process gRPC 往返 ------------------------------------

    @staticmethod
    def _serve(options):
        """起一个只实现 CreateStudioUploadDocument 的临时服务端。"""
        from concurrent import futures
        import grpc as _grpc
        from shared.proto import report_service_pb2 as pb
        from shared.proto import report_service_pb2_grpc as pb_grpc

        class _Recording(pb_grpc.ReportStudioServiceServicer):
            def __init__(self):
                self.received = []

            def CreateStudioUploadDocument(self, request, context):
                self.received.append(len(request.data.encode('utf-8')))
                return pb.StudioResponse(success=True, message='ok', code=0,
                                         data='{"doc_id": "d1"}')

        servicer = _Recording()
        server = _grpc.server(futures.ThreadPoolExecutor(max_workers=2), options=options)
        pb_grpc.add_ReportStudioServiceServicer_to_server(servicer, server)
        port = server.add_insecure_port('127.0.0.1:0')
        server.start()
        return server, port, servicer

    @staticmethod
    def _call_upload(port, markdown, timeout=30):
        import grpc as _grpc
        from shared.clients._grpc_channels import _channel_options
        from shared.proto import report_service_pb2 as pb
        from shared.proto import report_service_pb2_grpc as pb_grpc
        from shared.utils.grpc_json import dumps as _j

        with _grpc.insecure_channel(f'127.0.0.1:{port}', options=_channel_options()) as ch:
            stub = pb_grpc.ReportStudioServiceStub(ch)
            return stub.CreateStudioUploadDocument(
                pb.StudioDocumentRequest(data=_j({'markdown_content': markdown})),
                timeout=timeout)

    def test_roundtrip_over_4mib_markdown(self):
        from report_service.interfaces.grpc.server import _server_options

        markdown = 'x' * (5 * 1024 * 1024)  # 5MiB，超过 grpcio 默认 4MiB
        server, port, servicer = self._serve(_server_options())
        try:
            resp = self._call_upload(port, markdown)
        finally:
            server.stop(0)
        assert resp.success is True
        assert servicer.received[0] > 4 * 1024 * 1024, '正文没真的送到服务端'

    def test_default_server_rejects_over_4mib(self):
        """对照（P2 现场）：不带 options 的服务端正是 4MiB 拒收的来源。"""
        import grpc as _grpc

        server, port, _servicer = self._serve(None)
        try:
            with pytest.raises(_grpc.RpcError) as ei:
                self._call_upload(port, 'x' * (5 * 1024 * 1024))
        finally:
            server.stop(0)
        assert ei.value.code() == _grpc.StatusCode.RESOURCE_EXHAUSTED


# ==================== 返工 P3-2：引导链登记 ====================

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_MIGRATION_REL = 'scripts/migrations/202610/alter_report_studio_sources.py'
_ANALYZE_REL = 'scripts/migrations/202610/analyze_stale_statistics_int1741.py'
_BOOTSTRAP_PATH = os.path.join(PROJECT_ROOT, 'docker', 'db_bootstrap_entrypoint.py')


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location('int1763_db_bootstrap', _BOOTSTRAP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestBootstrapChainRegistration:
    """只写迁移脚本不接引导链 = 存量库永远缺列（INT-1565 同类根因）。

    本卡合入 V9.7.31 时 ``db_bootstrap_entrypoint.py`` 必然冲突（与 INT-1783
    的步骤号/位置重叠），一条断言能挡住解冲突解漏。
    """

    def test_migration_file_exists(self):
        assert os.path.isfile(os.path.join(PROJECT_ROOT, _MIGRATION_REL)), \
            f'迁移脚本不存在：{_MIGRATION_REL}'

    def test_registered_in_bootstrap_with_apply(self):
        steps = [list(step) for step in _load_bootstrap().BOOTSTRAP_STEPS]
        matched = [step for step in steps if _MIGRATION_REL in step]
        assert matched, f'BOOTSTRAP_STEPS 未包含 {_MIGRATION_REL}：存量库不会补 source_type 等列'
        assert '--apply' in matched[0], \
            f'{_MIGRATION_REL} 在引导链中缺少 --apply（只预览不执行）'

    def test_runs_before_analyze_step(self):
        """须排在统计兜底 ANALYZE 之前（该步固定为引导链末步）。"""
        order = [step[1] for step in _load_bootstrap().BOOTSTRAP_STEPS]
        assert _ANALYZE_REL in order, '统计兜底步不见了，引导链被改坏'
        assert order.index(_MIGRATION_REL) < order.index(_ANALYZE_REL)


class TestGatewayToServicerOver4MiB:
    """P2 端到端：>4MiB 的 md 走真实 HTTP 路由 → BFF → 真实 gRPC servicer。

    与上面的纯传输用例互补：这条连网关序列化、路由 multipart、servicer 落库
    一起走，确认 5MiB 正文能真正建成 uploaded_file 文档（原先在 gRPC 收包
    4MiB 处就断，表现为 HTTP 500）。
    """

    def test_import_5mib_markdown_returns_200(self, sqlite_db, monkeypatch):
        from concurrent import futures

        import grpc as _grpc
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from shared.clients._grpc_channels import _channel_options
        from shared.proto import report_service_pb2 as pb
        from shared.proto import report_service_pb2_grpc as pb_grpc
        from shared.utils.grpc_json import dumps as _j, loads as _l
        from report_service.interfaces.grpc.server import _server_options
        from report_service.interfaces.grpc.servicers import StudioServicer
        import api_gateway.application.services.report.report_studio_service as bff_mod
        import api_gateway.routes.report_studio_bp as bp_mod

        server = _grpc.server(futures.ThreadPoolExecutor(max_workers=4),
                              options=_server_options())
        pb_grpc.add_ReportStudioServiceServicer_to_server(StudioServicer(), server)
        port = server.add_insecure_port('127.0.0.1:0')
        server.start()
        channel = _grpc.insecure_channel(f'127.0.0.1:{port}', options=_channel_options())
        try:
            stub = pb_grpc.ReportStudioServiceStub(channel)
            monkeypatch.setattr(bff_mod, 'report_studio_service',
                                type('P', (), {'stub': stub})())

            app = FastAPI()

            @app.middleware('http')
            async def _perms(request, call_next):
                request.state.permissions = ['report:studio:create']
                request.state.user_id = 1
                return await call_next(request)

            app.include_router(bp_mod.router, prefix='/api/v1/report-studio')
            client = TestClient(app, raise_server_exceptions=False)

            md = ('# 大报告\n' + '正文内容 abcdefghij\n' * 200000).encode('utf-8')
            assert len(md) > 4 * 1024 * 1024, '用例没跨过 grpcio 默认 4MiB 边界'
            resp = client.post('/api/v1/report-studio/import',
                               files={'file': ('report.md', md, 'text/markdown')},
                               data={'title': '大报告', 'format': 'md'})
            assert resp.status_code == 200, resp.text
            doc_id = resp.json()['data']['doc_id']

            raw = stub.GetStudioDocument(
                pb.StudioDocumentRequest(data=_j({'doc_id': doc_id})))
            doc = _l(raw.data, {})
            assert doc['source_type'] == 'uploaded_file'
            assert doc['source_format'] == 'md'
            assert doc['markdown_content'].encode('utf-8') == md
        finally:
            channel.close()
            server.stop(0)
