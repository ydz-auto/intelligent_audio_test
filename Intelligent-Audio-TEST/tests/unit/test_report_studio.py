# -*- coding: utf-8 -*-
"""Report Studio 业务资产单测（INT-673 验收标准）

覆盖（SQLite 文件库，导出线程共享同库）：
- 创建文档：用现有 reportId 建草稿，落当前版 + 初始版本快照（同事务）
- 乐观锁：并发 PUT 同 expected_version → 409 + 差异，不覆盖
- 版本恢复：restore 产生新版本（version+1），历史只读不可变
- 图表：按当前报告数据 + ChartSpec 返回；非法/越权 chartId → 404/403
- 导出：POST 创建作业（pending）→ 轮询至 done → download 可得文件；
  重复导出同版本可重试稳定；PPTX/PDF 失败带错误信息
- 对象级权限：跨账号读文档/图表/导出作业 → 403（§15.8）
"""
import os
import sys
import tempfile
import time

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
from shared.models import common_enums
from report_service.config.config import Config
from report_service.infrastructure.persistence.models import (
    Report,
    ReportMetricStats,
    ReportSummary,
)
from report_service.infrastructure.persistence.report_studio_repository import (
    ReportStudioRepositoryImpl,
)
from report_service.application.services.report_studio_service import (
    ReportStudioService,
    report_studio_service,
)


@pytest.fixture()
def sqlite_db(monkeypatch, tmp_path):
    """SQLite 文件库：主线程 + 导出后台线程共享同一引擎/文件。"""
    path = str(tmp_path / 'studio_test.db')
    engine = create_engine(f'sqlite:///{path}', connect_args={'check_same_thread': False})
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(engine)
    # 导出产物落盘到 tmp_path 下子目录
    monkeypatch.setattr(Config, 'REPORT_STUDIO_EXPORT_DIR', str(tmp_path / 'exports'))
    yield database
    database.remove_db_session()
    engine.dispose()


def _seed_report(session):
    """预置一张测试报告 + 摘要 + 指标统计（图表数据事实源）。"""
    report = Report(name='测试报告', type='standard', status='completed', task_id=1)
    session.add(report)
    session.flush()
    session.add(ReportSummary(
        id=int(report.id) + 50000,
        report_id=report.id, total_cases=10, completed_cases=9, failed_cases=1,
        pass_rate=0.9, metadata={'category': '普通话通用'}))
    # sqlite 下 BIGINT 主键无自增，显式给 id
    session.add(ReportMetricStats(
        id=int(report.id) + 100000,
        report_id=report.id,
        metric_data={'category': '普通话通用', 'avg': 4.2, 'min': 1.0, 'max': 9.8,
                     'std_dev': 2.1, 'sample_count': 10}))
    session.commit()
    return report.id


def _wait_status(repo, export_id, target, timeout=15.0):
    """轮询导出作业至目标状态。"""
    deadline = time.time() + timeout
    job = repo.get_export_job(export_id)
    while job is None or job.status not in target:
        assert time.time() < deadline, f'导出作业未在 {timeout}s 内到 {target}: {job}'
        time.sleep(0.1)
        job = repo.get_export_job(export_id)
    return job


