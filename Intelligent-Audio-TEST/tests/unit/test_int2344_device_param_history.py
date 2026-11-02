# -*- coding: utf-8 -*-
"""INT-2344 回归：设备参数 / 映射写操作必须记录 param_change_history。

缺陷（INT-2332 矩阵测试 #8）：``api_gateway/routes/algorithm_bp.py`` 的
``_record_device_history`` 以 ``isinstance(response, tuple)`` 判定写成功，
但 6 个调用点传入的都是 ``to_response(...)`` 的返回值 ——
``(dict, status)`` 已被转成 ``CustomJSONResponse``，条件恒 False，
``ParamHistoryService.record('device', ...)`` 永不执行：接口恒返回空历史、
``param_change_history`` 表 0 行。

契约（本文件逐条守住）：
1. 原始 ``(dict, status)`` tuple 且 status < 400 → 记录；
2. ``Response`` 形态（带 ``status_code``）且 < 400 → 记录（本次修复的关键路径）；
3. 失败状态码（tuple / Response 两种形态）→ 不记录；
4. 缺 ``device_id`` 或 ``algorithm_type`` → 不记录；
5. ``lookup_scope('params', id)`` 与删除口径一致：设备表优先、只认未删除行
   （两张参数表 id 独立自增，同号/软删占号会把历史写到别的作用域）。

用轻量假对象 + monkeypatch 替换记录入口；lookup_scope 用假 session，
不连库、不触达 gRPC。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from api_gateway.infrastructure.repositories import param_history_repository as repo_mod  # noqa: E402
from api_gateway.infrastructure.repositories.param_history_repository import (  # noqa: E402
    SCOPE_API,
    SCOPE_DEVICE,
    ParamHistoryRepository,
)
from api_gateway.routes import algorithm_bp  # noqa: E402


class _FakeHistoryService:
    """记录调用参数，替代真实 ParamHistoryService。"""

    def __init__(self):
        self.calls = []

    def record(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {'id': len(self.calls)}


@pytest.fixture()
def history(monkeypatch):
    fake = _FakeHistoryService()
    monkeypatch.setattr(algorithm_bp.ParamHistoryService, 'record', fake.record)
    return fake


def test_tuple_success_records(history):
    algorithm_bp._record_device_history(({'id': 1}, 200), 12, 'voice_llm')
    assert history.calls == [(('device', 12, 'voice_llm'), {})]


def test_response_success_records(history):
    """修复前该用例失败：to_response 已把 tuple 转成 Response。"""
    response = JSONResponse(content={'id': 1}, status_code=201)
    algorithm_bp._record_device_history(response, '7', 'voice_llm')
    assert history.calls == [(('device', 7, 'voice_llm'), {})]


def test_tuple_failure_not_recorded(history):
    algorithm_bp._record_device_history(({'message': 'bad'}, 400), 12, 'voice_llm')
    assert history.calls == []


def test_response_failure_not_recorded(history):
    response = JSONResponse(content={'message': 'forbidden'}, status_code=403)
    algorithm_bp._record_device_history(response, 12, 'voice_llm')
    assert history.calls == []


def test_missing_scope_not_recorded(history):
    ok = JSONResponse(content={'id': 1}, status_code=200)
    algorithm_bp._record_device_history(ok, None, 'voice_llm')
    algorithm_bp._record_device_history(ok, 12, '')
    algorithm_bp._record_device_history(ok, 12, None)
    assert history.calls == []


def test_algorithm_level_write_not_recorded(history):
    """device_id=null（算法级默认行）不是设备覆盖，不应记设备版本。"""
    ok = JSONResponse(content={'id': 1}, status_code=200)
    algorithm_bp._record_device_history(ok, None, 'voice_llm')
    assert history.calls == []


def test_unknown_response_shape_not_recorded(history):
    """非 tuple 且无 status_code 的对象按 500 处理，宁可不记也不误记。"""
    algorithm_bp._record_device_history(object(), 12, 'voice_llm')
    assert history.calls == []


# ---------- lookup_scope：删除前定位作用域（与 soft_delete 同口径） ----------

class _Result:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _FakeSession:
    """按 SQL 是否带 ``deleted = false`` 区分活跃/软删行。

    故意在无过滤时回落到软删行：一旦有人删掉过滤条件，用例 2/4 就会
    把作用域判到已被软删的同号行上，直接红。
    """

    def __init__(self, live, deleted=None):
        self.live = live
        self.deleted = deleted or {}

    @staticmethod
    def _table(sql):
        for name in ('algorithm_device_params', 'algorithm_api_params',
                     'param_mappings'):
            if name in sql:
                return name
        return ''

    def execute(self, stmt, params):
        sql = str(stmt).lower()
        table = self._table(sql)
        if 'deleted = false' in sql:
            return _Result(self.live.get(table))
        return _Result(self.deleted.get(table) or self.live.get(table))


def _repo(monkeypatch, live, deleted=None):
    monkeypatch.setattr(repo_mod, 'get_db_session',
                        lambda: _FakeSession(live, deleted))
    return ParamHistoryRepository()


_DEV = {'algorithm_type': 'int2344_matrix', 'scope_id': 24}
_API = {'algorithm_type': 'voice_llm', 'scope_id': 17}


def test_lookup_params_prefers_live_device_row(monkeypatch):
    """两表同号且都活跃：与 soft_delete 一致取设备行，不取 API 同号行。"""
    repo = _repo(monkeypatch, {
        'algorithm_device_params': _DEV,
        'algorithm_api_params': _API,
    })
    assert repo.lookup_scope('params', 238) == ('device', 24, 'int2344_matrix')


def test_lookup_params_skips_soft_deleted_row(monkeypatch):
    """设备行已软删、API 同号行活跃 → 取 API 作用域，不能把 API id 当设备 id。"""
    repo = _repo(
        monkeypatch,
        live={'algorithm_api_params': _API},
        deleted={'algorithm_device_params': _DEV},
    )
    assert repo.lookup_scope('params', 238) == (SCOPE_API, 17, 'voice_llm')


def test_lookup_params_all_deleted_returns_none(monkeypatch):
    repo = _repo(monkeypatch, live={}, deleted={
        'algorithm_device_params': _DEV,
        'algorithm_api_params': _API,
    })
    assert repo.lookup_scope('params', 238) is None


def test_lookup_mappings_respects_live_scope(monkeypatch):
    repo = _repo(monkeypatch, live={'param_mappings': {
        'algorithm_type': 'int2344_matrix', 'api_id': None, 'device_id': 24}})
    assert repo.lookup_scope('mappings', 10999) == (
        SCOPE_DEVICE, 24, 'int2344_matrix')

    repo = _repo(monkeypatch, live={}, deleted={'param_mappings': {
        'algorithm_type': 'int2344_matrix', 'api_id': 5, 'device_id': None}})
    assert repo.lookup_scope('mappings', 10999) is None
