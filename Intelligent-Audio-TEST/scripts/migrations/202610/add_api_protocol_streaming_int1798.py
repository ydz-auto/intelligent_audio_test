# -*- coding: utf-8 -*-
"""迁移脚本：apis 加协议 × 流式性两列并回填、删 meta.protocol（INT-1799 / B1）

背景（B0 裁定文档 `doc/功能设计文档/01_测试执行/09_API协议面与执行道契约.md`）：
- 协议与流式性原先被压进一个枚举 `apis.device_type`（http_api 同时表示
  「http」与「非流式」，websocket_api 同时表示「websocket」与「流式」），
  执行路由直接吃该枚举，还用 `rounds>1` 二次推断流式性（负责人说的遗留问题）；
- 负责人 2026-10-24 拍板：拆成 `protocol`（http/websocket/sse/grpc）与
  `streaming`（true=流式）两列，`device_type` 退场（本卡不再读写，列留 P3 删），
  `meta.protocol` 迁移后删除、不保留只读。

步骤（同一脚本内固定顺序，校验不通过则回滚且不写任何行）：
    ① 加两列（可空，避免存量行违反 NOT NULL）
    ② 校验 + 回填：
       device_type  http_api       → protocol='http',      streaming=false
       device_type  websocket_api  → protocol='websocket', streaming=true
       physical / NULL / 空 / 其他 → 非法：中止并列出 id
       meta.protocol 交叉校验（仅当键存在）：
         http/https→http，ws/wss→websocket，sse→sse，grpc→grpc，其他→中止；
         归一后的协议必须与 device_type 推出的协议一致，否则中止（不猜不覆盖）
    ③ 收紧约束 + 补默认（protocol='http' / streaming=false，NOT NULL）
    ④ 删除 apis.meta 的 protocol 键（只删该键，其余键保留）

用法：
    python scripts/migrations/202610/add_api_protocol_streaming_int1799.py          # 预览
    python scripts/migrations/202610/add_api_protocol_streaming_int1799.py --apply  # 执行

幂等：列已存在且已 NOT NULL → ①②③ SKIP；回填按值比对只写有差异的行；
meta 无 protocol 键 → ④ 跳过；全新库（ORM 建表已含两列）全 SKIP。
"""
import argparse
import json
import os
import sys
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

from shared.models.common_enums import normalize_protocol  # noqa: E402

TABLE = 'apis'
PROTOCOL_COL = 'protocol'
STREAMING_COL = 'streaming'
LOCK_TIMEOUT_MS = 5000
STATEMENT_TIMEOUT_MS = 300000

# device_type → (protocol, streaming)；physical 不在 apis 表语义内（非法）
DEVICE_TYPE_MAPPING = {
    'http_api': ('http', False),
    'websocket_api': ('websocket', True),
}


def _connect():
    parsed = urlparse(os.environ['DATABASE_URL'])
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password)