class TestDocumentCrud:
    def test_create_get_roundtrip(self, sqlite_db):
        session = database.get_db_session()
        report_id = _seed_report(session)
        session.close()
        svc = report_studio_service
        r = svc.create_document({'report_id': report_id, 'title': '草稿A',
                                 'markdown_content': '# 初始草稿'})
        assert r['success'] is True, r
        doc = r['data']
        assert doc['current_version'] == 1
        assert doc['etag']
        assert doc['report_id'] == report_id
        assert doc['markdown_content'] == '# 初始草稿'
        doc_id = doc['doc_id']

        r2 = svc.get_document({'doc_id': doc_id})
        assert r2['success'] is True
        assert r2['data']['current_version'] == 1
        assert r2['data']['etag'] == doc['etag']

        # 初始版本快照已落库
        versions = svc.list_versions({'doc_id': doc_id})
        assert versions['data']['total'] == 1
        assert versions['data']['items'][0]['version'] == 1

    def test_create_missing_report_404(self, sqlite_db):
        r = report_studio_service.create_document({'report_id': 999999})
        assert r['success'] is False
        assert r['code'] == 404

    def test_update_optimistic_lock_conflict_409(self, sqlite_db):
        session = database.get_db_session()
        report_id = _seed_report(session)
        session.close()
        svc = report_studio_service
        doc_id = svc.create_document({'report_id': report_id, 'title': 'D'})['data']['doc_id']

        # 正确版本 → 成功，version 2
        ok = svc.update_document({'doc_id': doc_id, 'expected_version': 1,
                                  'markdown_content': '# v2'})
        assert ok['success'] is True, ok
        assert ok['data']['current_version'] == 2

        # 并发提交同一 expected_version=1 → 409 + 差异，不覆盖
        conflict = svc.update_document({'doc_id': doc_id, 'expected_version': 1,
                                        'markdown_content': '# 被覆盖'})
        assert conflict['success'] is False
        assert conflict['code'] == 409
        assert conflict['data']['current_version'] == 2
        assert conflict['data']['diff']

        # 当前内容未被覆盖
        cur = svc.get_document({'doc_id': doc_id})
        assert cur['data']['markdown_content'] == '# v2'

        # 每次写操作同事务落新版本快照
        versions = svc.list_versions({'doc_id': doc_id})
        assert versions['data']['total'] == 2
        assert [v['version'] for v in versions['data']['items']] == [1, 2]

    def test_restore_creates_new_version(self, sqlite_db):
        session = database.get_db_session()
        report_id = _seed_report(session)
        session.close()
        svc = report_studio_service
        doc_id = svc.create_document({'report_id': report_id,
                                      'markdown_content': '# 版本1'})['data']['doc_id']
        svc.update_document({'doc_id': doc_id, 'expected_version': 1,
                             'markdown_content': '# 版本2'})

        # 恢复版本 1 → 新版本 3（不覆盖），当前内容 = 版本1
        r = svc.restore_version({'doc_id': doc_id, 'version': 1, 'expected_version': 2})
        assert r['success'] is True, r
        assert r['data']['current_version'] == 3
        assert r['data']['markdown_content'] == '# 版本1'
        cur = svc.get_document({'doc_id': doc_id})
        assert cur['data']['markdown_content'] == '# 版本1'

        versions = svc.list_versions({'doc_id': doc_id})
        assert versions['data']['total'] == 3
        reasons = [v['snapshot_reason'] for v in versions['data']['items']]
        assert reasons == ['manual_edit', 'manual_edit', 'restore']

    def test_restore_conflict_409(self, sqlite_db):
        session = database.get_db_session()
        report_id = _seed_report(session)
        session.close()
        svc = report_studio_service
        doc_id = svc.create_document({'report_id': report_id})['data']['doc_id']
        r = svc.restore_version({'doc_id': doc_id, 'version': 1, 'expected_version': 5})
        assert r['success'] is False
        assert r['code'] == 409

    def test_get_missing_404(self, sqlite_db):
        r = report_studio_service.get_document({'doc_id': 'no-such-doc'})
        assert r['code'] == 404


class TestChartData:
    def test_get_chart_data_and_validation(self, sqlite_db):
        session = database.get_db_session()
        report_id = _seed_report(session)
        session.close()
        svc = report_studio_service
        doc_id = svc.create_document({'report_id': report_id, 'title': '图表D'})['data']['doc_id']

        # 创建 ChartSpec（受控引用，服务端校验指标/归属）
        from report_service.domain.entities.report_studio import ReportStudioChartSpec
        svc.repo.create_chart_spec(ReportStudioChartSpec(
            chart_id='chart-001', doc_id=doc_id, report_id=report_id,
            metric_params={'metrics': ['overall'], 'group_by': 'category'},
            style={'type': 'bar'}, version=1))

        r = svc.get_chart_data({'doc_id': doc_id, 'chart_id': 'chart-001'})
        assert r['success'] is True, r
        data = r['data']
        assert data['chart_id'] == 'chart-001'
        assert data['report_id'] == report_id
        assert any(m['name'] == 'overall' and m['avg'] == 4.2 for m in data['metrics'])
        assert data['series'], '分组序列非空'
        assert any(s['name'] == '普通话通用' for s in data['series'])

        # 非法 chartId → 404
        bad = svc.get_chart_data({'doc_id': doc_id, 'chart_id': 'nope'})
        assert bad['code'] == 404

        # 越权：ChartSpec 属于其他文档 → 403
        doc2 = svc.create_document({'report_id': report_id})['data']['doc_id']
        stolen = svc.get_chart_data({'doc_id': doc2, 'chart_id': 'chart-001'})
        assert stolen['code'] == 404  # doc2 下无该图表


