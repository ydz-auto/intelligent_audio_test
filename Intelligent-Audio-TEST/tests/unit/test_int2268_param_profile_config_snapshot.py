# -*- coding: utf-8 -*-
"""INT-2268 参数策略 PUT 不带 config 清空 config_snapshot 的回归单测。

缺陷（INT-2224 走查 P1-2）：``PUT /algorithm/param-profiles/{id}`` 的网关
``req.model_dump()`` 把未传的 ``config`` 序列化成 ``None`` 一并下发，仓储看到
``'config' in data`` 就写 ``NULL`` —— 编辑名称/描述/状态即静默清空快照。

修复口径：
- 网关 ``model_dump(exclude_none=True)``：显式 null 与「未提供」同义，键不下发；
- 仓储 ``save()``：``config`` 为 None 一律保持原快照（防绕过网关直连 gRPC）；
- 整份保存语义写死：``params``/``mappings`` 缺失等同 ``[]``（全量软删）。
"""
import os

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from api_gateway.application.services.algorithm import (  # noqa: E402
    algorithm_profile_service as profile_service,
)
from shared.models.database import (  # noqa: E402
    Base, get_db_session, get_engine, init_db, remove_db_session,
)
from algorithm_service.infrastructure.persistence.models import (  # noqa: E402
    AlgorithmApiParam,
    ApiParamBinding,
    ParamMapping,
    ParamProfile,
    ParamProfileMapping,
    ParamProfileParam,
)
from algorithm_service.infrastructure.persistence._param_profile_repositories \
    import ParamProfileCommandRepository  # noqa: E402

ALGO = 'ut_int2268_profile'

_TABLES = (
    ParamProfile, ParamProfileParam, ParamProfileMapping,
    ApiParamBinding, AlgorithmApiParam, ParamMapping,
)


# ========== 网关层：null / 缺失不进入下发载荷 ==========

class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    def get_json(self):
        return self._payload


class _FakeProxy:
    def __init__(self):
        self.calls = []

    def save_param_profile(self, data):
        self.calls.append(data)
        return {'success': True, 'data': {'id': 7}, 'message': 'ok'}


@pytest.fixture()
def proxy(monkeypatch):
    fake = _FakeProxy()
    monkeypatch.setattr(profile_service, '_algo_proxy', fake)
    return fake


def _patch_body(monkeypatch, payload):
    monkeypatch.setattr(profile_service, 'request', _FakeRequest(payload))


_BASE = {'algorithm_type': ALGO, 'name': 'p1'}

_CONFIG = {'protocol': 'http', 'streaming': False,
           'audio_config': {'sample_rate': 16000}}


def test_update_without_config_does_not_send_config_key(monkeypatch, proxy):
    _patch_body(monkeypatch, {**_BASE, 'status': 'offline'})
    _, http_code = profile_service.AlgorithmProfileService.update_profile(7)
    assert http_code == 200
    assert 'config' not in proxy.calls[0]
    assert proxy.calls[0]['id'] == 7
    assert proxy.calls[0]['status'] == 'offline'


def test_update_with_explicit_null_config_does_not_send_config_key(
        monkeypatch, proxy):
    """React ``toParamProfileDto`` 在无快照时显式提交 config:null，同样不得下发。"""
    _patch_body(monkeypatch, {**_BASE, 'config': None})
    profile_service.AlgorithmProfileService.update_profile(7)
    assert 'config' not in proxy.calls[0]


def test_update_with_config_passes_snapshot_through(monkeypatch, proxy):
    _patch_body(monkeypatch, {**_BASE, 'config': _CONFIG})
    profile_service.AlgorithmProfileService.update_profile(7)
    assert proxy.calls[0]['config'] == _CONFIG


def test_update_keeps_full_replace_lists_explicit(monkeypatch, proxy):
    """params/mappings 仍以 [] 下发（整份替换语义不变）。"""
    _patch_body(monkeypatch, _BASE)
    profile_service.AlgorithmProfileService.update_profile(7)
    assert proxy.calls[0]['params'] == []
    assert proxy.calls[0]['mappings'] == []


def test_create_without_config_does_not_send_config_key(monkeypatch, proxy):
    _patch_body(monkeypatch, _BASE)
    profile_service.AlgorithmProfileService.create_profile()
    assert 'config' not in proxy.calls[0]


