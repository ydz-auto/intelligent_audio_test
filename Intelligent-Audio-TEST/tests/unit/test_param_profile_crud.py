# -*- coding: utf-8 -*-
"""参数策略写仓储（ParamProfileCommandRepository）原子性与唯一键单测。

走文件型 SQLite 隔离库（conftest 已提供进程级临时 DATABASE_URL），
create_all 只建本组用例涉及的表，每用例前后清空，保证可重复运行。
"""
import os

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

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

ALGO = 'ut_param_profile'
ALGO_OTHER = 'ut_param_profile_other'

_TABLES = (
    ParamProfile, ParamProfileParam, ParamProfileMapping,
    ApiParamBinding, AlgorithmApiParam, ParamMapping,
)


@pytest.fixture(scope='module')
def db():
    """初始化文件型 SQLite 并建表（与 conftest 的进程级临时库同一个文件）。"""
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), (
        f'参数策略仓储测试需要文件型 sqlite，实际绑定 {engine.url}'
    )
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


def _profile(name, params=None, mappings=None, **kwargs):
    payload = {
        'scope': kwargs.pop('scope', 'api'),
        'algorithm_type': kwargs.pop('algorithm_type', ALGO),
        'name': name,
        'status': 'online',
        'params': params or [],
        'mappings': mappings or [],
    }
    payload.update(kwargs)
    return payload


def _param(code, **kwargs):
    item = {'param_code': code, 'param_type': 'text', 'direction': 'input'}
    item.update(kwargs)
    return item


def _mapping(source_param, target_param='t1', dimension_id=1, **kwargs):
    item = {
        'source': 'api',
        'source_param': source_param,
        'target_param': target_param,
        'dimension_id': dimension_id,
    }
    item.update(kwargs)
    return item


def _all(po, **filters):
    session = get_db_session()
    return session.query(po).filter_by(**filters).all()


class TestParamProfileSave:

    def test_save_create_roundtrip(self, clean_db, repo):
        detail = repo.save(_profile(
            'p1', description='d',
            params=[_param('a', ui_order=2, label='A'),
                    _param('b', direction='output', ui_order=1,
                           default_value='medium',
                           validation_rules={'min': 1})],
            mappings=[_mapping('s1', 't1', 7),
                      _mapping('s2', 't2', 8)],
        ))

        assert detail['id'] > 0
        assert detail['scope'] == 'api'
        assert detail['algorithm_type'] == ALGO
        assert detail['name'] == 'p1'
        assert detail['description'] == 'd'
        assert detail['status'] == 'online'

        # params 按 ui_order 升序
        assert [p['param_code'] for p in detail['params']] == ['b', 'a']
        b_out = detail['params'][0]
        assert b_out['direction'] == 'output'
        assert b_out['default_value'] == 'medium'
        assert b_out['validation'] == {'min': 1}
        assert b_out['profile_id'] == detail['id']

        # mappings 全量
        got = sorted(
            (m['source'], m['source_param'], m['dimension_id'],
             m['target_param']) for m in detail['mappings'])
        assert got == [('api', 's1', 7, 't1'), ('api', 's2', 8, 't2')]

        # 直查库确认行数与详情一致
        assert len(_all(ParamProfileParam, profile_id=detail['id'])) == 2
        assert len(_all(ParamProfileMapping, profile_id=detail['id'])) == 2

    def test_save_uses_natural_keys_and_soft_deletes_removed_rows(
            self, clean_db, repo):
        profile_id = repo.save(_profile(
            'p1',
            params=[_param('a', label='A'), _param('b', label='B')],
            mappings=[_mapping('s1', 't1', 1), _mapping('s2', 't2', 2)],
        ))['id']

        # 同自然键重复提交 → 更新而非新增
        repo.save({
            'id': profile_id,
            'params': [_param('a', label='A2'), _param('b', label='B2')],
            'mappings': [_mapping('s1', 't1b', 1), _mapping('s2', 't2b', 2)],
        })
        assert len(_all(ParamProfileParam, profile_id=profile_id)) == 2
        assert len(_all(ParamProfileMapping, profile_id=profile_id)) == 2

        detail = repo.get(profile_id)
        assert {p['param_code']: p['label'] for p in detail['params']} == \
            {'a': 'A2', 'b': 'B2'}
        assert {m['source_param']: m['target_param']
                for m in detail['mappings']} == {'s1': 't1b', 's2': 't2b'}

        # 未提交的行变软删：行数不变，活跃视图不再包含
        repo.save({
            'id': profile_id,
            'params': [_param('a', label='A2')],
            'mappings': [_mapping('s1', 't1b', 1)],
        })
        detail = repo.get(profile_id)
        assert [p['param_code'] for p in detail['params']] == ['a']
        assert [m['source_param'] for m in detail['mappings']] == ['s1']

        assert len(_all(ParamProfileParam, profile_id=profile_id)) == 2
        assert len(_all(ParamProfileMapping, profile_id=profile_id)) == 2
        assert [r.param_code for r in _all(
            ParamProfileParam, profile_id=profile_id, deleted=True)] == ['b']
        assert [r.source_param for r in _all(
            ParamProfileMapping, profile_id=profile_id, deleted=True)] == ['s2']

    def test_clone_copies_full_payload_without_touching_source(
            self, clean_db, repo):
        source = repo.save(_profile(
            'src', description='src-desc',
            params=[_param('a', ui_order=1), _param('b', direction='output')],
            mappings=[_mapping('s1', 't1', 1), _mapping('s2', 't2', 2)],
        ))

        copied = repo.clone(source['id'], 'copy', 'copy-desc')

        assert copied['id'] != source['id']
        assert copied['name'] == 'copy'
        assert copied['description'] == 'copy-desc'
        assert copied['cloned_from'] == source['id']
        assert copied['algorithm_type'] == source['algorithm_type']
        assert copied['scope'] == source['scope']
        assert {p['param_code'] for p in copied['params']} == {'a', 'b'}
        assert {p['profile_id'] for p in copied['params']} == {copied['id']}
        assert {m['source_param'] for m in copied['mappings']} == {'s1', 's2'}

        # 源策略不受影响
        latest = repo.get(source['id'])
        assert latest['name'] == 'src'
        assert latest['cloned_from'] is None
        assert {p['param_code'] for p in latest['params']} == {'a', 'b'}
        assert len(_all(ParamProfileParam, profile_id=source['id'])) == 2

    def test_delete_soft_deletes_profile_and_children(self, clean_db, repo):
        profile_id = repo.save(_profile(
            'p1', params=[_param('a')], mappings=[_mapping('s1')]))['id']

        assert repo.delete(profile_id) is True
        assert repo.get(profile_id) is None
        assert profile_id not in [p['id'] for p in repo.list(algorithm_type=ALGO)]

        assert _all(ParamProfileParam, profile_id=profile_id)[0].deleted is True
        assert _all(ParamProfileMapping, profile_id=profile_id)[0].deleted is True
        assert repo.delete(profile_id) is False


