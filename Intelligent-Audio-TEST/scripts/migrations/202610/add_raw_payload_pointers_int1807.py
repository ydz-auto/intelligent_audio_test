# -*- coding: utf-8 -*-
"""迁移脚本：test_result_dimensions 补原始报文指针列（INT-1807 / C1）

背景：``test_result_dimensions.api_raw_response`` / ``api_request_body`` 是 JSON
列，与维度评分行耦合在一起——同一份厂商报文按「维度 × 轮」重复落库（主库实测
51,857 行，去重后仅 6,506 个不同响应 + 6,259 个不同请求体），TOAST 占 275MB。
本卡给表补**指针列**：把报文按内容寻址搬进对象存储（``raw/resp/<sha[:2]>/<sha>.json.gz``
/ ``raw/req/...``），行上只留 uri + sha256 + 压缩字节数 + content_type + 写入时间。

本卡**只加列、只加回填脚本**，不改任何线上读写路径（写路径切换归 C2、删列归 M1）：
合入部署后应用照旧写 JSON 列，新列全为 NULL，没有任何代码读它。

列定义（两组，request 与 response 是独立对象、独立去重，不打包成一份）：
    api_raw_response_uri          text         NULL  内容寻址对象路径
    api_raw_response_sha256       char(64)     NULL  规范化 JSON 字节的 sha256
    api_raw_response_bytes        integer      NULL  对象压缩后字节数（gzip）
    api_raw_response_content_type varchar(64)  NULL  固定 application/json+gzip
    api_raw_response_created_at   timestamptz  NULL  对象写入时间
    api_request_body_  同构五列
全部可空、无默认值、无索引：存量行天然兼容；读侧按 (test_result_id, round_number)
定位后按行取 uri，不需要指针列上的独立索引。

DDL 与 evaluation_service/infrastructure/persistence/models/result_models.py 的
TestResultDimension 元数据逐列对齐（全新库 create_all 已含这些列，执行为全 [SKIP]）。

锁预算（INT-1652 口径）：10 个 ADD COLUMN 合成**一条** ALTER TABLE 语句，只拿一次
ACCESS EXCLUSIVE 锁；lock_timeout 默认 5s（DB_MIGRATION_LOCK_TIMEOUT_MS 可覆盖），
拿不到就失败退出并打印持锁者，绝不排队堵住整张表。

回滚说明：新列无人读，可随时弃——回退镜像即可（对象是派生物）。
确需回滚结构时：
    ALTER TABLE test_result_dimensions
      DROP COLUMN IF EXISTS api_raw_response_uri, ... ;  -- 全部 10 列

用法：
    python scripts/migrations/202610/add_raw_payload_pointers_int1807.py            # 预览
    python scripts/migrations/202610/add_raw_payload_pointers_int1807.py --apply    # 执行

幂等性：列已存在即 SKIP（逐列判定，只对缺失列发 DDL）；列注释每次重写（catalog
级、幂等）；重复执行不产生任何表重写。
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

TABLE = 'test_result_dimensions'
DEFAULT_LOCK_TIMEOUT_MS = 5000
DEFAULT_STATEMENT_TIMEOUT_MS = 300000

# (列名, DDL 类型, information_schema 期望的 (data_type, character_maximum_length), 注释)
# 顺序 = 模型里的列顺序（响应组在前、请求组在后），便于与 ORM 逐列对拍。
COLUMNS = (
    ('api_raw_response_uri', 'text', ('text', None),
     '原始响应对象路径（内容寻址 raw/resp/{sha[:2]}/{sha}.json.gz）'),
    ('api_raw_response_sha256', 'char(64)', ('character', 64),
     '响应规范化 JSON 字节的 sha256（内容寻址 key 的取值依据）'),
    ('api_raw_response_bytes', 'integer', ('integer', None),
     '响应对象压缩后字节数（gzip）'),
    ('api_raw_response_content_type', 'varchar(64)', ('character varying', 64),
     '响应对象 content_type（固定 application/json+gzip）'),
    ('api_raw_response_created_at', 'timestamptz', ('timestamp with time zone', None),
     '响应对象写入时间'),
    ('api_request_body_uri', 'text', ('text', None),
     '请求体对象路径（内容寻址 raw/req/{sha[:2]}/{sha}.json.gz）'),
    ('api_request_body_sha256', 'char(64)', ('character', 64),
     '请求体规范化 JSON 字节的 sha256（内容寻址 key 的取值依据）'),
    ('api_request_body_bytes', 'integer', ('integer', None),
     '请求体对象压缩后字节数（gzip）'),
    ('api_request_body_content_type', 'varchar(64)', ('character varying', 64),
     '请求体对象 content_type（固定 application/json+gzip）'),
    ('api_request_body_created_at', 'timestamptz', ('timestamp with time zone', None),
     '请求体对象写入时间'),
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
        password=parsed.password, application_name='migration_int1807')


def _table_exists(cur) -> bool:
    cur.execute(
        'SELECT 1 FROM information_schema.tables WHERE table_name = %s', (TABLE,))
    return cur.fetchone() is not None


def _existing_columns(cur) -> dict:
    """返回 {列名: (data_type, character_maximum_length, is_nullable, column_default)}。"""
    cur.execute(
        'SELECT column_name, data_type, character_maximum_length, is_nullable, '
        'column_default FROM information_schema.columns WHERE table_name = %s',
        (TABLE,))
    return {row[0]: row[1:] for row in cur.fetchall()}


def _missing_columns(existing: dict):
    return [(name, ddl_type) for name, ddl_type, _expected, _comment in COLUMNS
            if name not in existing]


def build_add_column_ddl(missing) -> str:
    """把缺失列合成一条 ALTER TABLE（一次 AccessExclusiveLock）。"""
    parts = [f'ADD COLUMN IF NOT EXISTS {name} {ddl_type}' for name, ddl_type in missing]
    return f'ALTER TABLE {TABLE} ' + ', '.join(parts)


def _blocking_pids(cur):
    """持锁阻塞别人的后端 pid（诊断用）。"""
    cur.execute(
        'SELECT DISTINCT l.pid FROM pg_locks l '
        'JOIN pg_stat_activity a ON a.pid = l.pid '
        'WHERE l.granted AND l.relation = %s::regclass AND a.pid <> pg_backend_pid()',
        (TABLE,))
    return [row[0] for row in cur.fetchall()]


def _waiting_lock_pids(cur):
    """当前在该表上等锁的后端 pid（只用于失败诊断，不参与判定）。"""
    cur.execute(
        'SELECT pid FROM pg_locks WHERE NOT granted AND relation = %s::regclass',
        (TABLE,))
    return [row[0] for row in cur.fetchall()]


def _verify(cur) -> bool:
    """逐列校验类型 / 可空 / 无默认值；任一不符返回 False。"""
    existing = _existing_columns(cur)
    ok = True
    for name, _ddl, (want_type, want_len), _comment in COLUMNS:
        row = existing.get(name)
        if not row:
            print(f'[VERIFY][FAIL] {TABLE}.{name} 不存在')
            ok = False
            continue
        data_type, max_len, nullable, default = row
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
        print(f'[VERIFY] {name}: {data_type}({max_len}) '
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

        if not _table_exists(cur):
            print(f'[SKIP] 表 {TABLE} 不存在（空库请先 create_all_tables.py）')
            return

        missing = _missing_columns(_existing_columns(cur))
        if not missing:
            print(f'[SKIP] {len(COLUMNS)} 列均已存在')
            _verify(cur)
            return

        print(f'[{"DRY" if dry_run else "APPLY"}] 缺失 {len(missing)} 列：'
              f'{", ".join(name for name, _ in missing)}')
        ddl = build_add_column_ddl(missing)
        print(f'[{"DRY" if dry_run else "APPLY"}] {ddl}')
        if dry_run:
            print('[DRY] 未执行 DDL；--apply 时按 lock_timeout='
                  f'{lock_timeout_ms}ms / statement_timeout='
                  f'{statement_timeout_ms}ms 执行')
            return

        waiting = _waiting_lock_pids(cur)
        if waiting:
            print(f'[WARN] 迁移前该表已有等锁后端 pid={waiting}')

        started = time.monotonic()
        try:
            cur.execute(ddl)
            conn.commit()
        except psycopg2.errors.LockNotAvailable:
            conn.rollback()
            print(f'[FAIL] {lock_timeout_ms}ms 内未拿到 ACCESS EXCLUSIVE 锁；'
                  f'持锁者 pid={_blocking_pids(cur)}，等锁者 pid={_waiting_lock_pids(cur)}')
            raise SystemExit(2)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        print(f'[APPLY] 加列完成 {len(missing)} 列，耗时 {elapsed_ms}ms'
              f'（lock_timeout={lock_timeout_ms}ms，未触发=等锁低于预算）')

        # 列注释：与 ORM comment 对齐（create_all 新库自带），catalog 级幂等
        for name, _ddl, _expected, comment in COLUMNS:
            cur.execute(f"COMMENT ON COLUMN {TABLE}.{name} IS %s", (comment,))
        conn.commit()

        if not _verify(cur):
            raise SystemExit(3)
        cur.close()
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(
        description='test_result_dimensions 补原始报文指针列（INT-1807 / C1）')
    ap.add_argument('--apply', action='store_true', help='执行（默认 dry-run 预览）')
    args = ap.parse_args()
    migrate(dry_run=not args.apply)


if __name__ == '__main__':
    main()
