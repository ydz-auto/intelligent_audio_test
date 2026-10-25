# -*- coding: utf-8 -*-
"""INT-1652：迁移 DDL 锁预算的真实 Postgres 红-绿验收。

事故（2026-10-23）：db_bootstrap 的 `ALTER TABLE case_algorithm_params ADD
COLUMN` 排在一条应用层 idle in transaction 的 ACCESS SHARE 后面无限等待；发起
它的 run 容器被删后 Postgres 后端不退出，永久占住锁队列头部，algorithm_service
所有查该表的 SELECT 全部排在这条 ALTER 后面，/algorithm/* 全站 60s 超时。

本文件按 INT-1565 同款方式（真实 Postgres 临时库，用后即删）验证修复：
- 红：一个会话 holding ACCESS EXCLUSIVE 时跑引导步里的 DDL → 必须在
  lock_timeout（本次预算 3s）内失败退出、退出码非零；
- 绿：挡住它的会话释放后同一 DDL 成功；
- 收口：失败后 application_name=db_bootstrap 的会话不留 idle in transaction；
- 定向清理：_cleanup_own_orphans 只 terminate 本 job 的空转后端，别人的不动。
"""
import importlib.util
import os
import time
import uuid

import pytest

psycopg2 = pytest.importorskip('psycopg2')

# tests/conftest.py 的日志重定向钩子会 import BaseConfig（required=True 的 OSS
# 凭据）：本用例不触网，给占位值即可。
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_ENTRYPOINT = os.path.join(PROJECT_ROOT, 'docker', 'db_bootstrap_entrypoint.py')

PG_HOST = os.environ.get('INT35_PG_HOST', '127.0.0.1')
PG_PORT = int(os.environ.get('INT35_PG_PORT', '5432'))
PG_USER = os.environ.get('INT35_PG_USER', 'intelligent_audio_test')
PG_PASSWORD = os.environ.get('INT35_PG_PASSWORD', 'intelligent_audio_test666')

_TABLE = 'int1652_lock_target'
_LOCK_TIMEOUT_MS = 3000


def _pg_params():
    return dict(host=PG_HOST, port=PG_PORT, user=PG_USER,
                password=PG_PASSWORD, connect_timeout=5)


def _pg_reachable():
    try:
        conn = psycopg2.connect(dbname='postgres', **_pg_params())
        conn.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def _load_entrypoint():
    spec = importlib.util.spec_from_file_location('int1652_db_bootstrap_entrypoint_it',
                                                  _ENTRYPOINT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def entrypoint():
    return _load_entrypoint()


@pytest.fixture(scope='module')
def drill_db():
    """真实 Postgres 临时库 + 一张 DDL 演练表，用后即删。"""
    if not _pg_reachable():
        pytest.skip(f'本机 Postgres {PG_HOST}:{PG_PORT} 不可用，INT-1652 锁预算验收跳过')

    dbname = f'int1652_{uuid.uuid4().hex[:10]}'
    admin = psycopg2.connect(dbname='postgres', **_pg_params())
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'CREATE DATABASE {dbname} ENCODING utf8')

    uri = f'postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{dbname}'
    conn = psycopg2.connect(uri)
    with conn.cursor() as cur:
        cur.execute(f'CREATE TABLE {_TABLE} (id INTEGER PRIMARY KEY, note TEXT)')
    conn.commit()
    conn.close()

    yield {'dbname': dbname, 'uri': uri}

    admin = psycopg2.connect(dbname='postgres', **_pg_params())
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS {dbname} WITH (FORCE)')
    admin.close()