class TestApiBinding:

    def test_bind_update_unbind(self, clean_db, repo):
        p1 = repo.save(_profile('p1'))['id']
        p2 = repo.save(_profile('p2'))['id']

        assert repo.bind_api(501, p1) == {'api_id': 501, 'profile_id': p1}
        assert repo.get_binding(501) == p1

        # 重复绑定同一 api → 更新 profile_id，不新增行
        assert repo.bind_api(501, p2) == {'api_id': 501, 'profile_id': p2}
        assert repo.get_binding(501) == p2
        assert len(_all(ApiParamBinding, api_id=501)) == 1

        # profile_id=None → 解绑
        assert repo.bind_api(501, None) == {'api_id': 501, 'profile_id': None}
        assert repo.get_binding(501) is None
        assert [r for r in _all(ApiParamBinding, api_id=501)
                if not r.deleted] == []

    def test_bind_device_scope_rejected_and_rolled_back(self, clean_db, repo):
        p_api = repo.save(_profile('p-api'))['id']
        p_device = repo.save(_profile('p-device', scope='device'))['id']

        repo.bind_api(502, p_api)
        with pytest.raises(ValueError):
            repo.bind_api(502, p_device)

        # 事务回滚后绑定保持原值，且没有多出绑定行
        assert repo.get_binding(502) == p_api
        assert [r.profile_id for r in _all(ApiParamBinding, api_id=502)
                if not r.deleted] == [p_api]


class TestSaveApiOverrides:

    def test_overrides_only_touch_target_api_scope(self, clean_db, repo):
        # 目标 api 601；同算法类型另 api 602；另一算法类型同 api 601
        first = repo.save_api_overrides(
            601, ALGO,
            [_param('a', label='A'), _param('b', label='B')],
            [_mapping('m1', 't1', 1), _mapping('m2', 't2', 2)],
        )
        assert first == {
            'params_created': 2, 'params_updated': 0, 'params_deleted': 0,
            'mappings_created': 2, 'mappings_updated': 0, 'mappings_deleted': 0,
        }
        repo.save_api_overrides(
            602, ALGO,
            [_param('x', label='X'), _param('y', label='Y')],
            [_mapping('m3', 't3', 3)],
        )
        repo.save_api_overrides(
            601, ALGO_OTHER,
            [_param('a', label='OTH')],
            [_mapping('m1', 'ot', 1)],
        )

        counts = repo.save_api_overrides(
            601, ALGO,
            [_param('a', label='A2'), _param('c', label='C')],
            [_mapping('m1', 't1b', 1), _mapping('m4', 't4', 4)],
        )
        assert counts == {
            'params_created': 1, 'params_updated': 1, 'params_deleted': 1,
            'mappings_created': 1, 'mappings_updated': 1, 'mappings_deleted': 1,
        }

        active_params = {
            (r.api_id, r.param_code): r.label
            for r in _all(AlgorithmApiParam, algorithm_type=ALGO) if not r.deleted
        }
        assert active_params == {
            (601, 'a'): 'A2', (601, 'c'): 'C',
            (602, 'x'): 'X', (602, 'y'): 'Y',
        }

        active_mappings = {
            (r.api_id, r.source_param): r.target_param
            for r in _all(ParamMapping, algorithm_type=ALGO) if not r.deleted
        }
        assert active_mappings == {
            (601, 'm1'): 't1b', (601, 'm4'): 't4', (602, 'm3'): 't3',
        }

        # 另一 algorithm_type 的行完全不变
        other = _all(AlgorithmApiParam, algorithm_type=ALGO_OTHER)
        assert [(r.api_id, r.param_code, r.label) for r in other] == \
            [(601, 'a', 'OTH')]
        assert all(not r.deleted for r in other)
