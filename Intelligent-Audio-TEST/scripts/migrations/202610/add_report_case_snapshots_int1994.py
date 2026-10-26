# -*- coding: utf-8 -*-
"""迁移脚本：report_case_snapshots 表 + report_cases 4 个指针列（INT-1994 / 档4 R1）

背景：``report_cases`` 是报告级用例行，每份报告把用例配置**整份**再落一次库，同
一份配置在几十份报告里重复（主库实测 33,925 行 / 258MB；九字段 payload 去重后
仅 10,843 个不同值）。R1 把九个字段按 ``sha256(规范化 JSON)`` 内容寻址外置到
``report_case_snapshots``，行上只留 4 个指针列，**双写期间原内容列照旧写**。

本脚本**只建表 / 加列**。回填与门禁在
``backfill_report_case_snapshots_int1994.py``（33,925 行写，不进引导链，独立窗口跑）。

DDL（列定义与
``report_service/infrastructure/persistence/models/report_case_snapshot_models.py`` /
``report_models.py`` 逐列对齐，全新库 create_all 已含，执行为全 [SKIP]）：

    CREATE TABLE report_case_snapshots (
      sha256        char(64) PRIMARY KEY,       -- 内容寻址主键
      payload_gz    bytea NOT NULL,             -- 九字段规范化 JSON 的 gzip 体
      payload_bytes integer,                    -- 压缩后字节数
      created_at    timestamptz NOT NULL DEFAULT now()
    );
    ALTER TABLE report_case_snapshots ALTER COLUMN payload_gz SET STORAGE EXTERNAL;
    ALTER TABLE report_cases
      ADD COLUMN IF NOT EXISTS snapshot_uri          varchar(128),
      ADD COLUMN IF NOT EXISTS snapshot_sha256       char(64),
      ADD COLUMN IF NOT EXISTS snapshot_bytes        bigint,
      ADD COLUMN IF NOT EXISTS snapshot_created_at   timestamptz;

`payload_gz` 必带 ``SET STORAGE EXTERNAL``：内容已经是 gzip 体，TOAST 的二次压缩
只会白烧 CPU 且拿不到压缩比。

**不建 ``deleted`` / ``report_id`` / 任何索引**：纯内容寻址，引用集合以
``report_cases`` 为准；R1 期间旧内容列还在，指针列不需要独立索引。**不 DROP 任何
列、不 VACUUM FULL**（M1 的范围）。

锁预算（INT-1652 口径）：4 个 ADD COLUMN 合成**一条** ALTER TABLE，只拿一次
ACCESS EXCLUSIVE 锁；lock_timeout 默认 5s（DB_MIGRATION_LOCK_TIMEOUT_MS 可覆盖），
拿不到就失败退出并打印持锁者，绝不排队堵住整张表。

回滚说明：新表与新列无人写错时可直接弃（回退镜像 + ``REPORT_CASE_SNAPSHOT_SOURCE
=column`` 即可回到列读）；确需回滚结构时：
    DROP TABLE IF EXISTS report_case_snapshots;
    ALTER TABLE report_cases DROP COLUMN IF EXISTS snapshot_uri, ... ;  -- 4 列

用法：
    python scripts/migrations/202610/add_report_case_snapshots_int1994.py           # 预览
    python scripts/migrations/202610/add_report_case_snapshots_int1994.py --apply   # 执行

幂等性：表 / 列已存在即 SKIP；列注释每次重写（catalog 级、幂等）；重复执行不产生
任何表重写。
"""
import argparse
import os
import sys
import time

import psycopg2

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')