def _column_state(cur, column):
    """返回 (exists: bool, is_nullable: str|None)。"""
    cur.execute(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s", (TABLE, column))
    row = cur.fetchone()
    return (row is not None, row[0] if row else None)


def _has_meta_protocol_key(cur):
    cur.execute(
        f"SELECT count(*) FROM {TABLE} WHERE meta IS NOT NULL "
        f"AND meta::jsonb ? 'protocol'")
    return cur.fetchone()[0]


def _resolve_row(api_id, device_type, meta_raw):
    """单行映射 + 交叉校验；返回 ((protocol, streaming), None) 或 (None, 原因)。"""
    key = (device_type or '').strip()
    mapping = DEVICE_TYPE_MAPPING.get(key)
    if mapping is None:
        return None, f"非法的 device_type={device_type!r}（apis 表不承载物理设备）"
    protocol, streaming = mapping

    meta = {}
    if meta_raw:
        try:
            parsed = json.loads(meta_raw)
            if isinstance(parsed, dict):
                meta = parsed
        except (TypeError, ValueError):
            return None, f"meta 不是合法 JSON: {meta_raw[:80]!r}"
    if 'protocol' in meta:
        try:
            meta_protocol = normalize_protocol(meta['protocol'])
        except ValueError as e:
            return None, f"非法 meta.protocol={meta['protocol']!r}: {e}"
        if meta_protocol != protocol:
            return None, (f"meta.protocol={meta['protocol']!r} 归一为 {meta_protocol!r} "
                          f"与 device_type={device_type!r} 推出的 {protocol!r} 冲突")
    return (protocol, streaming), None


def _backfill(cur, apply, columns_exist=True):
    """校验全表 + 回填 NULL 行。返回 (scanned, pending, changed, issues)。

    `columns_exist=False`（dry-run 于未迁移库）：两列尚不存在，无法用
    `IS NULL` 过滤待回填行——此时全表都是待回填行，校验/预览仍覆盖全表，
    这样 dry-run 也能给出「扫描 N 行 / 冲突 M 行」的迁移前结论。
    """
    cur.execute(f"SELECT count(*) FROM {TABLE}")
    scanned = cur.fetchone()[0]
    where = (f"WHERE {PROTOCOL_COL} IS NULL OR {STREAMING_COL} IS NULL"
             if columns_exist else "")
    cur.execute(
        f"SELECT id, device_type, meta::text FROM {TABLE} {where} ORDER BY id")
    rows = cur.fetchall()
    pending = []
    issues = []
    for api_id, device_type, meta_raw in rows:
        resolved, reason = _resolve_row(api_id, device_type, meta_raw)
        if resolved is None:
            issues.append((api_id, reason))
        else:
            pending.append((resolved[0], resolved[1], api_id))
    if issues:
        # 校验失败：不写任何行（调用方回滚并退出）
        return scanned, len(pending), 0, issues
    changed = 0
    if apply and pending:
        cur.executemany(
            f"UPDATE {TABLE} SET {PROTOCOL_COL} = %s, {STREAMING_COL} = %s "
            f"WHERE id = %s", pending)
        changed = len(pending)
    return scanned, len(pending), changed, issues


def _tighten(cur, dry_run):
    """③ 收紧约束 + 补默认（列已 NOT NULL 即 SKIP）。返回是否发生变更。"""
    for column, ddl_type, default_sql in (
            (PROTOCOL_COL, 'VARCHAR(20)', "'http'"),
            (STREAMING_COL, 'BOOLEAN', 'false')):
        exists, is_nullable = _column_state(cur, column)
        if not exists:
            print(f"[{'DRY' if dry_run else 'SKIP'}] 列 {TABLE}.{column} 不存在"
                  f"（步骤①建列后由步骤③ SET DEFAULT / SET NOT NULL）")
            continue
        if is_nullable == 'NO':
            print(f'[SKIP] 列 {TABLE}.{column} 已是 NOT NULL')
            continue
        stmts = [
            f"ALTER TABLE {TABLE} ALTER COLUMN {column} SET DEFAULT {default_sql}",
            f"ALTER TABLE {TABLE} ALTER COLUMN {column} SET NOT NULL",
        ]
        for stmt in stmts:
            print(f"[{'DRY' if dry_run else 'APPLY'}] {stmt}")
            if not dry_run:
                cur.execute(stmt)


def migrate(dry_run=True):
    conn = _connect()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        # 锁预算与 db_bootstrap 一致：不长时间阻塞线上读写
        cur.execute(f"SET lock_timeout = '{LOCK_TIMEOUT_MS}ms'")
        cur.execute(f"SET statement_timeout = '{STATEMENT_TIMEOUT_MS}ms'")

        # ① 加列（可空）
        for column, ddl_type in ((PROTOCOL_COL, 'VARCHAR(20)'),
                                 (STREAMING_COL, 'BOOLEAN')):
            exists, _ = _column_state(cur, column)
            if exists:
                print(f'[SKIP] 列 {TABLE}.{column} 已存在')
                continue
            stmt = f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS {column} {ddl_type}"
            print(f"[{'DRY' if dry_run else 'APPLY'}] {stmt}")
            if not dry_run:
                cur.execute(stmt)

        # ② 校验 + 回填
        protocol_exists, _ = _column_state(cur, PROTOCOL_COL)
        streaming_exists, _ = _column_state(cur, STREAMING_COL)
        columns_exist = protocol_exists and streaming_exists
        if dry_run and not columns_exist:
            # dry-run 且列还没建：两列没法 SELECT，但校验/预览仍覆盖全表
            # （迁移前结论：多少行、是否 0 冲突），--apply 时一次完成三步
            print('[DRY] 两列尚未创建（本次 dry-run 只预览校验结论）')
        scanned, pending, changed, issues = _backfill(
            cur, apply=not dry_run, columns_exist=columns_exist)
        if issues:
            conn.rollback()
            print(f'[ABORT] 校验失败：{len(issues)} 行非法/冲突，未写入任何行')
            for api_id, reason in issues[:50]:
                print(f'  - id={api_id}: {reason}')
            if len(issues) > 50:
                print(f'  ... 其余 {len(issues) - 50} 行省略')
            sys.exit(1)
        print(f"[{'DRY' if dry_run else 'APPLY'}] 回填：扫描 {scanned} 行，"
              f"待改 {pending} 行，已改 {changed} 行")

        if not dry_run:
            conn.commit()
        # ③ 收紧约束（回填后无 NULL 才能 SET NOT NULL）
        _tighten(cur, dry_run)
        if not dry_run:
            conn.commit()

        # ④ 删除 meta.protocol 键
        has_key = _has_meta_protocol_key(cur)
        stmt = (f"UPDATE {TABLE} SET meta = (meta::jsonb - 'protocol')::json "
                f"WHERE meta IS NOT NULL AND meta::jsonb ? 'protocol'")
        if has_key:
            print(f"[{'DRY' if dry_run else 'APPLY'}] {stmt}  -- 命中 {has_key} 行")
            if not dry_run:
                cur.execute(stmt)
                conn.commit()
        else:
            print('[SKIP] apis.meta 中已无 protocol 键')
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='执行（默认 dry-run 预览）')
    args = ap.parse_args()
    migrate(dry_run=not args.apply)


if __name__ == '__main__':
    main()
