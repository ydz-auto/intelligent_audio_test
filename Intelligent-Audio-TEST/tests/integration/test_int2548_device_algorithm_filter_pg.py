# -*- coding: utf-8 -*-
"""INT-2548 设备列表 ``algorithm_type`` 过滤：PostgreSQL 实方言验收。

SQLite 用例（``tests/unit/test_int2548_device_algorithm_filter.py``）覆盖不出
缺陷本身：JSON 列的 ``contains`` 在 SQLite / PG 上生成的 SQL 不同——PG 退化为
``json ~~ text``（无该操作符）→ 400，SQLite 只是普通 LIKE。因此本文件在真实
PostgreSQL 临时库上复核生产行为：

- 按真实存在的算法过滤 → 只返回 ``supported_algorithms`` 含该算法的设备；
- 不存在的算法 → 空列表（不是异常 / 400）；
- 过滤条件编译为 JSONB ``@>``（不是 LIKE 文本比较）；
- 软删设备不出现，``asr`` 不命中 ``asr_stream``；
- 反向锚点：修复前的 ``json LIKE text`` 形态在 PG 上必然报错（证明 SQLite
  全绿不等于 PG 可用）。

DB：真实 Postgres 临时库（整库创建 → 全模型建表 → 用后即删）；本机 Postgres
不可用时跳过。``TEMPLATE template0`` 是必需的——本机 PG 的 template1 带
Windows 中文 collation，直接 ``CREATE DATABASE ... ENCODING utf8`` 会因
collation 不兼容失败（已实测）。
"""
import os
import uuid

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

PG_HOST = os.environ.get('INT35_PG_HOST', '127.0.0.1')
PG_PORT = int(os.environ.get('INT35_PG_PORT', '5432'))
PG_USER = os.environ.get('INT35_PG_USER', 'intelligent_audio_test')
PG_PASSWORD = os.environ.get('INT35_PG_PASSWORD', 'intelligent_audio_test666')

# 设备 PO 必须在 create_all 前注册（只导入 device_service 的模型即可）
import device_service.infrastructure.persistence.models  # noqa: E402,F401


def _pg_reachable():
    import psycopg2

    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD,
            dbname='postgres', connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope='module')
def device_pg_db():
    """真实 Postgres 临时库：整库创建 → device 模型建表 → 用后即删。"""
    if not _pg_reachable():
        pytest.skip(f'本机 Postgres {PG_HOST}:{PG_PORT} 不可用，'
                    'INT-2548 实方言用例跳过')

    import psycopg2
    from sqlalchemy import create_engine

    import shared.models.database as database

    dbname = f'int2548_{uuid.uuid4().hex[:10]}'
    admin = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD,
        dbname='postgres', connect_timeout=5)
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute(f'CREATE DATABASE {dbname} ENCODING utf8 TEMPLATE template0')
    cur.close()

    engine = create_engine(
        f'postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@'
        f'{PG_HOST}:{PG_PORT}/{dbname}', pool_pre_ping=True)
    database._engine = engine
    database._SessionFactory.configure(bind=engine)
    database.Base.metadata.create_all(engine)
    yield database

    database.remove_db_session()
    engine.dispose()
    cur = admin.cursor()
    cur.execute(f'DROP DATABASE IF EXISTS {dbname} WITH (FORCE)')
    cur.close()
    admin.close()


@pytest.fixture(autouse=True)
def _fresh_main_thread_session():
    """清主线程 session scope：先序 SQLite 用例可能缓存了旧 engine 的 session，
    临时库的 _SessionFactory rebind 只影响新建 session（同 test_int337 口径）。"""
    from shared.models.database import remove_db_session

    remove_db_session()
    yield
    remove_db_session()


@pytest.fixture()
def repository(device_pg_db):
    from shared.models.database import get_db_session

    from device_service.infrastructure.persistence.models import Device

    session = get_db_session()
    try:
        session.query(Device).delete(synchronize_session=False)
        session.add_all([
            Device(name='d_asr', model='M1', type='phone', system='Android',
                   system_version='14', app_name='demo', app_version='1.0',
                   status='online', supported_algorithms=['asr'], deleted=False),
            Device(name='d_asr_tts', model='M1', type='phone', system='Android',
                   system_version='14', app_name='demo', app_version='1.0',
                   status='online', supported_algorithms=['tts', 'asr'],
                   deleted=False),
            Device(name='d_tts', model='M1', type='phone', system='Android',
                   system_version='14', app_name='demo', app_version='1.0',
                   status='online', supported_algorithms=['tts'], deleted=False),
            Device(name='d_asr_stream', model='M1', type='phone',
                   system='Android', system_version='14', app_name='demo',
                   app_version='1.0', status='online',
                   supported_algorithms=['asr_stream'], deleted=False),
            Device(name='d_deleted', model='M1', type='phone', system='Android',
                   system_version='14', app_name='demo', app_version='1.0',
                   status='online', supported_algorithms=['asr'], deleted=True),
        ])
        session.commit()
    finally:
        session.close()

    from device_service.infrastructure.persistence import _device_repository_impl

    return _device_repository_impl.DeviceRepository()


def _names(result):
    return {item['name'] for item in result['items']}


def test_algorithm_type_filter_on_postgres(repository):
    """PG 上按数组元素精确过滤（缺陷现场就是这条查询 400）。"""
    result = repository.list_devices(page=1, per_page=50, algorithm_type='asr')
    assert result['total'] == 2
    assert _names(result) == {'d_asr', 'd_asr_tts'}
    for item in result['items']:
        assert 'asr' in item['supported_algorithms']
    assert 'd_asr_stream' not in _names(result)


def test_unknown_algorithm_is_empty_list_on_postgres(repository):
    result = repository.list_devices(page=1, per_page=50,
                                     algorithm_type='__no_such_algorithm__')
    assert result['total'] == 0 and result['items'] == []


def test_filter_sqlshape_uses_jsonb_containment(repository, device_pg_db):
    """过滤条件在 PG 上编译为 JSONB ``@>``，不再是 ``json ~~ text`` 的 LIKE。"""
    from device_service.infrastructure.persistence import _device_repository_impl
    from shared.models.database import get_db_session

    session = get_db_session()
    try:
        condition = _device_repository_impl.supported_algorithm_filter(
            session, 'asr')
        compiled = str(condition.compile(
            dialect=session.get_bind().dialect))
    finally:
        session.close()
    assert '@>' in compiled
    assert 'LIKE' not in compiled.upper()


def test_pre_fix_json_like_is_really_broken_on_postgres(repository, device_pg_db):
    """反向锚点：修复前的 JSON 列 ``contains``（``json ~~ text``）在 PG 上必报错。"""
    from sqlalchemy.exc import ProgrammingError

    from device_service.infrastructure.persistence.models import Device
    from shared.models.database import get_db_session

    session = get_db_session()
    try:
        with pytest.raises(ProgrammingError):
            session.query(Device).filter(
                Device.supported_algorithms.contains(['asr'])
            ).all()
    finally:
        session.rollback()
        session.close()
