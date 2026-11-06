# -*- coding: utf-8 -*-
"""迁移脚本：test_reports.status 历史混值归一（INT-2238）

背景：
- 报告行状态只有一套词表（`shared.models.common_enums.ReportStatus`）：
  draft / published —— 表达「是否已发布」一个维度。
- 历史上同一列被两套互斥词表混写：
  - 生成链路 / 统计 / 渲染 / 前端：draft / published；
  - DDD 领域实体与 handle_create / handle_generate / UpdateReportStatus：
    pending / generating / completed / failed。
  混写行的后果是统计（只认 published）漏计、报告页恒显示「草稿」、
  Tab 计数对不上。代码侧已统一改走 ReportStatus 枚举，本脚本把库里
  残留的历史值一次性归一。

归一映射（与代码侧语义对齐）：
    completed            → published   （生成成功 = 已发布）
    pending / generating → draft       （未发布）
    failed               → draft       （生成失败不发布，留草稿待重试）
    其它未知取值          → draft       （一律视为未发布，打印原值备查）
draft / published 不动；空值（理论上 NOT NULL）不动。

用法：
    python scripts/migrations/202611/normalize_report_status_int2238.py
        # 预览（显式 BEGIN + UPDATE + 回读 + ROLLBACK，不落库）
    python scripts/migrations/202611/normalize_report_status_int2238.py --apply
        # 真正执行 UPDATE

幂等性：
    只处理 status 不在 (draft, published) 的行；归一后再次执行命中 0 行。
    纯数据 UPDATE，无 DDL。
"""
import argparse
import os
import sys

import psycopg2

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')

# 历史混值 → ReportStatus 标准值
LEGACY_STATUS_MAP = {
    'completed': 'published',
    'pending': 'draft',
    'generating': 'draft',
    'failed': 'draft',
}

STANDARD_STATUSES = ('draft', 'published')

SELECT_CANDIDATES_SQL = """
SELECT id, status
FROM test_reports
WHERE status IS NOT NULL
  AND status NOT IN (%s, %s)
ORDER BY id
"""

UPDATE_SQL = """
UPDATE test_reports
SET status = %(new_status)s
WHERE id = %(id)s
  AND status = %(old_status)s
"""


def normalize_report_status(value):
    """历史状态值 → 标准状态值；无需归一返回 None。"""
    if value is None:
        return None
    if value in STANDARD_STATUSES:
        return None
    return LEGACY_STATUS_MAP.get(str(value).strip().lower(), 'draft')


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='INT-2238 test_reports.status 历史混值归一')
    parser.add_argument('--apply', action='store_true',
                        help='真正执行 UPDATE（默认 dry-run，事务内执行后回滚）')
    args = parser.parse_args(argv)

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(SELECT_CANDIDATES_SQL, STANDARD_STATUSES)
        rows = cur.fetchall()
        print(f'[{"EXEC" if args.apply else "DRY-RUN"}] '
              f'命中待归一 test_reports.status 行：{len(rows)}')

        before = {}
        after = {}
        for _rid, status in rows:
            before[status] = before.get(status, 0) + 1
            target = normalize_report_status(status)
            after[target] = after.get(target, 0) + 1
        if rows:
            print('  归一前分布: ' + ', '.join(f'{k}={v}' for k, v in sorted(before.items())))
            print('  归一后分布: ' + ', '.join(f'{k}={v}' for k, v in sorted(after.items())))
            unknown = sorted(k for k in before if k not in LEGACY_STATUS_MAP)
            if unknown:
                print('  [WARN] 未知历史取值（按 draft 归一）: '
                      + ', '.join(repr(k) for k in unknown))

        if args.apply:
            changed = 0
            for rid, status in rows:
                target = normalize_report_status(status)
                if target is None:
                    continue
                cur.execute(UPDATE_SQL, {'id': rid, 'new_status': target,
                                         'old_status': status})
                changed += cur.rowcount
            print(f'[EXEC] 已更新 {changed} 行')
        else:
            # 预览：显式 BEGIN + UPDATE + 回读 + ROLLBACK（0 行 UPDATE 后
            # psycopg2 隐性事务不自动 BEGIN，会直接落库，故必须显式 BEGIN）
            cur.execute('BEGIN')
            try:
                for rid, status in rows:
                    target = normalize_report_status(status)
                    if target is None:
                        continue
                    cur.execute(UPDATE_SQL, {'id': rid, 'new_status': target,
                                             'old_status': status})
                cur.execute(
                    'SELECT status, count(*) FROM test_reports GROUP BY status ORDER BY status')
                print('[DRY-RUN] 事务内回读（将回滚）：'
                      + ', '.join(f'{s}={c}' for s, c in cur.fetchall()))
            finally:
                cur.execute('ROLLBACK')
            print('[DRY-RUN] 已回滚，未落库（--apply 执行）')
    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
