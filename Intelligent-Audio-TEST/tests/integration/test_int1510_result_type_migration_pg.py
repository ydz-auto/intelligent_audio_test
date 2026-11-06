# -*- coding: utf-8 -*-
"""INT-1510：test_results.result_type 迁移（㊶）真实 Postgres 验收。

背景：INT-1510 给 test_results 加了 result_type 落库列（候选/树接口 DB-first，
请求路径零 OSS 往返），create_all 只建缺失的表、不给已存在的表补列，存量库
（真实库 / 隔离库）需要迁移补列 + 回填，否则读侧 UndefinedColumn 400。

本文件按 INT-1565 同款方式（真实 Postgres 临时库，用后即删）做红-绿验收：
- 红：临时库整库 create_all 后 DROP COLUMN result_type，还原「存量库」形态，
  此时按新口径查该列必报 UndefinedColumn（复现缺陷）；
- 绿：执行迁移脚本 --apply → 补列、存量行按 `materialize_result_type(None, ...)`
  回填（只读 DB 轻量 JSON，**不回源对象存储**；缺键行保持 NULL = 待补充桶）；
- 幂等：二次执行全 [SKIP]、待改 0 行（db_bootstrap 每次部署都会跑该步）。

DB：本文件模块级夹具整库创建 → 真实 PO 建表 → 用后即删（测试数据不落库外）。
"""
import json
import os
import subprocess
import sys
import uuid

import psycopg2
import pytest
from sqlalchemy import create_engine

from tests.integration.test_task_execute_real_chain import (
    _pg_reachable,  # noqa: F401  复用可达性探针口径
)
from tests.integration.test_data_transfer_roundtrip import (
    storage_env,  # noqa: F401  OSS 本地降级（建表/迁移不触网）
)

PG_HOST = os.environ.get('INT35_PG_HOST', '127.0.0.1')
PG_PORT = int(os.environ.get('INT35_PG_PORT', '5432'))
PG_USER = os.environ.get('INT35_PG_USER', 'intelligent_audio_test')
PG_PASSWORD = os.environ.get('INT35_PG_PASSWORD', 'intelligent_audio_test666')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_MIGRATION = os.path.join(
    PROJECT_ROOT, 'scripts', 'migrations', '202610',
    'add_test_result_result_type_int1510.py')
_COLUMN = 'result_type'

# 存量行（迁移前形态，无 result_type 列）：
#   _ASR     轻量 JSON 已含 result_type → 回填 asr
#   _VOICE   轻量 JSON 是被 JSON 编码过的字符串（双重编码）→ 回填 voice
#   _NO_KEY  轻量 JSON 缺键 → 保持 NULL（待补充桶）
#   _NULL    result_data 为空 → 保持 NULL
_LEGACY_ROWS = (
    (9101, {'result_type': 'asr', 'extra': 1}),
    (9102, json.dumps({'result_type': 'voice'})),
    (9103, {'foo': 1}),
    (9104, None),
)


def _pg_params():
    return dict(host=PG_HOST, port=PG_PORT, user=PG_USER,
                password=PG_PASSWORD, connect_timeout=5)


