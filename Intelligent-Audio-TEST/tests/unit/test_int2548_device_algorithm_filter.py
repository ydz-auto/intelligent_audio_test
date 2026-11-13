# -*- coding: utf-8 -*-
"""INT-2548 设备列表按 ``algorithm_type`` 过滤（SQLite 侧语义回归）。

缺陷：``Device.supported_algorithms`` 是 ``Column(JSON)``，JSON 列的
``contains`` 在 PostgreSQL 方言退化为 ``json ~~ text`` 的 LIKE 文本比较，
PG 没有该操作符 → ``GET /api/v1/test-devices?algorithm_type=asr`` 必然 400。
修复按方言分支（PG 转 JSONB 用 ``@>``，SQLite 沿用 JSON 序列化 LIKE）。

本文件在 SQLite 上锁语义（默认测试套件可跑）；PostgreSQL 实方言用例见
``tests/integration/test_int2548_device_algorithm_filter_pg.py``——
SQLite 覆盖不出 PG 的方言差异，两个方言各测一遍才闭环。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.models.database import (
    Base, get_db_session, get_engine, init_db, remove_db_session,
)


_TABLES = None


def _ensure_tables():
    init_db(pool_size=2)
    global _TABLES
    if _TABLES is None:
        from device_service.infrastructure.persistence.models import Device

        _TABLES = [Device.__table__]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLES)
    return _TABLES


def _device(name, algorithms, deleted=False):
    from device_service.infrastructure.persistence.models import Device

    return Device(
        name=name, model='M1', type='phone', system='Android',
        system_version='14', app_name='demo', app_version='1.0',
        status='online', supported_algorithms=algorithms, deleted=deleted,
    )


def _seed():
    _ensure_tables()
    session = get_db_session()
    try:
        session.query(_device_model()).delete(synchronize_session=False)
        session.add_all([
            _device('d_asr', ['asr']),
            _device('d_asr_tts', ['tts', 'asr']),
            _device('d_tts', ['tts']),
            _device('d_asr_stream', ['asr_stream']),
            _device('d_empty', []),
            _device('d_deleted', ['asr'], deleted=True),
        ])
        session.commit()
    finally:
        session.close()


def _device_model():
    from device_service.infrastructure.persistence.models import Device

    return Device


@pytest.fixture()
def repository():
    _seed()
    from device_service.infrastructure.persistence import _device_repository_impl

    yield _device_repository_impl.DeviceRepository()
    remove_db_session()


def _names(result):
    return {item['name'] for item in result['items']}


def test_algorithm_type_filter_matches_array_member(repository):
    """返回行必须都包含该算法；不相关的行与软删行不出现。"""
    result = repository.list_devices(page=1, per_page=50, algorithm_type='asr')
    assert result['total'] == 2
    assert _names(result) == {'d_asr', 'd_asr_tts'}
    for item in result['items']:
        assert 'asr' in item['supported_algorithms']


def test_algorithm_type_filter_is_exact_not_substring(repository):
    """``asr`` 不能命中 ``asr_stream``（文本子串匹配的边角由此锁住）。"""
    result = repository.list_devices(page=1, per_page=50,
                                     algorithm_type='asr')
    assert 'd_asr_stream' not in _names(result)


def test_unknown_algorithm_returns_empty_page_not_error(repository):
    """不存在的算法是合法过滤：空列表 200，而不是 400 / 异常。"""
    result = repository.list_devices(page=1, per_page=50,
                                     algorithm_type='__no_such_algorithm__')
    assert result['total'] == 0 and result['items'] == []


def test_filter_combines_with_other_filters(repository):
    result = repository.list_devices(page=1, per_page=50, algorithm_type='asr',
                                     device_type='phone')
    assert result['total'] == 2

    result = repository.list_devices(page=1, per_page=50, algorithm_type='asr',
                                     keyword='tts')
    assert _names(result) == {'d_asr_tts'}