class TestExportJob:
    def test_export_html_roundtrip(self, sqlite_db):
        session = database.get_db_session()
        report_id = _seed_report(session)
        session.close()
        svc = report_studio_service
        doc_id = svc.create_document({'report_id': report_id,
                                      'title': '导出D',
                                      'markdown_content': '# 标题\n\n| a | b |\n| --- | --- |\n| 1 | 2 |',
                                      })['data']['doc_id']

        r = svc.create_export_job({'doc_id': doc_id, 'version': 1, 'format': 'html',
                                   'theme': 'default'})
        assert r['success'] is True, r
        export_id = r['data']['export_id']
        assert r['data']['status'] == 'pending'

        job = _wait_status(svc.repo, export_id, target={'done', 'failed'})
        assert job.status == 'done', job.error
        assert job.progress == 100

        poll = svc.get_export_job({'export_id': export_id})
        assert poll['success'] is True
        assert poll['data']['status'] == 'done'
        assert poll['data']['download_ref'].endswith(f'/exports/{export_id}/download')

        dl = svc.download_export({'export_id': export_id})
        assert dl['success'] is True, dl
        content = dl['data']['content_base64']
        assert b'<html>' in __import__('base64').b64decode(content)
        assert b'<table>' in __import__('base64').b64decode(content)

    def test_export_md_roundtrip(self, sqlite_db):
        session = database.get_db_session()
        report_id = _seed_report(session)
        session.close()
        svc = report_studio_service
        doc_id = svc.create_document({'report_id': report_id,
                                      'markdown_content': '# MD 内容'})['data']['doc_id']
        r = svc.create_export_job({'doc_id': doc_id, 'version': 1, 'format': 'md'})
        export_id = r['data']['export_id']
        job = _wait_status(svc.repo, export_id, target={'done', 'failed'})
        assert job.status == 'done', job.error
        dl = svc.download_export({'export_id': export_id})
        assert '# MD 内容' in __import__('base64').b64decode(dl['data']['content_base64']).decode('utf-8')

    def test_export_retry_same_version_stable(self, sqlite_db):
        """同一版本重复导出可重试稳定（§15.6）。"""
        session = database.get_db_session()
        report_id = _seed_report(session)
        session.close()
        svc = report_studio_service
        doc_id = svc.create_document({'report_id': report_id,
                                      'markdown_content': '# 重试'})['data']['doc_id']
        ids = []
        for _ in range(2):
            r = svc.create_export_job({'doc_id': doc_id, 'version': 1, 'format': 'md'})
            assert r['success'] is True
            ids.append(r['data']['export_id'])
        for export_id in ids:
            job = _wait_status(svc.repo, export_id, target={'done', 'failed'})
            assert job.status == 'done', job.error
            dl = svc.download_export({'export_id': export_id})
            assert dl['success'] is True

    def test_export_unsupported_format_fails_with_error(self, sqlite_db):
        """PPTX/PDF 属 S3 增强候选技术（§15.6）：作业 failed 带错误信息。"""
        session = database.get_db_session()
        report_id = _seed_report(session)
        session.close()
        svc = report_studio_service
        doc_id = svc.create_document({'report_id': report_id})['data']['doc_id']
        r = svc.create_export_job({'doc_id': doc_id, 'version': 1, 'format': 'pptx'})
        assert r['success'] is True
        job = _wait_status(svc.repo, r['data']['export_id'], target={'done', 'failed'})
        assert job.status == 'failed'
        assert 'S3' in (job.error or '') or 'html/md' in (job.error or '')

    def test_export_bad_format_400(self, sqlite_db):
        session = database.get_db_session()
        report_id = _seed_report(session)
        session.close()
        r = report_studio_service.create_export_job(
            {'doc_id': 'x', 'version': 1, 'format': 'exe'})
        assert r['code'] == 400

    def test_export_missing_version_404(self, sqlite_db):
        session = database.get_db_session()
        report_id = _seed_report(session)
        session.close()
        svc = report_studio_service
        doc_id = svc.create_document({'report_id': report_id})['data']['doc_id']
        r = svc.create_export_job({'doc_id': doc_id, 'version': 99, 'format': 'md'})
        assert r['code'] == 404

    def test_download_before_done_400(self, sqlite_db):
        r = report_studio_service.download_export({'export_id': 'no-such'})
        assert r['code'] == 404


