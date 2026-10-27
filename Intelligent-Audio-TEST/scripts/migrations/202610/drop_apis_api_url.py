# -*- coding: utf-8 -*-
"""迁移脚本：移除被测 API Master 入口 URL（apis.api_url）—— 先回填 api_endpoints，后删列

背景（INT-1361，父卡 INT-1223 足迹 + 方案一致性审计员 INT-1359 可行性评审）：
- 负责人 2026-10-22 裁定「直接移除 api url 不再开放填写，前后端都移除」，
  `api_endpoints` 为唯一端点配置入口。
- `apis.api_url`（Master 入口 URL）前后端全量移除；存量仅填 api_url 的记录
  迁移前回填为首个 endpoint（保历史可执行）。
- 回填结构对齐 api_test_service `_build_endpoints_list` 产物：
  endpoint/name/max_process/max_timeout/max_audio_duration/status/health_score/
  priority/description，缺省值取 default_max_process/default_max_timeout/
  default_max_audio_duration。

破坏性门禁（INT-2078 评审补齐，对齐 INT-1813/INT-1995 的 --confirm-read-path 口径）：
- 若在旧代码（仍读 `apis.api_url`）部署前删列 → 窗口内旧代码 UndefinedColumn 500。
  `--apply` 因此必须带 `--confirm-read-path`（操作人确认前后端已移除 api_url 读写），
  缺省即拒绝（exit 4，不动库）；`--gate` 只读报告列现状与回填预览，不写。

用法:
    python scripts/migrations/202610/drop_apis_api_url.py                    # 预览（只读）
    python scripts/migrations/202610/drop_apis_api_url.py --gate             # 门禁报告 + 回填预览（只读）
    python scripts/migrations/202610/drop_apis_api_url.py --apply            # 缺 --confirm-read-path → 拒绝（exit 4）
    python scripts/migrations/202610/drop_apis_api_url.py --apply --confirm-read-path  # 执行

幂等性:
    重复执行安全：回填仅处理 api_endpoints 为空的存量行；列已不存在即 [SKIP]。

环境：``DATABASE_URL`` 优先、``DATABASE_URI`` 兜底；两者都缺即报错退出（INT-2078
评审补齐，不静默连本地默认库）。

退出码：0 完成 / 只读预览；3 执行后复查失败；4 缺前置确认。
"""
import argparse
import os
import sys

import psycopg2
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()


def resolve_database_url():
    """连接串解析：DATABASE_URL 优先、DATABASE_URI 兜底；两者都缺即报错退出。

    与 ``fix_users_email_unique.py``（INT-2078）同口径：迁移脚本不允许静默连
    本地默认库——对错库执行 DDL 会造成跨库破坏。
    """
    url = os.environ.get('DATABASE_URL') or os.environ.get('DATABASE_URI')
    if not url:
        print('错误：未设置 DATABASE_URL / DATABASE_URI，拒绝连默认库——'
              '对错库执行 DDL 会造成跨库破坏。', file=sys.stderr)
        sys.exit(1)
    return url


def _connect():
    parsed = urlparse(resolve_database_url())
    return psycopg2.connect(
        host=parsed.hostname, port=parsed.port or 5432,
        dbname=parsed.path.lstrip('/'), user=parsed.username,
        password=parsed.password,
    )


BACKFILL_PREDICATE = """
    api_url IS NOT NULL
      AND api_url <> ''
      AND (api_endpoints IS NULL OR json_array_length(api_endpoints) = 0)
"""

BACKFILL_SQL = """
    UPDATE apis
    SET api_endpoints = json_build_array(
            json_build_object(
                'endpoint', api_url,
                'name', '',
                'max_process', COALESCE(default_max_process, 5),
                'max_timeout', COALESCE(default_max_timeout, 30),
                'max_audio_duration', COALESCE(default_max_audio_duration, 60),
                'status', 'online',
                'health_score', 100,
                'priority', 0,
                'description', ''
            )
        ),
        updated_at = NOW()
    WHERE %s
""" % BACKFILL_PREDICATE