# ========== 仓储层：直接落库口径 ==========

@pytest.fixture(scope='module')
def db():
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), (
        f'策略仓储测试需要文件型 sqlite，实际绑定 {engine.url}')
    remove_db_session()
    Base.metadata.create_all(
        bind=engine, tables=[po.__table__ for po in _TABLES])
    yield engine
    remove_db_session()


def _purge():
    session = get_db_session()
    for po in _TABLES:
        session.query(po).delete()
    session.commit()
    session.expunge_all()
    remove_db_session()


@pytest.fixture()
def clean_db(db):
    _purge()
    yield
    _purge()


@pytest.fixture()
def repo():
    return ParamProfileCommandRepository()


def _profile(name, **kwargs):
    payload = {
        'scope': 'api',
        'algorithm_type': ALGO,
        'name': name,
        'status': 'online',
        'params': [],
        'mappings': [],
    }
    payload.update(kwargs)
    return payload


def _snapshot(profile_id):
    session = get_db_session()
    po = session.query(ParamProfile).filter_by(id=profile_id).first()
    return None if po is None else po.config_snapshot


def test_save_create_persists_config_snapshot(clean_db, repo):
    detail = repo.save(_profile('p1', config=_CONFIG))
    assert detail['config'] == _CONFIG
    assert _snapshot(detail['id']) is not None


def test_update_without_config_key_keeps_snapshot(clean_db, repo):
    profile_id = repo.save(_profile('p1', config=_CONFIG))['id']

    repo.save({'id': profile_id, 'name': 'p1-renamed',
               'status': 'offline', 'params': [], 'mappings': []})

    detail = repo.get(profile_id)
    assert detail['name'] == 'p1-renamed'
    assert detail['status'] == 'offline'
    assert detail['config'] == _CONFIG


def test_update_with_explicit_none_config_keeps_snapshot(clean_db, repo):
    """绕过网关直连 gRPC 塞 config=None 也不得清快照。"""
    profile_id = repo.save(_profile('p1', config=_CONFIG))['id']

    repo.save({'id': profile_id, 'name': 'p1', 'config': None})

    assert repo.get(profile_id)['config'] == _CONFIG


def test_update_with_config_overwrites_snapshot(clean_db, repo):
    profile_id = repo.save(_profile('p1', config=_CONFIG))['id']
    new_config = {'protocol': 'ws', 'streaming': True}

    repo.save({'id': profile_id, 'name': 'p1', 'config': new_config})

    assert repo.get(profile_id)['config'] == new_config


def test_update_with_empty_config_clears_to_empty_object(clean_db, repo):
    """清快照的唯一口径是显式 ``{}``（存 '{}'），不是 null。"""
    profile_id = repo.save(_profile('p1', config=_CONFIG))['id']

    repo.save({'id': profile_id, 'name': 'p1', 'config': {}})

    assert repo.get(profile_id)['config'] == {}
    assert _snapshot(profile_id) == '{}'


def test_omitted_params_and_mappings_still_full_replace(clean_db, repo):
    """整份替换语义写死：params/mappings 缺失等同 []，既有行被软删。"""
    profile_id = repo.save(_profile(
        'p1',
        params=[{'param_code': 'a', 'param_type': 'text', 'direction': 'input'}],
        mappings=[{'source': 'api', 'source_param': 'a',
                   'target_param': 't1', 'dimension_id': 1}],
    ))['id']

    repo.save({'id': profile_id, 'name': 'p1'})

    detail = repo.get(profile_id)
    assert detail['params'] == []
    assert detail['mappings'] == []
    session = get_db_session()
    assert session.query(ParamProfileParam).filter_by(
        profile_id=profile_id, deleted=True).count() == 1
    assert session.query(ParamProfileMapping).filter_by(
        profile_id=profile_id, deleted=True).count() == 1


def test_clone_keeps_source_snapshot(clean_db, repo):
    source = repo.save(_profile('src', config=_CONFIG))

    copied = repo.clone(source['id'], 'copy')

    assert copied['config'] == _CONFIG
    assert repo.get(source['id'])['config'] == _CONFIG
