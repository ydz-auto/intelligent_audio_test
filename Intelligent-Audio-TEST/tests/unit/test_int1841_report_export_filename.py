# -*- coding: utf-8 -*-
"""INT-1841 专项：报告导出 `Content-Disposition` 中文文件名 latin-1 编码失败（HTTP 500）。

修复前：`api_gateway/routes/report_bp._handle` 把 report_service 返回的中文文件名
（HTML 分支用报告名拼文件名）原样写进响应头，Starlette 按 latin-1 编码抛
`UnicodeEncodeError`，`POST /api/v1/reports/export {"format":"html"}` 恒 500；
csv/pdf/excel 分支的 ASCII 文件名不触发。

覆盖：
- `_response.content_disposition`：ASCII 兜底名 + `filename*=UTF-8''` 百分号编码
- report_bp 导出路由：HTML（中文文件名）返回 200，响应头可 latin-1 编码
- report_studio_bp 下载路由：同一写法，一并验证
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from urllib.parse import unquote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_gateway.routes._response import content_disposition

CN_FILENAME = ('report_564_环境理解小艺E2E测试任务_2026_9_28 11_44_42 - 测试报告'
               '_20261025.html')


def _parse_filename_star(header):
    """从 Content-Disposition 里取出 filename* 并解码。"""
    marker = "filename*=UTF-8''"
    assert marker in header
    return unquote(header.split(marker, 1)[1])


# ======================================================================
# 工具函数
# ======================================================================

class TestContentDisposition:
    def test_chinese_filename_is_latin1_safe(self):
        header = content_disposition(CN_FILENAME)
        assert header.isascii()
        header.encode('latin-1')  # 原实现此行抛 UnicodeEncodeError
        assert 'filename="export.html"' in header
        assert _parse_filename_star(header) == CN_FILENAME

    def test_ascii_filename_keeps_original_in_fallback(self):
        """ASCII 文件名口径不变：filename= 仍是原名，另加 filename*。"""
        header = content_disposition('reports_export_20261025.csv')
        assert header.isascii()
        assert 'filename="reports_export_20261025.csv"' in header
        assert _parse_filename_star(header) == 'reports_export_20261025.csv'

    def test_missing_filename_uses_fallback(self):
        for value in (None, ''):
            header = content_disposition(value)
            assert header.startswith('attachment; filename="export"')
            assert _parse_filename_star(header) == 'export'

    def test_header_value_has_no_raw_quote_injection(self):
        """文件名里的引号/分号只出现在百分号编码段，不会破坏 filename= 段。"""
        header = content_disposition('a"b;c.html')
        assert header.count('"') == 2
        assert _parse_filename_star(header) == 'a"b;c.html'


# ======================================================================
# 路由层（复刻线上崩溃路径）
# ======================================================================

def _gw_app(router, prefix, permission_middleware):
    from api_gateway.middleware import RequestAdapterMiddleware

    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _inject_permissions(request, call_next):
        request.state.permissions = ['*']
        return await call_next(request)

    app.include_router(router, prefix=prefix)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def report_client():
    from api_gateway.routes.report_bp import router as report_router
    return _gw_app(report_router, '/api/v1/reports', True)


@pytest.fixture()
def studio_client():
    from api_gateway.routes.report_studio_bp import router as studio_router
    return _gw_app(studio_router, '/api/v1/report-studio', True)


def _binary_result(filename, content=b'<html>ok</html>', mime='text/html; charset=utf-8'):
    return {'binary': True, 'content': content,
            'mime_type': mime, 'filename': filename}


class TestReportExportRoute:
    def test_html_export_with_chinese_filename_returns_200(self, report_client, monkeypatch):
        from api_gateway.application.services.report.report_query_sevice import (
            ReportQueryService,
        )

        monkeypatch.setattr(ReportQueryService, 'export',
                            staticmethod(lambda: _binary_result(CN_FILENAME)))
        r = report_client.post('/api/v1/reports/export',
                               json={'ids': [564], 'format': 'html'})
        assert r.status_code == 200, r.text
        assert r.content == b'<html>ok</html>'
        assert r.headers['content-type'].startswith('text/html')
        header = r.headers['content-disposition']
        header.encode('latin-1')
        assert 'filename="export.html"' in header
        assert _parse_filename_star(header) == CN_FILENAME

    @pytest.mark.parametrize('fmt,filename,mime', [
        ('csv', 'reports_export_20261025.csv', 'text/csv'),
        ('excel', 'reports_export_20261025.xlsx',
         'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
        ('pdf', 'reports_export_20261025.pdf', 'application/pdf'),
    ])
    def test_ascii_branches_unchanged(self, report_client, monkeypatch,
                                      fmt, filename, mime):
        """回归：csv/pdf/excel 仍 200，头部仍带原名（ASCII 兜底 + filename*）。"""
        from api_gateway.application.services.report.report_query_sevice import (
            ReportQueryService,
        )

        monkeypatch.setattr(ReportQueryService, 'export',
                            staticmethod(lambda: _binary_result(filename, b'x', mime)))
        r = report_client.post('/api/v1/reports/export',
                               json={'ids': [564], 'format': fmt})
        assert r.status_code == 200
        assert _parse_filename_star(r.headers['content-disposition']) == filename


class TestReportStudioDownloadRoute:
    def test_download_with_chinese_filename_returns_200(self, studio_client, monkeypatch):
        from api_gateway.application.services.report.report_studio_service import (
            ReportStudioQueryService,
        )

        monkeypatch.setattr(ReportStudioQueryService, 'download_export',
                            staticmethod(lambda export_id: _binary_result(CN_FILENAME)))
        r = studio_client.get('/api/v1/report-studio/exports/1/download')
        assert r.status_code == 200, r.text
        header = r.headers['content-disposition']
        header.encode('latin-1')
        assert _parse_filename_star(header) == CN_FILENAME