def column_exists(cur, table, column):
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table, column))
    return cur.fetchone() is not None


def pending_backfill_count(cur):
    """待回填行数（api_url 非空且 api_endpoints 为空的存量行）。"""
    cur.execute(f"SELECT count(*) FROM apis WHERE {BACKFILL_PREDICATE}")
    return cur.fetchone()[0]


def run_gates(cur, has_url):
    """只读门禁报告：api_url 列现状 + 待回填行数预览（不写）。"""
    if has_url:
        pending = pending_backfill_count(cur)
        print(f"[GATE] apis.api_url: 列存在 → 待回填 {pending} 行"
              f"（api_url → api_endpoints 首项）")
        print("[GATE] 未确认读路径已移除 api_url（--confirm-read-path）："
              "旧代码仍读该列时删列会 UndefinedColumn 500")
        return pending
    print("[GATE] apis.api_url: 已不存在 → N/A（列已删，幂等完成）")
    return None


def migrate(args):
    conn = _connect()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        has_url = column_exists(cur, 'apis', 'api_url')

        # 只读（--gate / dry-run / 默认预览）：打印门禁与回填/删列预览，不写。
        if args.gate or not args.apply:
            pending = run_gates(cur, has_url)
            if has_url:
                if not args.confirm_read_path:
                    print('[GATE] 未确认前后端已移除 api_url 读写（--confirm-read-path）')
                print(f'[DRY] 将回填 {pending} 行 apis.api_url → api_endpoints 首项')
                print('[DRY] ALTER TABLE apis DROP COLUMN api_url')
            else:
                print('[SKIP] apis.api_url 已不存在，无回填/删列需求')
            return 0

        # --apply：删列前必须确认读路径已移除（DB 查不出来，由操作人显式确认）
        if has_url and not args.confirm_read_path:
            print('[FAIL] 缺 --confirm-read-path：删除 apis.api_url 前必须确认'
                  '前后端已移除 api_url 读写（INT-1361 裁定前后端全量移除；'
                  '旧代码仍读该列会 UndefinedColumn 500）。确认后加 --confirm-read-path 重跑')
            return 4

        # ① 回填 api_url → api_endpoints 首项（必须在删列之前执行）
        if has_url:
            cur.execute(BACKFILL_SQL)
            print(f"[EXEC] 回填完成，涉及 {cur.rowcount} 行")
        else:
            print("[SKIP] apis.api_url 已删除，无回填需求")

        # ② 删除废弃列
        if has_url:
            cur.execute("ALTER TABLE apis DROP COLUMN api_url")
            print("[EXEC] apis.api_url 已删除")
        else:
            print("[SKIP] apis.api_url 已不存在")

        # 复查
        if column_exists(cur, 'apis', 'api_url'):
            print("[FAIL] 复查：apis.api_url 仍存在 → 校验失败")
            return 3
        print("[VERIFY] apis.api_url 已不存在 → OK")
        return 0
    finally:
        cur.close()
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description='移除被测 API Master 入口 URL（apis.api_url）—— 先回填 '
                    'api_endpoints，后删列（INT-1361；INT-2078 补 --confirm-read-path 门禁）')
    ap.add_argument('--apply', action='store_true',
                    help='执行（默认 dry-run：只打印门禁与回填/删列预览）')
    ap.add_argument('--gate', action='store_true',
                    help='只跑门禁报告与回填预览（只读）')
    ap.add_argument('--confirm-read-path', action='store_true',
                    help='确认前后端已移除 api_url 读写（删除列前必须给；'
                         '--apply 缺省即拒绝）')
    ap.add_argument('--dry-run', action='store_true',
                    help='（旧用法兼容）显式预览；等价于不带 --apply / --gate')
    return ap


def main():
    args = build_parser().parse_args()

    if args.gate or args.dry_run:
        args.apply = False

    try:
        code = migrate(args)
    except SystemExit as exc:  # 连接串缺失等已打印原因
        code = exc.code if isinstance(exc.code, int) else 1
    sys.exit(code)


if __name__ == '__main__':
    main()
