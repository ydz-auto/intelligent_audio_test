# -*- coding: utf-8 -*-
"""运维脚本：report_case_snapshots 孤儿快照低频 sweep（INT-1995 / 档4 M1）

背景（设计文档 `doc/功能设计文档/01_测试执行/10_报告用例快照外置.md` §7）：
``report_case_snapshots`` 是内容寻址共享表，引用集合以 ``report_cases`` 为准。
软删 / 搬运 / 替换 / 导入四条链路都不在按报告删快照时打断别的报告——快照只增不
删，孤儿由本脚本在 **``hard_delete_expired`` 之后**低频回收（建议月度 / 手动）。

SQL 口径（卡面第 4 条）：

    DELETE FROM report_case_snapshots
     WHERE sha256 NOT IN (
       SELECT snapshot_sha256 FROM report_cases WHERE snapshot_sha256 IS NOT NULL
     );

**子查询必须显式滤 NULL**——PG 的 ``NOT IN`` 遇 NULL 返回空集，一条都删不掉。
本脚本把该句固化成常量 ``SWEEP_SQL``，防复制漂移。

**不建 refcount 列**：软删 / 搬运 / 替换 / 导入四条链路都会让计数漂移，权威引用
集合永远可从 ``report_cases`` 重算；anti-join 是亚秒级（10,843 个快照行）。

用法::

    # 只打印孤儿统计（只读，可重复执行）
    python scripts/migrations/202610/sweep_report_case_snapshots_int1995.py
    # 预览将删除的行（带 sha 前缀 / 计数，不动库）
    python scripts/migrations/202610/sweep_report_case_snapshots_int1995.py --dry-run
    # 执行删除（单条 SQL，autocommit）
    python scripts/migrations/202610/sweep_report_case_snapshots_int1995.py --apply

环境：``DATABASE_URL``（或 ``DATABASE_URI``）。
退出码：0 完成；1 连接 / 统计失败。

幂等性：孤儿删完后再跑命中 0 行；``DELETE`` 只删无引用的行，任何引用它的用例行
都会把它留在表里。**不得在 ``hard_delete_expired`` 之前跑**——被软删报告引用的
快照在硬删后才会变成孤儿。
"""
import argparse
import os
import sys

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

#: 孤儿判定唯一来源。子查询显式 ``IS NOT NULL`` 滤掉 NULL 指针——PG 的 ``NOT IN``
#: 遇 NULL 返回空集，漏了这条一条都删不掉。
SWEEP_SQL = (
    f'DELETE FROM {SNAPSHOT_TABLE} '
    f'WHERE sha256 NOT IN ('
    f'  SELECT snapshot_sha256 FROM {CASES_TABLE} WHERE snapshot_sha256 IS NOT NULL)'
)

COUNT_SQL = (
    f'SELECT count(*) FROM {SNAPSHOT_TABLE} s '
    f'WHERE s.sha256 NOT IN ('
    f'  SELECT snapshot_sha256 FROM {CASES_TABLE} WHERE snapshot_sha256 IS NOT NULL)'
)

PREVIEW_SQL = (
    f'SELECT left(s.sha256, 12) AS sha_prefix, s.payload_bytes, s.created_at '
    f'FROM {SNAPSHOT_TABLE} s '
    f'WHERE s.sha256 NOT IN ('
    f'  SELECT snapshot_sha256 FROM {CASES_TABLE} WHERE snapshot_sha256 IS NOT NULL) '
    f'ORDER BY s.created_at'
)


def _connect():
    from urllib.parse import urlparse
    parsed = urlparse(os.environ['DATABASE_URL'])
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password, application_name='sweep_int1995')


def sweep(args) -> int:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(COUNT_SQL)
        orphan_count = int(cur.fetchone()[0])
        cur.execute(
            'SELECT count(*) FROM ' + SNAPSHOT_TABLE)
        total = int(cur.fetchone()[0])
        print(f'[STAT] 快照总数 {total}，孤儿 {orphan_count}'
              f'（被引用 {total - orphan_count}）')

        if orphan_count == 0:
            print('[SKIP] 无孤儿，无需 sweep')
            return 0

        if getattr(args, 'dry_run', False) or not args.apply:
            cur.execute(PREVIEW_SQL)
            rows = cur.fetchall()
            print(f'[PREVIEW] 将删除 {len(rows)} 条（样例前 10）：')
            for sha_prefix, payload_bytes, created_at in rows[:10]:
                print(f'  {sha_prefix}  payload_bytes={payload_bytes}  created_at={created_at}')
            print('[DRY] 未执行；--apply 时执行上面那句 DELETE')
            return 0

        cur.execute(SWEEP_SQL)
        deleted = cur.rowcount
        conn.commit()
        print(f'[APPLY] 删除 {deleted} 条孤儿快照')
        cur.execute(COUNT_SQL)
        remain = int(cur.fetchone()[0])
        print(f'[VERIFY] 剩余孤儿 {remain}（0 = sweep 完成）')
        return 0 if remain == 0 else 3
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    """命令行开关（``main`` 与单测共用一处，防开关名漂移）。"""
    ap = argparse.ArgumentParser(
        description='report_case_snapshots 孤儿快照低频 sweep（INT-1995；'
                    '必须在 hard_delete_expired 之后跑）')
    ap.add_argument('--apply', action='store_true', help='执行删除（默认只打印孤儿统计）')
    ap.add_argument('--dry-run', action='store_true',
                    help='预览将删除的行（不执行 DELETE）')
    return ap


def main():
    args = build_parser().parse_args()
    try:
        code = sweep(args)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    sys.exit(code)


if __name__ == '__main__':
    main()
