# -*- coding: utf-8 -*-
"""INT-1565：test_cases.derived_test_type 迁移（㊳）真实 Postgres 验收。

背景：INT-1469 给 test_cases 加了写时物化的派生列 derived_test_type 并随之
落盘迁移脚本 add_derived_test_type_int1469.py，但存量库（真实库 / 隔离库）
一直没有该列 —— create_all 只建缺失的表、不给已存在的表补列。task_service
新镜像一旦重建，建用例 / 用例列表即 UndefinedColumn 400（冒烟门禁 S2 原文）。

本文件按 INT-423 同款方式（真实 Postgres 临时库，用后即删）做红-绿验收：
- 红：临时库整库 create_all 后 DROP COLUMN derived_test_type，还原「存量库」
  形态；此时按新代码口径插入带派生列的用例必报 UndefinedColumn（复现缺陷）；
- 绿：执行迁移脚本 --apply → 补列 NOT NULL DEFAULT 'api'、建索引
  ix_test_cases_derived_test_type、存量行按 derive_case_test_type 回填
  （默认值只作过渡，e2e 形态不能再被粗放标成 api）；
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
    'add_derived_test_type_int1469.py')
_COLUMN = 'derived_test_type'
_INDEX = 'ix_test_cases_derived_test_type'

# 存量行（迁移前形态，无 derived_test_type 列）：
#   _API   配置无 playback_device_id → api
#   _E2E   任一音频带 playback_device_id → e2e（回填必须改正，默认 'api' 不对）
#   _DIRTY config 是 JSON 字符串而非对象 → 兜底按 api，不能让引导链单行失败
_API_CONFIG = {'rounds': [{'roundNumber': 1, 'audios': [{'audio_id': 1}]}]}
_E2E_CONFIG = {'rounds': [{'roundNumber': 1,
                           'audios': [{'audio_id': 1, 'playback_device_id': 3}]}]}
_LEGACY_ROWS = (
    ('I1565_API', '存量api用例', _API_CONFIG),
    ('I1565_E2E', '存量e2e用例', _E2E_CONFIG),
    ('I1565_DIRTY', '存量脏配置用例', 'not-an-object'),
)


def _pg_params():
    return dict(host=PG_HOST, port=PG_PORT, user=PG_USER,
                password=PG_PASSWORD, connect_timeout=5)


@pytest.fixture(scope='module')
def int1565_pg_db(storage_env):  # noqa: F811
    """真实 Postgres 临时库：整库创建 → 全模型建表 → 削列还原存量形态 → 用后即删。"""
    if not _pg_reachable():
        pytest.skip(f'本机 Postgres {PG_HOST}:{PG_PORT} 不可用，INT-1565 实方言验收跳过')

    dbname = f'int1565_{uuid.uuid4().hex[:10]}'
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
        cur.execute(f'ALTER TABLE test_cases DROP COLUMN {_COLUMN}')
        cur.execute(f'DROP INDEX IF EXISTS {_INDEX}')
        for tc_id, name, config in _LEGACY_ROWS:
            cur.execute(
                'INSERT INTO test_cases (id, name, config, deleted) '
                'VALUES (%s, %s, %s, FALSE)',
                (tc_id, name, json.dumps(config)))
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
    return subprocess.run(
        [sys.executable, _MIGRATION, *args], env=env, cwd=PROJECT_ROOT,
        capture_output=True, text=True)


def _derived_values(uri):
    conn = psycopg2.connect(uri)
    cur = conn.cursor()
    try:
        cur.execute(f'SELECT id, {_COLUMN} FROM test_cases ORDER BY id')
        return dict(cur.fetchall())
    finally:
        cur.close()
        conn.close()


class TestDerivedTestTypeMigrationRealPG:
    """红-绿 + 幂等（方法定义顺序即执行顺序，首次迁移在第二个用例内完成）。"""

    def test_red_legacy_db_rejects_new_code_insert(self, int1565_pg_db):
        """红：存量库无该列时，新代码口径的插入必 UndefinedColumn（冒烟 S2 根因）。"""
        conn = psycopg2.connect(int1565_pg_db)
        conn.autocommit = False
        cur = conn.cursor()
        try:
            with pytest.raises(psycopg2.errors.UndefinedColumn):
                cur.execute(
                    'INSERT INTO test_cases (id, name, config, deleted, '
                    f'{_COLUMN}) VALUES (%s, %s, %s, FALSE, %s)',
                    ('I1565_RED', '存量库插入', json.dumps(_API_CONFIG), 'api'))
        finally:
            conn.rollback()
            cur.close()
            conn.close()

    def test_migration_adds_column_backfills_and_index(self, int1565_pg_db):
        """绿：--apply 补列 + 回填 + 建索引，存量行口径与派生函数一致。"""
        proc = _run_migration(int1565_pg_db, '--apply')
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert '[APPLY]' in proc.stdout

        conn = psycopg2.connect(int1565_pg_db)
        cur = conn.cursor()
        try:
            cur.execute(
                'SELECT data_type, is_nullable, column_default '
                'FROM information_schema.columns '
                'WHERE table_name = %s AND column_name = %s',
                ('test_cases', _COLUMN))
            row = cur.fetchone()
            assert row is not None, f'test_cases.{_COLUMN} 列缺失'
            data_type, is_nullable, col_default = row
            assert data_type == 'character varying'
            assert is_nullable == 'NO'
            assert col_default is not None and 'api' in col_default

            cur.execute(
                'SELECT 1 FROM pg_indexes WHERE tablename = %s AND indexname = %s',
                ('test_cases', _INDEX))
            assert cur.fetchone() is not None, f'索引 {_INDEX} 缺失'
        finally:
            cur.close()
            conn.close()

        from shared.utils.testcase_helpers import derive_case_test_type
        got = _derived_values(int1565_pg_db)
        assert set(got) == {tc_id for tc_id, _n, _c in _LEGACY_ROWS}
        for tc_id, name, config in _LEGACY_ROWS:
            want = (derive_case_test_type(config, name)
                    if isinstance(config, dict) else 'api')
            assert got[tc_id] == want, tc_id
        # 默认值只作过渡：e2e 形态存量行必须被回填改正
        assert got['I1565_E2E'] == 'e2e'
        assert got['I1565_API'] == 'api'
        # 脏配置兜底：不能因单行非对象 config 让整个引导链失败
        assert got['I1565_DIRTY'] == 'api'

    def test_insert_after_migration_succeeds(self, int1565_pg_db):
        """迁移后新代码口径的写入恢复（含默认值走 server_default 的兜底路径）。"""
        conn = psycopg2.connect(int1565_pg_db)
        cur = conn.cursor()
        try:
            cur.execute(
                'INSERT INTO test_cases (id, name, config, deleted, '
                f'{_COLUMN}) VALUES (%s, %s, %s, FALSE, %s)',
                ('I1565_GREEN', '迁移后插入', json.dumps(_E2E_CONFIG), 'e2e'))
            cur.execute(
                f'SELECT {_COLUMN} FROM test_cases WHERE id = %s', ('I1565_GREEN',))
            assert cur.fetchone()[0] == 'e2e'
            conn.commit()
        finally:
            cur.close()
            conn.close()

    def test_second_run_is_idempotent(self, int1565_pg_db):
        """幂等：二次执行全 [SKIP]、回填待改 0 行（db_bootstrap 每次部署都会跑）。"""
        proc = _run_migration(int1565_pg_db, '--apply')
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert f'[SKIP] 列 test_cases.{_COLUMN} 已存在' in proc.stdout
        assert f'[SKIP] 索引 {_INDEX} 已存在' in proc.stdout
        assert '待改 0 行，已改 0 行' in proc.stdout