def _idle_in_tx_pids(uri, application_name):
    conn = psycopg2.connect(uri, connect_timeout=5)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT pid FROM pg_stat_activity
                 WHERE datname = current_database()
                   AND application_name = %s
                   AND state LIKE 'idle in transaction%%'
            """, (application_name,))
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def _write_ddl_step(tmp_path, uri, column='added_by_int1652'):
    """一个最小的迁移步：就像引导链里的脚本一样，用 libpq 连接执行 DDL。"""
    script = tmp_path / 'ddl_step.py'
    script.write_text(
        'import os\n'
        'import psycopg2\n'
        'conn = psycopg2.connect(os.environ["STEP_DB_URL"])\n'
        'with conn.cursor() as cur:\n'
        f'    cur.execute("ALTER TABLE {_TABLE} ADD COLUMN {column} INTEGER")\n'
        'conn.commit()\n'
        'conn.close()\n',
        encoding='utf-8')
    return script


def _run_ddl_step(entrypoint, drill_db, tmp_path, monkeypatch, column):
    """以引导入口的真实口径（_prepare_env 的 PGOPTIONS + _run_step）跑一个 DDL 步。"""
    monkeypatch.setenv('DATABASE_URI', drill_db['uri'])
    monkeypatch.setenv('DB_BOOTSTRAP_LOCK_TIMEOUT_MS', str(_LOCK_TIMEOUT_MS))
    monkeypatch.delenv('PGOPTIONS', raising=False)
    env = entrypoint._prepare_env(entrypoint.lock_budget())
    env['STEP_DB_URL'] = drill_db['uri']
    script = _write_ddl_step(tmp_path, drill_db['uri'], column)
    started = time.monotonic()
    rc, timed_out = entrypoint._run_step((os.sys.executable, str(script)),
                                         str(tmp_path), env, 'y', step_timeout_s=60)
    return rc, timed_out, time.monotonic() - started


def test_locked_table_makes_ddl_fail_fast_then_succeeds_after_release(
        entrypoint, drill_db, tmp_path, monkeypatch):
    """红 → 绿：等锁超时 ≤ lock_timeout 内失败退出，放锁后同一 DDL 成功。"""
    blocker = psycopg2.connect(drill_db['uri'], connect_timeout=5,
                              application_name='int1652_blocker')
    try:
        with blocker.cursor() as cur:
            cur.execute(f'LOCK TABLE {_TABLE} IN ACCESS EXCLUSIVE MODE')
        # 红：DDL 必须被锁预算打断，而不是一直等
        rc, timed_out, elapsed = _run_ddl_step(entrypoint, drill_db, tmp_path,
                                               monkeypatch, column='col_red')
        assert timed_out is False, 'DDL 步被进程级超时兜底打断，说明锁预算没生效'
        assert rc != 0, '持 ACCESS EXCLUSIVE 时 DDL 竟然成功了'
        assert _LOCK_TIMEOUT_MS / 1000 <= elapsed <= 20, \
            f'DDL 等锁 {elapsed:.1f}s，超出 lock_timeout 预算'
        # 失败后不留本 job 的 idle in transaction
        assert _idle_in_tx_pids(drill_db['uri'], entrypoint.BOOTSTRAP_APP_NAME) == []
    finally:
        blocker.rollback()          # 释放 ACCESS EXCLUSIVE（演练只在隔离库）
        blocker.close()

    # 绿：放锁后同一 DDL 成功
    rc, timed_out, _ = _run_ddl_step(entrypoint, drill_db, tmp_path,
                                     monkeypatch, column='col_green')
    assert timed_out is False
    assert rc == 0

    conn = psycopg2.connect(drill_db['uri'], connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                 WHERE table_name = %s AND column_name = 'col_green'
            """, (_TABLE,))
            assert cur.fetchone() is not None
    finally:
        conn.close()


def test_cleanup_only_terminates_own_orphan_sessions(entrypoint, drill_db, monkeypatch):
    """失败清理只 terminate application_name=db_bootstrap 的空转后端。"""
    monkeypatch.setenv('DATABASE_URI', drill_db['uri'])
    monkeypatch.delenv('PGOPTIONS', raising=False)
    env = entrypoint._prepare_env(entrypoint.lock_budget())

    own = psycopg2.connect(drill_db['uri'], connect_timeout=5,
                           application_name=entrypoint.BOOTSTRAP_APP_NAME)
    other = psycopg2.connect(drill_db['uri'], connect_timeout=5,
                             application_name='int1652_other_service')
    try:
        with own.cursor() as cur:
            cur.execute('SELECT 1')         # 开事务后停下 → idle in transaction
        own_pid = own.get_backend_pid()
        with other.cursor() as cur:
            cur.execute('SELECT 1')

        assert own_pid in _idle_in_tx_pids(drill_db['uri'],
                                           entrypoint.BOOTSTRAP_APP_NAME)
        terminated = entrypoint._cleanup_own_orphans(env)

        assert own_pid in terminated
        # 别人的会话必须原样活着
        with other.cursor() as cur:
            cur.execute('SELECT 1')
            assert cur.fetchone()[0] == 1
    finally:
        try:
            other.rollback()
            other.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            own.close()
        except Exception:  # noqa: BLE001
            pass
