# -*- coding: utf-8 -*-
"""INT-106 网关 multipart 表单解析与 Flask 兼容代理单测

覆盖：
1. RequestAdapterMiddleware 预解析 multipart/form-data：
   字段 → request.state._form_data，文件 → request.state._files
2. _FormProxy.get Flask 兼容 type 形参（原缺陷：缺 type 形参 →
   chunk 上传端点 400 `_FormProxy.get() got an unexpected keyword argument 'type'`）
3. _FilesProxy 返回 Flask FileStorage 语义包装（同步 read / filename / save）
4. 既有 JSON 预解析行为不回归
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_gateway.infrastructure import request_adapter
from api_gateway.infrastructure.request_adapter import request
from api_gateway.middleware import RequestAdapterMiddleware


def _make_app():
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.post('/echo-form')
    def echo_form():
        file_id = request.form.get('file_id')
        chunk_index = request.form.get('chunk_index', type=int)
        total_chunks = request.form.get('total_chunks', type=int)
        task_id = request.form.get('task_id')
        if 'chunk' not in request.files:
            return {'error': 'missing chunk'}
        chunk_file = request.files['chunk']
        content = chunk_file.read()
        return {
            'file_id': file_id,
            'chunk_index': chunk_index,
            'total_chunks': total_chunks,
            'task_id': task_id,
            'filename': chunk_file.filename,
            'content': content.decode('utf-8'),
            'ct': chunk_file.content_type,
        }

    @app.post('/echo-json')
    def echo_json():
        return {'body': request.get_json()}

    return app


@pytest.fixture()
def client():
    return TestClient(_make_app())


class TestMultipartPreparse:

    def test_chunk_upload_form_fields_and_file(self, client):
        """分片上传全链形态：表单字段（含 type=int 转换）+ 分片文件。"""
        resp = client.post('/echo-form',
                           data={'file_id': 'f-1', 'chunk_index': '2',
                                 'total_chunks': '5', 'task_id': 't-1'},
                           files={'chunk': ('part2.wav', b'BIN2', 'audio/wav')})
        assert resp.status_code == 200
        body = resp.json()
        assert body['file_id'] == 'f-1'
        assert body['chunk_index'] == 2
        assert body['total_chunks'] == 5
        assert body['task_id'] == 't-1'
        assert body['filename'] == 'part2.wav'
        assert body['content'] == 'BIN2'
        assert body['ct'] == 'audio/wav'

    def test_type_coerce_failure_returns_default(self, client):
        """type 转换失败回退 default（Flask 语义），不再抛 TypeError。"""
        resp = client.post('/echo-form',
                           data={'file_id': 'f-1', 'chunk_index': 'not-a-number',
                                 'total_chunks': '5', 'task_id': 't-1'},
                           files={'chunk': ('p.wav', b'B', 'audio/wav')})
        assert resp.status_code == 200
        assert resp.json()['chunk_index'] is None

    def test_missing_file_reports_missing(self, client):
        resp = client.post('/echo-form',
                           data={'file_id': 'f-1', 'chunk_index': '0',
                                 'total_chunks': '1', 'task_id': 't-1'})
        assert resp.status_code == 200
        assert resp.json() == {'error': 'missing chunk'}

    def test_json_body_preparse_unaffected(self, client):
        resp = client.post('/echo-json', json={'a': 1})
        assert resp.json() == {'body': {'a': 1}}


class TestFormProxyUnit:

    def _proxy_with(self, form_data):
        class _Req:
            class state:
                _form_data = form_data
        return request_adapter._FormProxy(_Req)

    def test_get_without_type(self):
        proxy = self._proxy_with({'a': '1'})
        assert proxy.get('a') == '1'
        assert proxy.get('missing', 'dft') == 'dft'

    def test_get_with_type(self):
        proxy = self._proxy_with({'idx': '3'})
        assert proxy.get('idx', type=int) == 3

    def test_get_with_type_invalid_returns_default(self):
        proxy = self._proxy_with({'idx': 'x'})
        assert proxy.get('idx', 7, type=int) == 7

    def test_contains_and_to_dict(self):
        proxy = self._proxy_with({'a': '1'})
        assert 'a' in proxy
        assert 'b' not in proxy
        assert proxy.to_dict() == {'a': '1'}

    def test_iteration_protocol(self):
        """`for key in request.form` 可迭代（评估维度导入依赖此形态）。"""
        proxy = self._proxy_with({'a': '1', 'b': '2'})
        collected = {k: proxy.get(k) for k in proxy}
        assert collected == {'a': '1', 'b': '2'}
        assert len(proxy) == 2
        assert dict(proxy.items()) == {'a': '1', 'b': '2'}


class TestUploadedFileWrapper:

    def test_save_and_read(self, tmp_path):
        class _FakeUpload:
            filename = 'x.wav'
            name = 'chunk'
            content_type = 'audio/wav'

            def __init__(self):
                import io
                self.file = io.BytesIO(b'WAVDATA')

        first = request_adapter._UploadedFile(_FakeUpload())
        assert first.read() == b'WAVDATA'  # read 消费流（与 Flask FileStorage 一致）

        second = request_adapter._UploadedFile(_FakeUpload())
        assert second.filename == 'x.wav'
        dst = tmp_path / 'out.wav'
        second.save(str(dst))
        assert dst.read_bytes() == b'WAVDATA'
