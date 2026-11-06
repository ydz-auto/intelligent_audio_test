# -*- coding: utf-8 -*-
"""INT-111 网关 multipart 预解析回灌回归（testserver 级）

覆盖「RequestAdapterMiddleware 开启 + FastAPI 原生 UploadFile 路由」组合。
原缺陷：中间件预解析 multipart 只调 form()（内部走 stream()），请求流被耗尽
且不回灌，下游 FastAPI UploadFile 路由拿到空 body → 422 Field required
（data-transfer import/preview 全挂）。修复：先 body() 缓存原始体，
starlette _CachedRequest 向下游完整回灌，form() 再从缓存体解析。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient

from api_gateway.infrastructure.request_adapter import request
from api_gateway.middleware import RequestAdapterMiddleware


def _make_app():
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.post('/upload')
    def native_upload(file: UploadFile):
        """FastAPI 原生 UploadFile 路由（data-transfer import/preview 同形态）"""
        content = file.file.read()
        return {'filename': file.filename, 'size': len(content),
                'content': content.decode('utf-8')}

    @app.post('/chunk')
    def flask_semantic_chunk():
        """Flask 语义代理路由（chunk 上传同形态，消费中间件预解析 state）"""
        return {
            'file_id': request.form.get('file_id'),
            'filename': request.files['chunk'].filename,
            'content': request.files['chunk'].read().decode('utf-8'),
        }

    return app


@pytest.fixture()
def client():
    return TestClient(_make_app())


class TestMultipartBodyReplay:

    def test_native_uploadfile_route_receives_file(self, client):
        """回归主用例：中间件预解析后，原生 UploadFile 路由仍拿到完整文件"""
        resp = client.post('/upload',
                           files={'file': ('data.zip', b'ZIPBYTES', 'application/zip')})
        assert resp.status_code == 200, resp.text
        assert resp.json() == {'filename': 'data.zip', 'size': 8, 'content': 'ZIPBYTES'}

    def test_two_semantics_coexist_on_same_app(self, client):
        """同 app 上 Flask 语义路由与原生 UploadFile 路由先后访问互不干扰"""
        chunk = client.post('/chunk',
                            data={'file_id': 'f-1'},
                            files={'chunk': ('p.wav', b'BIN', 'audio/wav')})
        assert chunk.status_code == 200, chunk.text
        assert chunk.json() == {'file_id': 'f-1', 'filename': 'p.wav', 'content': 'BIN'}

        upload = client.post('/upload',
                             files={'file': ('x.zip', b'X', 'application/zip')})
        assert upload.status_code == 200, upload.text
        assert upload.json()['content'] == 'X'

    def test_form_fields_alongside_file(self, client):
        """带表单字段的 multipart：原生路由文件不丢（字段仅供 Flask 语义消费）"""
        resp = client.post(
            '/upload',
            data={'note': 'n1'},
            files={'file': ('a.zip', b'AAA', 'application/zip')})
        assert resp.status_code == 200, resp.text
        assert resp.json()['content'] == 'AAA'

    def test_broken_multipart_returns_structured_client_error(self, client):
        """坏 multipart：返回结构化 4xx（FastAPI 侧 400），非饿死空 body 的 422"""
        resp = client.post(
            '/upload',
            content=b'not-multipart-body',
            headers={'content-type': 'multipart/form-data; boundary=broken'})
        assert 400 <= resp.status_code < 500, resp.status_code