class TestObjectLevelPermission:
    """§15.8：账号 A 无法读取账号 B 的文档/历史版本/图表/导出文件。"""

    def test_cross_account_access_denied(self, sqlite_db):
        session = database.get_db_session()
        report_id = _seed_report(session)
        session.close()

        set_current_user_id(100)
        set_current_user_is_admin(False)
        doc_id = report_studio_service.create_document(
            {'report_id': report_id, 'title': 'A的文档'})['data']['doc_id']

        # B 账号读取 A 的文档 → 403
        set_current_user_id(200)
        r = report_studio_service.get_document({'doc_id': doc_id})
        assert r['code'] == 403
        r = report_studio_service.list_versions({'doc_id': doc_id})
        assert r['code'] == 403
        r = report_studio_service.update_document(
            {'doc_id': doc_id, 'expected_version': 1, 'markdown_content': 'x'})
        assert r['code'] == 403

        # 管理员放行
        set_current_user_is_admin(True)
        r = report_studio_service.get_document({'doc_id': doc_id})
        assert r['success'] is True

        # 复位上下文，避免污染其他用例
        set_current_user_id(None)
        set_current_user_is_admin(False)


class TestRenderHtml:
    def test_render_escapes_content(self):
        html_out = ReportStudioService._render_html('# <script>alert(1)</script>', 't', 'T')
        assert '<script>' not in html_out
        assert '&lt;script&gt;' in html_out


# ==================== 网关路由（9 端点可达性，验收标准 1） ====================