@pytest.fixture(scope='module')
def int1510_pg_db(storage_env):  # noqa: F811
    """真实 Postgres 临时库：整库创建 → 全模型建表 → 削列还原存量形态 → 用后即删。"""
    if not _pg_reachable():
        pytest.skip(f'本机 Postgres {PG_HOST}:{PG_PORT} 不可用，INT-1510 实方言验收跳过')

    dbname = f'int1510_{uuid.uuid4().hex[:10]}'
    admin = psycopg2.connect(dbname='postgres', **_pg_params())
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute(f'CREATE DATABASE {dbname} ENCODING utf8')
    cur.close()

    import task_service.infrastructure.persistence.models  # noqa: F401
    import evaluation_service.infrastructure.persistence.models  # noqa: F401
    import audio_service.infrastructure.persistence.models  # noqa: F401
    import report_service.infrastructure.persistence.models  # noqa: F401
    import auth_service.infrastructure.persistence.models  # noqa: F401
    import shared.models.database as database

    uri = f'postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{dbname}'
    engine = create_engine(uri, pool_pre_ping=True)
    database.Base.metadata.create_all(engine)
    engine.dispose()

    # 还原「存量库」形态：create_all 建出的表带新列，去掉它才等价于线上老库
    conn = psycopg2.connect(uri)
    cur = conn.cursor()
    try:
        cur.execute(f'ALTER TABLE test_results DROP COLUMN {_COLUMN}')
        for result_id, result_data in _LEGACY_ROWS:
            cur.execute(
                'INSERT INTO test_results '
                '(id, task_id, test_case_id, device_id, execution_status, '
                ' result_data, excluded) '
                'VALUES (%s, 1, %s, 7, %s, %s, 0)',
                (result_id, f'I1510_{result_id}',
                 'completed',
                 json.dumps(result_data) if result_data is not None else None))
        conn.commit()
    finally:
        cur.close()
        conn.close()

    yield uri

    admin = psycopg2.connect(dbname='postgres', **_pg_params())
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute(f'DROP DATABASE IF EXISTS {dbname} WITH (FORCE)')
    cur.close()
    admin.close()


def _run_migration(uri, *args):
    """以真实 CLI 方式运行迁移脚本（独立进程，DATABASE_URL 注入连接串）。"""
    env = dict(os.environ)
    env['DATABASE_URL'] = uri
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    return subprocess.run(
        [sys.executable, _MIGRATION, *args], env=env, cwd=PROJECT_ROOT,
        capture_output=True, text=True, encoding='utf-8', errors='replace')


def _values(uri):
    conn = psycopg2.connect(uri)
    cur = conn.cursor()
    try:
        cur.execute(f'SELECT id, {_COLUMN} FROM test_results ORDER BY id')
        return dict(cur.fetchall())
    finally:
        cur.close()
        conn.close()


def _column_exists(uri):
    conn = psycopg2.connect(uri)
    cur = conn.cursor()
    try:
        cur.execute(
            'SELECT 1 FROM information_schema.columns '
            'WHERE table_name = %s AND column_name = %s',
            ('test_results', _COLUMN))
        return cur.fetchone() is not None
    finally:
        cur.close()
        conn.close()


def test_int1510_red_before_migration(int1510_pg_db):
    """存量库形态（无 result_type 列）：按新口径查询即 UndefinedColumn。"""
    assert not _column_exists(int1510_pg_db), '夹具应已削列还原存量形态'
    conn = psycopg2.connect(int1510_pg_db)
    cur = conn.cursor()
    try:
        with pytest.raises(psycopg2.errors.UndefinedColumn):
            cur.execute(f'SELECT {_COLUMN} FROM test_results LIMIT 1')
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def test_int1510_migration_adds_and_backfills(int1510_pg_db):
    """--apply 补列并按 DB 轻量 JSON 回填；缺键/空值行保持 NULL。"""
    from shared.utils.result_data_store import materialize_result_type

    result = _run_migration(int1510_pg_db, '--apply')
    assert result.returncode == 0, result.stdout + result.stderr

    assert _column_exists(int1510_pg_db)
    values = _values(int1510_pg_db)
    # 口径与写路径同一函数：materialize_result_type(None, result_data)
    for result_id, result_data in _LEGACY_ROWS:
        assert values[result_id] == materialize_result_type(None, result_data), (
            f'回填口径与 materialize_result_type 不一致: {result_id}')
    assert values[9101] == 'asr'
    assert values[9102] == 'voice'
    assert values[9103] is None
    assert values[9104] is None
    # 幂等要素：默认 dry-run
    source = open(_MIGRATION, encoding='utf-8').read()
    assert "add_argument('--apply'" in source
    assert 'ADD COLUMN IF NOT EXISTS' in source


def test_int1510_migration_idempotent(int1510_pg_db):
    """重复执行：补列全 SKIP，回填待改 0 行。"""
    before = _values(int1510_pg_db)
    result = _run_migration(int1510_pg_db, '--apply')
    assert result.returncode == 0, result.stdout + result.stderr
    assert '[SKIP]' in result.stdout
    assert '待改 0 行' in result.stdout or '待改 0' in result.stdout
    assert _values(int1510_pg_db) == before
