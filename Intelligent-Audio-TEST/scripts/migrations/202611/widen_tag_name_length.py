# -*- coding: utf-8 -*-
"""迁移脚本：标签 / 标签分类名称上限 50 → 100

背景：
- 标签与标签分类名称在 ORM 里是 ``String(50)``（DDL ``VARCHAR(50)``），
  服务层 ``TagCrudService.NAME_MAX_LENGTH = 50``、前端常量
  ``TAG_NAME_MAX_LENGTH = 50`` 也按 50 校验。
- 50 字符对「场景 + 语种 + 人数」这类组合命名不够用，本迁移把两张表 ``name``
  放宽到 100；服务层 / 前端常量同步改为 100（随代码一起发布）。

DDL（与 task_service/infrastructure/persistence/models/testcase_models.py 对齐）：
    SET lock_timeout = '10s'
    ALTER TABLE tag_categories ALTER COLUMN name TYPE VARCHAR(100)
    ALTER TABLE tags           ALTER COLUMN name TYPE VARCHAR(100)

执行语义：
- 默认 dry-run：打印待执行 DDL 与两表当前列宽，不改库；
- ``--apply``：单事务执行（DDL 在 PostgreSQL 可事务化，失败整体回滚）；
- ``--rollback``：改回 VARCHAR(50)；改小前先检查存量是否有超过 50 字符的行，
  有则拒绝并列出样例，避免静默截断失败；
- 幂等：列宽已是目标宽度即 SKIP。

用法：
    python scripts/migrations/202611/widen_tag_name_length.py            # 预览
    python scripts/migrations/202611/widen_tag_name_length.py --apply    # 执行
    python scripts/migrations/202611/widen_tag_name_length.py --rollback --apply
"""
import argparse
import os
import sys
import time
from urllib.parse import urlparse

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

LOCK_TIMEOUT = '10s'
TARGET_LENGTH = 100
LEGACY_LENGTH = 50
TABLES = ('tag_categories', 'tags')


def _connect():
    parsed = urlparse(os.environ['DATABASE_URL'])
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password, application_name='migration_tag_name_length')


def _table_exists(cur, table):
    cur.execute(
        'SELECT 1 FROM information_schema.tables '
        'WHERE table_schema = current_schema() AND table_name = %s', (table,))
    return cur.fetchone() is not None


def _name_length(cur, table):
    """name 列当前字符上限；列不存在返回 None。"""
    cur.execute(
        'SELECT character_maximum_length FROM information_schema.columns '
        'WHERE table_schema = current_schema() '
        'AND table_name = %s AND column_name = %s', (table, 'name'))
    row = cur.fetchone()
    return None if row is None else row[0]


def _too_long_count(cur, table):
    cur.execute(
        f'SELECT COUNT(*) FROM {table} WHERE char_length(name) > %s',
        (LEGACY_LENGTH,))
    return int(cur.fetchone()[0] or 0)


def _too_long_samples(cur, table, limit=5):
    cur.execute(
        f'SELECT id, name FROM {table} WHERE char_length(name) > %s '
        f'ORDER BY char_length(name) DESC LIMIT %s', (LEGACY_LENGTH, limit))
    return cur.fetchall()


def _forward_statements(cur):
    stmts = []
    for table in TABLES:
        if not _table_exists(cur, table):
            print(f'[SKIP] 表 {table} 不存在（空库请先 create_all_tables.py）')
            continue
        current = _name_length(cur, table)
        if current is None:
            print(f'[SKIP] {table}.name 不存在')
            continue
        if current == TARGET_LENGTH:
            print(f'[SKIP] {table}.name 已是 VARCHAR({TARGET_LENGTH})')
            continue
        stmts.append(
            (f'{table}.name',
             f'ALTER TABLE {table} ALTER COLUMN name TYPE VARCHAR({TARGET_LENGTH})'))
    return stmts


def _rollback_statements(cur):
    stmts = []
    blocked = False
    for table in TABLES:
        if not _table_exists(cur, table):
            print(f'[SKIP] 表 {table} 不存在')
            continue
        current = _name_length(cur, table)
        if current is None:
            print(f'[SKIP] {table}.name 不存在')
            continue
        if current == LEGACY_LENGTH:
            print(f'[SKIP] {table}.name 已是 VARCHAR({LEGACY_LENGTH})')
            continue
        over = _too_long_count(cur, table)
        if over:
            blocked = True
            print(f'[FAIL] {table} 有 {over} 行名称超过 {LEGACY_LENGTH} 字符，'
                  '回滚会失败或截断，已拒绝。样例：')
            for row_id, name in _too_long_samples(cur, table):
                print(f'       id={row_id} len={len(name)} name={name!r}')
            continue
        stmts.append(
            (f'{table}.name',
             f'ALTER TABLE {table} ALTER COLUMN name TYPE VARCHAR({LEGACY_LENGTH})'))
    if blocked:
        return None
    return stmts


def _precheck(cur):
    for table in TABLES:
        if not _table_exists(cur, table):
            print(f'[INFO] {table}: 表不存在')
            continue
        length = _name_length(cur, table)
        print(f'[INFO] {table}.name: '
              f'{"列不存在" if length is None else f"VARCHAR({length})"}')
        if length is not None:
            try:
                cur.execute(f'SELECT COUNT(*) FROM {table}')
                print(f'[INFO] {table}: {int(cur.fetchone()[0] or 0)} 行')
            except psycopg2.Error:
                pass


def _run(apply, statements_factory, label):
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
        stmts = statements_factory(cur)
        if stmts is None:
            conn.rollback()
            return 1
        if not conn.autocommit:
            conn.rollback()
        if not stmts:
            print(f'[SKIP] 结构已是{label}后形态，无需执行')
            return 0
        for name, sql in stmts:
            print(f"[{'DRY' if not apply else 'APPLY'}] {sql}")
        if not apply:
            print('[DRY] 未执行；加 --apply 生效')
            return 0

        started = time.time()
        try:
            cur.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
            for name, sql in stmts:
                cur.execute(sql)
                print(f'[OK] {name} 完成')
            conn.commit()
        except psycopg2.Error as exc:
            conn.rollback()
            print(f'[FAIL] {label}失败（pgcode={getattr(exc, "pgcode", None)}）：'
                  f'{exc}')
            return 1
        print(f'[APPLY] {label}完成，耗时 {time.time() - started:.2f}s')
        return 0
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description='标签名上限 50 → 100')
    ap.add_argument('--apply', action='store_true', help='执行（默认 dry-run 预览）')
    ap.add_argument('--rollback', action='store_true',
                    help='改回 VARCHAR(50)（默认 dry-run，配 --apply 执行）')
    args = ap.parse_args()

    conn = _connect()
    try:
        _precheck(conn.cursor())
    finally:
        conn.close()

    if args.rollback:
        return _run(args.apply, _rollback_statements, '回滚')
    return _run(args.apply, _forward_statements, '迁移')


if __name__ == '__main__':
    sys.exit(main())
