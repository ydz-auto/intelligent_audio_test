# -*- coding: utf-8 -*-
"""INT-806 历史审计日志操作人回填（可选回填，验收项）

背景：写侧归属落地前，logs.created_by_user_id 全 NULL，「仅自己」视图对
历史行永不可见。本脚本做一次性回填——只覆盖 content 可解析为 JSON 且含
operator_id 的审计行（category ∈ {auth, benchmark}），使上线即有数据。
已核验：auth 审计 content 确含 operator_id（auth_commands 全链路）；
benchmark 审计 content 是 operator 用户名串、不含 operator_id → 本脚本
实际只回填 auth 行（benchmark 行如需归属另需用户名→id 映射，超出本卡）。

幂等：created_by_user_id 非 NULL 的行一律 SKIP；重复执行零改动。
解析失败（content 非 JSON / 无 operator_id / operator_id 非法）放弃不阻塞。
默认 dry-run 预览，--apply 才落库。

用法:
    python scripts/migrations/202610/backfill_log_operator_int806.py
    python scripts/migrations/202610/backfill_log_operator_int806.py --apply

连接串：DATABASE_URL / DATABASE_URI 环境变量（默认本地共享业务库）。
"""
import argparse
import json
import os
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')
os.environ.setdefault('OSS_ACCESS_KEY', 'migration')
os.environ.setdefault('OSS_SECRET_KEY', 'migration')


def _parse_operator_id(content):
    """审计 content → operator_id（int）；解析失败/缺失/非法返回 None。"""
    if not content:
        return None
    try:
        payload = json.loads(content)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    operator_id = payload.get('operator_id')
    try:
        operator_id = int(operator_id)
    except (TypeError, ValueError):
        return None
    if operator_id <= 0:
        return None
    return operator_id


def main():
    parser = argparse.ArgumentParser(description='INT-806 历史审计日志操作人回填')
    parser.add_argument('--apply', action='store_true', help='真正执行 UPDATE（默认 dry-run）')
    args = parser.parse_args()

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SET lock_timeout = '10s'")

    cur.execute(
        "SELECT id, category, content FROM logs "
        "WHERE created_by_user_id IS NULL AND category IN ('auth', 'benchmark') "
        "ORDER BY id"
    )
    rows = cur.fetchall()
    conn.rollback()  # 只读查询，释放事务快照

    updates = []  # (id, category, operator_id)
    skipped = 0
    for log_id, category, content in rows:
        operator_id = _parse_operator_id(content)
        if operator_id is None:
            skipped += 1
            continue
        updates.append((log_id, category, operator_id))
        print(f'  [BACKFILL] logs#{log_id} category={category} → created_by_user_id={operator_id}'
              f'（content 前缀: {(content or "")[:80]!r}）')

    print(f'\n共 {len(rows)} 行：待回填 {len(updates)}，'
          f'解析失败/无 operator_id 跳过 {skipped}')

    if not updates:
        print('无需更新。')
        return

    if not args.apply:
        print('\n[dry-run] 未落库；确认后加 --apply 执行。')
        return

    try:
        for log_id, _category, operator_id in updates:
            cur.execute(
                "UPDATE logs SET created_by_user_id = %s WHERE id = %s",
                (operator_id, log_id),
            )
        conn.commit()
        print(f'\n[APPLY] 已回填 {len(updates)} 行 created_by_user_id。')
    except Exception:
        conn.rollback()
        print('\n[ABORT] 更新失败已回滚', file=sys.stderr)
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
