# -*- coding: utf-8 -*-
"""INT-1525 专项：GET/POST /api/v1/audios 的 tags 过滤参数一律 422。

缺陷（INT-1471 音频域基线核验发现）：
- `GET  /api/v1/audios?tags=INT-996` → 422（to_dict 取到单值 str，List[str] 校验失败）
- `GET  /api/v1/audios?tags=a&tags=b` → 422（重复参数被压成单值 str）
- `POST /api/v1/audios {"tags": [{"name": "INT-996", "mode": "and"}]}` → 422
  （schema 只声明 List[str]，dict 元素校验失败，and/or 语义无法表达）
- `GET /api/v1/audios/ids` 的 AudioIdQuery 同病

修复：
- AudioListQuery / AudioIdQuery 的 tags 放宽为 List[Union[str, dict]]，并把
  单值 str 归一成单元素列表；
- 网关 query 取值对 tags 用 getlist 取全量多值（不再被 to_dict 压成单值）；
- 服务层统一归一为 audio_service 的 [{'name', 'mode'}] 口径，str 按 and，
  dict 保留 or/and。

覆盖：GET 单值/多值、POST dict（and/or）与 str 列表、/ids 同名口径、
无 tags 的回归路径。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_gateway.application.services.audio import audio_query_service
from api_gateway.middleware import RequestAdapterMiddleware
from api_gateway.routes.audio_bp import router as audio_router
from api_gateway.utils.error_handlers import register_error_handlers


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _fake_auth(request, call_next):
        request.state.permissions = ['*']
        return await call_next(request)

    register_error_handlers(app)
    app.include_router(audio_router, prefix='/api/v1/audios', tags=['audios'])
    return app


class _RecordingAcl:
    """记录下游 params 并返回空结果的 ACL 桩。"""

    def __init__(self):
        self.calls = []

    def get_all(self, params):
        self.calls.append(params)
        return {'success': True, 'data': {
            'items': [], 'total': 0, 'page': params.get('page', 1),
            'per_page': params.get('per_page', 10), 'pages': 0, 'stats': {},
        }}

    def get_all_ids(self, params):
        self.calls.append(params)
        return {'success': True, 'data': {'ids': []}}


@pytest.fixture()
def client_and_acl(monkeypatch):
    acl = _RecordingAcl()
    monkeypatch.setattr(audio_query_service, '_audio_acl', acl)
    return TestClient(_make_app()), acl


def _tags_data(acl):
    assert acl.calls, '请求未触达 ACL'
    return acl.calls[-1]['tags_data']


class TestGetAudioListTags:
    """GET /api/v1/audios 的 tags 单值/多值（修复前均 422）。"""

    def test_single_tag_is_accepted_as_and(self, client_and_acl):
        client, acl = client_and_acl
        resp = client.get('/api/v1/audios', params={'page': 1, 'per_page': 20,
                                                    'tags': 'INT-996'})
        assert resp.status_code == 200, resp.text
        assert _tags_data(acl) == [{'name': 'INT-996', 'mode': 'and'}]

    def test_multi_tags_are_collected_from_query(self, client_and_acl):
        client, acl = client_and_acl
        resp = client.get('/api/v1/audios?page=1&per_page=20'
                          '&tags=INT-996&tags=int708_tag_1792294286_22a7b5')
        assert resp.status_code == 200, resp.text
        assert _tags_data(acl) == [
            {'name': 'INT-996', 'mode': 'and'},
            {'name': 'int708_tag_1792294286_22a7b5', 'mode': 'and'},
        ]

    def test_absent_tags_stays_empty(self, client_and_acl):
        client, acl = client_and_acl
        resp = client.get('/api/v1/audios?page=1&per_page=20')
        assert resp.status_code == 200, resp.text
        assert _tags_data(acl) == []


class TestPostAudioListTags:
    """POST /api/v1/audios：str 列表与 {name, mode} dict 列表双口径。"""

    def test_dict_tags_keep_and_or_mode(self, client_and_acl):
        client, acl = client_and_acl
        resp = client.post('/api/v1/audios', json={
            'page': 1, 'per_page': 20,
            'tags': [{'name': 'INT-996', 'mode': 'or'},
                     {'name': 'int708_tag_1792294286_22a7b5', 'mode': 'and'}],
        })
        assert resp.status_code == 200, resp.text
        assert _tags_data(acl) == [
            {'name': 'INT-996', 'mode': 'or'},
            {'name': 'int708_tag_1792294286_22a7b5', 'mode': 'and'},
        ]

    def test_str_tags_default_to_and(self, client_and_acl):
        client, acl = client_and_acl
        resp = client.post('/api/v1/audios', json={
            'page': 1, 'per_page': 20, 'tags': ['INT-996'],
        })
        assert resp.status_code == 200, resp.text
        assert _tags_data(acl) == [{'name': 'INT-996', 'mode': 'and'}]


class TestAudioIdsTags:
    """GET /api/v1/audios/ids（AudioIdQuery）与列表页同口径。"""

    def test_single_tag(self, client_and_acl):
        client, acl = client_and_acl
        resp = client.get('/api/v1/audios/ids?tags=INT-996')
        assert resp.status_code == 200, resp.text
        assert _tags_data(acl) == [{'name': 'INT-996', 'mode': 'and'}]

    def test_multi_tags(self, client_and_acl):
        client, acl = client_and_acl
        resp = client.get('/api/v1/audios/ids?tags=a_tags&tags=b_tags')
        assert resp.status_code == 200, resp.text
        assert _tags_data(acl) == [
            {'name': 'a_tags', 'mode': 'and'},
            {'name': 'b_tags', 'mode': 'and'},
        ]

    def test_post_dict_tags(self, client_and_acl):
        client, acl = client_and_acl
        resp = client.post('/api/v1/audios/ids',
                           json={'tags': [{'name': 'INT-996', 'mode': 'or'}]})
        assert resp.status_code == 200, resp.text
        assert _tags_data(acl) == [{'name': 'INT-996', 'mode': 'or'}]
