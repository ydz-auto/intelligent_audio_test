# -*- coding: utf-8 -*-
"""INT-2352 回归：``lookup_scope`` 必须设备表优先、只认未删除行。

缺陷（INT-2332 矩阵 #8 删除路径）：设备参数删除请求没有 body
（``DELETE /api/v1/algorithm/params/{id}``），路由靠 ``lookup_scope``
按行定位作用域。原实现按 ``_SCOPE_SPECS`` 的插入顺序遍历（**api 在前**）
且不过滤 ``deleted``；两张参数表各自独立自增 id、同号行很常见，命中同号
的 ``algorithm_api_params`` 行后就返回 api 作用域，``_device_scope`` 丢弃，
删除后不记版本（行已 ``deleted=t``、``param_change_history`` 无新行）。

契约（与 ``ParamRepository.soft_delete`` 的删除口径一致）：
1. 两表同号且都活跃 → 取设备行（设备表优先）；
2. 设备行已软删、API 同号行活跃 → 取 API 作用域；
3. 设备行活跃、无同号 API 行 → 取设备；
4. 同号行全部软删 → None（宁可不记，不误记到别的作用域）；
5. 映射侧同样只认 ``deleted = false`` 行；
6. 路由端到端：UI 形态的 ``DELETE``（无 body）命中真实 ``lookup_scope``
   → ``record('device', ...)`` 被调用。

用 sqlite 内存库建最小 schema 跑真实 SQL（不做假 session），
只 monkeypatch 会话工厂，不连 PG、不触达 gRPC。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from api_gateway.application.services.algorithm.param_history_service import (  # noqa: E402
    ParamHistoryService,
)
from api_gateway.infrastructure.repositories import (  # noqa: E402
    param_history_repository as repo_mod,
)
from api_gateway.infrastructure.repositories.param_history_repository import (  # noqa: E402
    SCOPE_API,
    SCOPE_DEVICE,
    ParamHistoryRepository,
)
from api_gateway.middleware import RequestAdapterMiddleware  # noqa: E402
from api_gateway.routes import algorithm_bp  # noqa: E402
from api_gateway.routes.algorithm_bp import router as algorithm_router  # noqa: E402

_DEVICE_ID = 42
_API_ID = 9
_ALGO = 'voice_llm'
_SAME_ID = 270

_DDL = (
    "CREATE TABLE algorithm_device_params ("
    " id INTEGER PRIMARY KEY, algorithm_type TEXT, device_id INTEGER,"
    " deleted BOOLEAN NOT NULL DEFAULT 0)",
    "CREATE TABLE algorithm_api_params ("
    " id INTEGER PRIMARY KEY, algorithm_type TEXT, api_id INTEGER,"
    " deleted BOOLEAN NOT NULL DEFAULT 0)",
    "CREATE TABLE param_mappings ("
    " id INTEGER PRIMARY KEY, algorithm_type TEXT, api_id INTEGER,"
    " device_id INTEGER, deleted BOOLEAN NOT NULL DEFAULT 0)",
)


class _Db:
    """sqlite 内存库（StaticPool 保证同库）+ 各表插桩写入。"""

    def __init__(self):
        self.engine = create_engine(
            'sqlite://', connect_args={'check_same_thread': False},
            poolclass=StaticPool)
        with self.engine.begin() as conn:
            for ddl in _DDL:
                conn.execute(text(ddl))
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

    def insert(self, table, **values):
        cols = ', '.join(values)
        marks = ', '.join(f':{c}' for c in values)
        self.session.execute(
            text(f"INSERT INTO {table} ({cols}) VALUES ({marks})"), values)
        self.session.commit()

    def count(self, table, **where):
        clause = ' AND '.join(f"{k} = :{k}" for k in where) or '1 = 1'
        return self.session.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE {clause}"), where
        ).scalar_one()

    def close(self):
        self.session.close()
        self.engine.dispose()


@pytest.fixture()
def db(monkeypatch):
    fake = _Db()
    monkeypatch.setattr(repo_mod, 'get_db_session', lambda: fake.session)
    yield fake
    fake.close()


def _repo() -> ParamHistoryRepository:
    return ParamHistoryRepository()


# ---------- params：设备表优先 / 只认未删除行 ----------

def test_same_id_devices_wins_over_api(db):
    """两表同号且都活跃 → 设备作用域（修复前返回 api，历史被记到别处）。"""
    db.insert('algorithm_device_params', id=_SAME_ID,
              algorithm_type=_ALGO, device_id=_DEVICE_ID, deleted=0)
    db.insert('algorithm_api_params', id=_SAME_ID,
              algorithm_type='api_algo', api_id=_API_ID, deleted=0)
    assert _repo().lookup_scope('params', _SAME_ID) == (
        SCOPE_DEVICE, _DEVICE_ID, _ALGO)


def test_soft_deleted_device_falls_back_to_live_api(db):
    """设备同号行已软删、API 行活跃 → 取 API，不能把 API id 当设备 id。"""
    db.insert('algorithm_device_params', id=_SAME_ID,
              algorithm_type=_ALGO, device_id=_DEVICE_ID, deleted=1)
    db.insert('algorithm_api_params', id=_SAME_ID,
              algorithm_type='api_algo', api_id=_API_ID, deleted=0)
    assert _repo().lookup_scope('params', _SAME_ID) == (
        SCOPE_API, _API_ID, 'api_algo')


def test_live_device_wins_even_when_api_soft_deleted(db):
    db.insert('algorithm_device_params', id=_SAME_ID,
              algorithm_type=_ALGO, device_id=_DEVICE_ID, deleted=0)
    db.insert('algorithm_api_params', id=_SAME_ID,
              algorithm_type='api_algo', api_id=_API_ID, deleted=1)
    assert _repo().lookup_scope('params', _SAME_ID) == (
        SCOPE_DEVICE, _DEVICE_ID, _ALGO)


def test_all_same_id_rows_deleted_returns_none(db):
    """同号行全部软删 → None（宁可漏记，也不再把历史串到别的作用域）。"""
    db.insert('algorithm_device_params', id=_SAME_ID,
              algorithm_type=_ALGO, device_id=_DEVICE_ID, deleted=1)
    db.insert('algorithm_api_params', id=_SAME_ID,
              algorithm_type='api_algo', api_id=_API_ID, deleted=1)
    assert _repo().lookup_scope('params', _SAME_ID) is None


def test_device_row_without_algorithm_type_skipped(db):
    """scope_id 为空的设备行不是有效作用域，继续回落到 API 行。"""
    db.insert('algorithm_device_params', id=_SAME_ID,
              algorithm_type=_ALGO, device_id=None, deleted=0)
    db.insert('algorithm_api_params', id=_SAME_ID,
              algorithm_type='api_algo', api_id=_API_ID, deleted=0)
    assert _repo().lookup_scope('params', _SAME_ID) == (
        SCOPE_API, _API_ID, 'api_algo')


# ---------- mappings：同样只认未删除行 ----------

def test_live_device_mapping_returns_device_scope(db):
    db.insert('param_mappings', id=88, algorithm_type=_ALGO,
              api_id=None, device_id=_DEVICE_ID, deleted=0)
    assert _repo().lookup_scope('mappings', 88) == (
        SCOPE_DEVICE, _DEVICE_ID, _ALGO)


def test_soft_deleted_device_mapping_returns_none(db):
    db.insert('param_mappings', id=88, algorithm_type=_ALGO,
              api_id=None, device_id=_DEVICE_ID, deleted=1)
    assert _repo().lookup_scope('mappings', 88) is None


def test_soft_deleted_api_mapping_returns_none(db):
    db.insert('param_mappings', id=88, algorithm_type=_ALGO,
              api_id=_API_ID, device_id=None, deleted=1)
    assert _repo().lookup_scope('mappings', 88) is None


def test_live_api_mapping_returns_api_scope(db):
    db.insert('param_mappings', id=88, algorithm_type=_ALGO,
              api_id=_API_ID, device_id=None, deleted=0)
    assert _repo().lookup_scope('mappings', 88) == (
        SCOPE_API, _API_ID, _ALGO)


# ---------- 路由端到端：UI 形态的 DELETE（无 body） ----------

def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _fake_auth(request, call_next):
        request.state.permissions = ['*']
        return await call_next(request)

    app.include_router(
        algorithm_router, prefix='/api/v1/algorithm', tags=['algorithm'])
    return app


def test_ui_delete_without_body_records_device_history(db, monkeypatch):
    """复现 INT-2332 #8 删除路径：无 body 的 DELETE 也要记一版。"""
    recorded = []

    def _record(scope, scope_id, algorithm_type, action='save'):
        recorded.append((scope, scope_id, algorithm_type, action))
        return {'id': 1, 'version': 1, 'action': action}

    class _FakeCommand:
        @staticmethod
        def delete_param(param_id):
            return {'success': True, 'data': {'id': param_id}}, 200

    monkeypatch.setattr(ParamHistoryService, 'record', staticmethod(_record))
    monkeypatch.setattr(algorithm_bp, 'AlgorithmCommandService', _FakeCommand)
    # 同号 API 行存在且活跃：修复前会命中它 → 不记设备版本
    db.insert('algorithm_device_params', id=_SAME_ID,
              algorithm_type=_ALGO, device_id=_DEVICE_ID, deleted=0)
    db.insert('algorithm_api_params', id=_SAME_ID,
              algorithm_type='api_algo', api_id=_API_ID, deleted=0)

    resp = TestClient(_app()).delete(f'/api/v1/algorithm/params/{_SAME_ID}')
    assert resp.status_code == 200
    assert recorded == [(SCOPE_DEVICE, _DEVICE_ID, _ALGO, 'save')]