SNAPSHOT_TABLE = 'report_case_snapshots'
CASES_TABLE = 'report_cases'
DEFAULT_LOCK_TIMEOUT_MS = 5000
DEFAULT_STATEMENT_TIMEOUT_MS = 300000

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SNAPSHOT_TABLE} (
    sha256        char(64)    NOT NULL PRIMARY KEY,
    payload_gz    bytea       NOT NULL,
    payload_bytes integer,
    created_at    timestamptz NOT NULL DEFAULT now()
)
""".strip()

#: payload_gz 已经是 gzip 体，关掉 TOAST 二次压缩（幂等，可重复执行）
STORAGE_SQL = (f'ALTER TABLE {SNAPSHOT_TABLE} '
               f'ALTER COLUMN payload_gz SET STORAGE EXTERNAL')

COMMENT_SQL = (
    (f"COMMENT ON TABLE {SNAPSHOT_TABLE} IS "
     "'报告用例配置内容寻址快照（INT-1994 / 档4 R1）：九字段 payload 一份一行'"),
    (f"COMMENT ON COLUMN {SNAPSHOT_TABLE}.sha256 IS "
     "'九字段规范化 JSON 字节的 sha256（内容寻址主键）'"),
    (f"COMMENT ON COLUMN {SNAPSHOT_TABLE}.payload_gz IS "
     "'九字段规范化 JSON 的 gzip 体（STORAGE EXTERNAL）'"),
    (f"COMMENT ON COLUMN {SNAPSHOT_TABLE}.payload_bytes IS '压缩后字节数（gzip）'"),
    (f"COMMENT ON COLUMN {SNAPSHOT_TABLE}.created_at IS "
     "'快照行写入时间（不是冻结时间；冻结时间看 report_cases.snapshot_created_at）'"),
)

# (列名, DDL 类型, information_schema 期望的 (data_type, character_maximum_length), 注释)
# 顺序 = ORM 里 ReportCase 的列顺序，便于逐列对拍。
COLUMNS = (
    ('snapshot_uri', 'varchar(128)', ('character varying', 128),
     '快照载体路径 db://report_case_snapshots/{sha256}'),
    ('snapshot_sha256', 'char(64)', ('character', 64),
     '快照内容主键（解引用 / 回填判据 / 门禁 / sweep 的一等键）'),
    ('snapshot_bytes', 'bigint', ('bigint', None),
     '快照压缩后字节数（gzip）'),
    ('snapshot_created_at', 'timestamptz', ('timestamp with time zone', None),
     '该快照对应内容的生成时间（在线=写入时刻，回填=源行 created_at）'),
)


def _int_env(name, default):
    """读取正整数环境变量，非法值回落默认。"""
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == '':
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _connect():
    from urllib.parse import urlparse
    parsed = urlparse(os.environ['DATABASE_URL'])
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password, application_name='migration_int1994')


def _table_exists(cur, table) -> bool:
    cur.execute(
        'SELECT 1 FROM information_schema.tables WHERE table_name = %s', (table,))
    return cur.fetchone() is not None


def _existing_columns(cur, table) -> dict:
    """返回 {列名: (data_type, character_maximum_length, is_nullable, column_default)}。"""
    cur.execute(
        'SELECT column_name, data_type, character_maximum_length, is_nullable, '
        'column_default FROM information_schema.columns WHERE table_name = %s',
        (table,))
    return {row[0]: row[1:] for row in cur.fetchall()}


def _missing_columns(existing: dict):
    return [(name, ddl_type) for name, ddl_type, _expected, _comment in COLUMNS
            if name not in existing]


def build_add_column_ddl(missing) -> str:
    """把缺失列合成一条 ALTER TABLE（一次 AccessExclusiveLock）。"""
    parts = [f'ADD COLUMN IF NOT EXISTS {name} {ddl_type}' for name, ddl_type in missing]
    return f'ALTER TABLE {CASES_TABLE} ' + ', '.join(parts)


def _blocking_pids(cur, table):
    """持锁阻塞别人的后端 pid（诊断用；表还没建时 to_regclass 返回 NULL，不报错）。"""
    cur.execute(
        'SELECT DISTINCT l.pid FROM pg_locks l '
        'JOIN pg_stat_activity a ON a.pid = l.pid '
        'WHERE l.granted AND l.relation = to_regclass(%s) '
        'AND a.pid <> pg_backend_pid()',
        (table,))
    return [row[0] for row in cur.fetchall()]


def _waiting_lock_pids(cur, table):
    """当前在该表上等锁的后端 pid（只用于失败诊断，不参与判定）。"""
    cur.execute(
        'SELECT pid FROM pg_locks WHERE NOT granted AND relation = to_regclass(%s)',
        (table,))
    return [row[0] for row in cur.fetchall()]


def _verify(cur) -> bool:
    """逐项校验：新表列类型 / 可空性、payload_gz 存储策略、4 个指针列。"""
    ok = True
    if not _table_exists(cur, SNAPSHOT_TABLE):
        print(f'[VERIFY][FAIL] 表 {SNAPSHOT_TABLE} 不存在')
        return False
    cur.execute(
        "SELECT attname, attstorage FROM pg_attribute "
        "WHERE attrelid = %s::regclass AND attname = 'payload_gz'", (SNAPSHOT_TABLE,))
    row = cur.fetchone()
    if not row:
        print('[VERIFY][FAIL] payload_gz 列不存在')
        ok = False
    else:
        # pg_attribute.attstorage：p=PLAIN / e=EXTERNAL / m=MAIN / x=EXTENDED
        #（bytea 默认 'x'，本卡要求 'e'）
        storage = row[1]
        status = 'OK' if storage == 'e' else f'FAIL 期望 EXTERNAL(e)，实际 {storage}'
        if storage != 'e':
            ok = False
        print(f'[VERIFY] {SNAPSHOT_TABLE}.payload_gz storage -> {status}')

    existing = _existing_columns(cur, SNAPSHOT_TABLE)
    expected_snapshot = {
        'sha256': ('character', 64, 'NO'),
        'payload_gz': ('bytea', None, 'NO'),
        'payload_bytes': ('integer', None, 'YES'),
        'created_at': ('timestamp with time zone', None, 'NO'),
    }
    for name, (want_type, want_len, want_nullable) in expected_snapshot.items():
        info = existing.get(name)
        if not info:
            print(f'[VERIFY][FAIL] {SNAPSHOT_TABLE}.{name} 不存在')
            ok = False
            continue
        data_type, max_len, nullable, _default = info
        status = 'OK'
        if (data_type, max_len) != (want_type, want_len):
            status = f'FAIL 期望 {want_type}({want_len})'
            ok = False
        elif nullable != want_nullable:
            status = f'FAIL 期望 nullable={want_nullable}'
            ok = False
        print(f'[VERIFY] {SNAPSHOT_TABLE}.{name}: {data_type}({max_len}) '
              f'{"NULL" if nullable == "YES" else "NOT NULL"} -> {status}')

    cases_columns = _existing_columns(cur, CASES_TABLE)
    for name, _ddl, (want_type, want_len), _comment in COLUMNS:
        info = cases_columns.get(name)
        if not info:
            print(f'[VERIFY][FAIL] {CASES_TABLE}.{name} 不存在')
            ok = False
            continue
        data_type, max_len, nullable, default = info
        status = 'OK'
        if (data_type, max_len) != (want_type, want_len):
            status = f'FAIL 期望 {want_type}({want_len})'
            ok = False
        elif nullable != 'YES':
            status = 'FAIL 期望可空'
            ok = False
        elif default is not None:
            status = f'FAIL 期望无默认值，实际 {default}'
            ok = False
        print(f'[VERIFY] {CASES_TABLE}.{name}: {data_type}({max_len}) '
              f'{"NULL" if nullable == "YES" else "NOT NULL"} '
              f'DEFAULT {default} -> {status}')
    return ok


def migrate(dry_run=True):
    lock_timeout_ms = _int_env('DB_MIGRATION_LOCK_TIMEOUT_MS',
                               DEFAULT_LOCK_TIMEOUT_MS)
    statement_timeout_ms = _int_env('DB_MIGRATION_STATEMENT_TIMEOUT_MS',
                                    DEFAULT_STATEMENT_TIMEOUT_MS)
    conn = _connect()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(f'SET lock_timeout = {lock_timeout_ms}')
        cur.execute(f'SET statement_timeout = {statement_timeout_ms}')

        if not _table_exists(cur, CASES_TABLE):
            print(f'[SKIP] 表 {CASES_TABLE} 不存在（空库请先 create_all_tables.py）')
            return

        need_table = not _table_exists(cur, SNAPSHOT_TABLE)
        missing = _missing_columns(_existing_columns(cur, CASES_TABLE))

        if not need_table and not missing:
            print(f'[SKIP] 表 {SNAPSHOT_TABLE} 与 {len(COLUMNS)} 列均已存在')
            _verify(cur)
            return

        tag = 'DRY' if dry_run else 'APPLY'
        if need_table:
            print(f'[{tag}] CREATE TABLE IF NOT EXISTS {SNAPSHOT_TABLE} (...)')
        if missing:
            print(f'[{tag}] 缺失 {len(missing)} 列：'
                  f'{", ".join(name for name, _ in missing)}')
            print(f'[{tag}] {build_add_column_ddl(missing)}')
        if dry_run:
            print('[DRY] 未执行 DDL；--apply 时按 lock_timeout='
                  f'{lock_timeout_ms}ms / statement_timeout='
                  f'{statement_timeout_ms}ms 执行')
            return

        waiting = _waiting_lock_pids(cur, SNAPSHOT_TABLE) + _waiting_lock_pids(cur, CASES_TABLE)
        if waiting:
            print(f'[WARN] 迁移前已有等锁后端 pid={waiting}')

        started = time.monotonic()
        try:
            if need_table:
                cur.execute(CREATE_TABLE_SQL)
                print(f'[APPLY] 建表 {SNAPSHOT_TABLE} 完成')
            cur.execute(STORAGE_SQL)
            if missing:
                cur.execute(build_add_column_ddl(missing))
            conn.commit()
        except psycopg2.errors.LockNotAvailable:
            conn.rollback()
            print(f'[FAIL] {lock_timeout_ms}ms 内未拿到 ACCESS EXCLUSIVE 锁；'
                  f'持锁者 pid={_blocking_pids(cur, CASES_TABLE) + _blocking_pids(cur, SNAPSHOT_TABLE)}，'
                  f'等锁者 pid={_waiting_lock_pids(cur, CASES_TABLE) + _waiting_lock_pids(cur, SNAPSHOT_TABLE)}')
            raise SystemExit(2)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        print(f'[APPLY] DDL 完成（表={need_table}，列={len(missing)}），耗时 {elapsed_ms}ms'
              f'（lock_timeout={lock_timeout_ms}ms，未触发=等锁低于预算）')

        for sql in COMMENT_SQL:
            cur.execute(sql)
        for name, _ddl, _expected, comment in COLUMNS:
            cur.execute(f"COMMENT ON COLUMN {CASES_TABLE}.{name} IS %s", (comment,))
        conn.commit()

        if not _verify(cur):
            raise SystemExit(3)
        cur.close()
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(
        description='report_case_snapshots 表 + report_cases 4 个指针列'
                    '（INT-1994 / 档4 R1）')
    ap.add_argument('--apply', action='store_true', help='执行（默认 dry-run 预览）')
    args = ap.parse_args()
    migrate(dry_run=not args.apply)


if __name__ == '__main__':
    main()