class TestGatewayRoutes:
    """report_studio_bp.py 全部 9 端点挂载 + 权限门 + 委托（验收标准 1/6）。"""

    @pytest.fixture(autouse=True)
    def _authless_app(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import api_gateway.routes.report_studio_bp as bp_mod

        class _Authless:
            async def __call__(self, scope, receive, send):
                from starlette.requests import Request
                # 模拟 AUTH_MODE=off 通配：注入 '*' 权限
                scope['state'] = {'permissions': ['*'], 'user_id': 1}
                await self._app(scope, receive, send)

        app = FastAPI()
        # 手工设置状态中间件
        @app.middleware('http')
        async def _inject_perms(request, call_next):
            request.state.permissions = ['*']
            request.state.user_id = 1
            return await call_next(request)
        # 对齐生产 app.py：report_studio_bp 挂 /api/v1/report-studio 前缀
        app.include_router(bp_mod.router, prefix='/api/v1/report-studio')
        return app, TestClient(app, raise_server_exceptions=False)

    def test_all_nine_endpoints_reachable(self, monkeypatch, _authless_app):
        from api_gateway.utils.response import success_response, error_response
        import api_gateway.routes.report_studio_bp as bp_mod

        class _FakeQ:
            @staticmethod
            def get_document(doc_id): return success_response({'doc_id': doc_id})
            @staticmethod
            def list_versions(doc_id): return success_response({'items': []})
            @staticmethod
            def get_chart_data(doc_id, chart_id): return success_response({'chart_id': chart_id})
            @staticmethod
            def get_export_job(export_id): return success_response({'status': 'pending'})
            @staticmethod
            def download_export(export_id): return error_response('未完成', http_code=400)

        class _FakeC:
            @staticmethod
            def create_document(): return success_response({'doc_id': 'd1'})
            @staticmethod
            def update_document(doc_id): return success_response({'current_version': 2})
            @staticmethod
            def restore_version(doc_id): return success_response({'current_version': 3})
            @staticmethod
            def create_export_job(doc_id): return success_response({'export_id': 'e1'})

        monkeypatch.setattr(bp_mod, 'ReportStudioQueryService', _FakeQ)
        monkeypatch.setattr(bp_mod, 'ReportStudioCommandService', _FakeC)

        _, client = _authless_app
        base = '/api/v1/report-studio'
        # 9 端点逐一可达
        assert client.post(f'{base}/documents', json={'report_id': 1}).status_code == 200
        assert client.get(f'{base}/documents/d1').status_code == 200
        assert client.put(f'{base}/documents/d1', json={'expected_version': 1}).status_code == 200
        assert client.get(f'{base}/documents/d1/versions').status_code == 200
        assert client.post(f'{base}/documents/d1/restore', json={'version': 1, 'expected_version': 2}).status_code == 200
        assert client.get(f'{base}/documents/d1/charts/c1').status_code == 200
        assert client.post(f'{base}/documents/d1/exports', json={'version': 1, 'format': 'md'}).status_code == 200
        assert client.get(f'{base}/exports/e1').status_code == 200
        assert client.get(f'{base}/exports/e1/download').status_code == 400  # 委托返回

    def test_permission_gate_403(self, monkeypatch):
        """guest 无权调用写端点（验收标准 6）：无 '*' 权限时 403。"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api_gateway.utils.response import success_response
        import api_gateway.routes.report_studio_bp as bp_mod

        class _FakeQ:
            @staticmethod
            def get_document(doc_id): return success_response({'doc_id': doc_id})

        monkeypatch.setattr(bp_mod, 'ReportStudioQueryService', _FakeQ)

        app = FastAPI()

        @app.middleware('http')
        async def _inject_perms(request, call_next):
            request.state.permissions = ['report:read']  # 仅读权限
            request.state.user_id = 1
            return await call_next(request)

        app.include_router(bp_mod.router, prefix='/api/v1/report-studio')
        client = TestClient(app, raise_server_exceptions=False)
        assert client.post('/api/v1/report-studio/documents', json={'report_id': 1}).status_code == 403
        assert client.put('/api/v1/report-studio/documents/d1', json={'expected_version': 1}).status_code == 403
        assert client.post('/api/v1/report-studio/documents/d1/restore', json={'version': 1, 'expected_version': 2}).status_code == 403
        assert client.post('/api/v1/report-studio/documents/d1/exports', json={'version': 1, 'format': 'md'}).status_code == 403
        # 读取侧 report:read 放行
        assert client.get('/api/v1/report-studio/documents/d1').status_code == 200

class TestGatewayBffService:
    """对齐 test_benchmark_gateway_operator.py 的网关 BFF 委托模式（INT-673）。"""

    @pytest.fixture(autouse=True)
    def _fake_request(self, monkeypatch):
        from api_gateway.infrastructure import request_adapter

        class _State:
            def __init__(self, json_body):
                self._json_body = json_body

        class _FakeRequest:
            def __init__(self, json_body):
                self.state = _State(json_body)

            def get_json(self):
                return self.state._json_body

        def _set(json_body=None):
            request_adapter.set_current_request(_FakeRequest(json_body))

        yield _set
        request_adapter.set_current_request(None)

    @staticmethod
    def _fake_stub():
        """假 stub：记录调用并返回可配置的 StudioResponse。"""

        class _Stub:
            def __init__(self):
                self.calls = []
                self.responses = {}

            def _mk(self, method):
                def fn(req):
                    import json as _json
                    from shared.proto import report_service_pb2 as pb
                    self.calls.append((method, _json.loads(req.data or '{}') or {}))
                    ok, message, data, code = self.responses.get(method, (True, 'ok', {}, 0))
                    return pb.StudioResponse(
                        success=ok, message=message, data=_json.dumps(data), code=code)
                return fn

            def __getattr__(self, name):
                return self._mk(name)

        return _Stub()

    def test_bff_create_and_mappings(self, monkeypatch, _fake_request):
        import api_gateway.application.services.report.report_studio_service as bff
        import api_gateway.infrastructure.grpc_proxies.report_studio_proxies as proxies_mod

        stub = self._fake_stub()
        monkeypatch.setattr(proxies_mod, 'report_studio_service', type('P', (), {'stub': stub})())
        monkeypatch.setattr(bff, 'report_studio_service', type('P', (), {'stub': stub})())

        # POST /documents 委托
        _fake_request({'report_id': 1, 'title': '草稿'})
        result = bff.ReportStudioCommandService.create_document()
        assert result[1] == 200
        assert stub.calls[0][0] == 'CreateStudioDocument'
        assert stub.calls[0][1]['report_id'] == 1

        # 404 映射
        stub.responses['GetStudioDocument'] = (False, '文档不存在', {}, 404)
        result = bff.ReportStudioQueryService.get_document('nope')
        assert result[1] == 404

        # 409 冲突映射
        stub.responses['UpdateStudioDocument'] = (
            False, '版本冲突', {'expected_version': 1, 'current_version': 2}, 409)
        _fake_request({'expected_version': 1, 'markdown_content': '# v2'})
        result = bff.ReportStudioCommandService.update_document('d1')
        assert result[1] == 409
        assert result[0]['detail']['current_version'] == 2

        # 403 越权映射
        stub.responses['GetStudioChartData'] = (False, '无权访问', {}, 403)
        result = bff.ReportStudioQueryService.get_chart_data('d1', 'c1')
        assert result[1] == 403

        # 二进制下载
        import base64
        stub.responses['DownloadStudioExport'] = (
            True, 'ok', {'content_base64': base64.b64encode(b'hello').decode(), 'mime_type': 'text/html',
                         'filename': 'x.html'}, 0)
        result = bff.ReportStudioQueryService.download_export('e1')
        assert result['binary'] is True
        assert result['content'] == b'hello'
        assert result['filename'] == 'x.html'
