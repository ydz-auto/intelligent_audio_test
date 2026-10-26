# -*- coding: utf-8 -*-
"""INT-2043 专项：音频列表「可见性」筛选（shared/private）服务端生效。

缺陷（INT-2020 第三轮前端 UX 审计实测）：
- `POST /api/v1/audios {"page":1,"perPage":1,"visibility":"private"}` 仍返回全量；
- `GET  /api/v1/audios?page=1&per_page=1&visibility=private` 同样返回全量；
- 即 UI 徽章有筛选态、请求体也带了 visibility，但网关 `AudioListQuery` 无该字段、
  `_parse_list_query_params()` 不透传、audio_service 过滤器不消费 → 静默忽略。

修复：
- 网关 `AudioListQuery` / `AudioIdQuery` 增加 `visibility`（限 shared/private；
  空串按 None = 全部；非法值 422 而不是静默忽略）；
- 服务层两个 parse 函数把 visibility 透传到 gRPC `data`；
- audio_service `apply_audio_list_filters` 按 `Audio.visibility` 追加 where
  （与既有 `visible_condition` 行级过滤叠加：筛选只在本来可见的行内生效）。

覆盖：GET/POST 列表与 /ids 的透传、空值/非法值口径、过滤器 SQL 条件。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api_gateway.application.services.audio import audio_query_service as aqs_mod
from api_gateway.middleware import RequestAdapterMiddleware
from api_gateway.routes.audio_bp import router as audio_router
from api_gateway.utils.error_handlers import register_error_handlers
from audio_service.infrastructure.persistence._audio_query_filters import (
    apply_audio_list_filters,
)
from audio_service.infrastructure.persistence.models import Audio


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
    monkeypatch.setattr(aqs_mod, '_audio_acl', acl)
    return TestClient(_make_app()), acl


def _visibility(acl):
    assert acl.calls, '请求未触达 ACL'
    return acl.calls[-1].get('visibility')


class TestListVisibilityPassThrough:
    """网关 → gRPC 的 visibility 透传（列表）。"""

    def test_post_body_visibility_reaches_acl(self, client_and_acl):
        client, acl = client_and_acl
        resp = client.post('/api/v1/audios',
                           json={'page': 1, 'perPage': 20, 'visibility': 'private'})
        assert resp.status_code == 200, resp.text
        assert _visibility(acl) == 'private'

    def test_get_query_visibility_reaches_acl(self, client_and_acl):
        client, acl = client_and_acl
        resp = client.get('/api/v1/audios?page=1&per_page=20&visibility=shared')
        assert resp.status_code == 200, resp.text
        assert _visibility(acl) == 'shared'

    def test_absent_visibility_is_none(self, client_and_acl):
        client, acl = client_and_acl
        resp = client.get('/api/v1/audios?page=1&per_page=20')
        assert resp.status_code == 200, resp.text
        assert _visibility(acl) is None

    def test_empty_visibility_means_all(self, client_and_acl):
        """筛选 UI 的「全部」= 空值，不能 422，也不应下发空串条件。"""
        client, acl = client_and_acl
        resp = client.get('/api/v1/audios?page=1&per_page=20&visibility=')
        assert resp.status_code == 200, resp.text
        assert _visibility(acl) is None


class TestListVisibilityValidation:
    """非法可见性值直接 422（避免再次出现「静默忽略」）。"""

    @pytest.mark.parametrize('bad', ['publik', 'shared,private', 'PRIVATE'])
    def test_get_invalid_visibility_422(self, client_and_acl, bad):
        client, _acl = client_and_acl
        resp = client.get('/api/v1/audios', params={'visibility': bad})
        assert resp.status_code == 422, resp.text

    def test_post_invalid_visibility_422(self, client_and_acl):
        client, _acl = client_and_acl
        resp = client.post('/api/v1/audios', json={'visibility': 'team'})
        assert resp.status_code == 422, resp.text


class TestIdsVisibilityPassThrough:
    """全选跨页（/audios/ids）与列表同口径，避免筛后全选选中范围外音频。"""

    def test_post_ids_visibility(self, client_and_acl):
        client, acl = client_and_acl
        resp = client.post('/api/v1/audios/ids',
                           json={'page': 1, 'perPage': 10000, 'visibility': 'private'})
        assert resp.status_code == 200, resp.text
        assert _visibility(acl) == 'private'

    def test_get_ids_visibility(self, client_and_acl):
        client, acl = client_and_acl
        resp = client.get('/api/v1/audios/ids?visibility=shared')
        assert resp.status_code == 200, resp.text
        assert _visibility(acl) == 'shared'


@pytest.fixture()
def audio_session():
    """独立 sqlite 会话（只建 audios 表），直接验过滤器 SQL 条件。"""
    engine = create_engine('sqlite://')
    Audio.__table__.create(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed(session):
    for audio_id, vis in [(1, 'private'), (2, 'shared'), (3, 'shared')]:
        session.add(Audio(
            id=audio_id, name=f'a{audio_id}', file_path=f'/tmp/a{audio_id}.wav',
            size=100, duration=1.0, format='wav', audio_type='dry', visibility=vis,
        ))
    session.flush()


def _list_ids(session, **params):
    query = session.query(Audio).filter_by(deleted=False)
    query = apply_audio_list_filters(query, session, params, lambda names: {})
    return sorted(a.id for a in query.all())


class TestAudioServiceVisibilityFilter:
    """audio_service 过滤器：按 visibility 列追加 where，None 不追加。"""

    def test_private_only(self, audio_session):
        _seed(audio_session)
        assert _list_ids(audio_session, visibility='private') == [1]

    def test_shared_only(self, audio_session):
        _seed(audio_session)
        assert _list_ids(audio_session, visibility='shared') == [2, 3]

    def test_none_returns_all(self, audio_session):
        _seed(audio_session)
        assert _list_ids(audio_session) == [1, 2, 3]
        assert _list_ids(audio_session, visibility=None) == [1, 2, 3]
