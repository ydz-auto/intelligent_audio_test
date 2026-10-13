# -*- coding: utf-8 -*-
"""INT-258 存量已发布任务 report_snapshot 补冻结（引用 + 冻结双轨）

背景：发布链路快照语义修正——report_snapshot 应冻结"报告管理（历史页面）
生成的真实报告"（报告 7 表渲染数据 + sourceReportId 引用），而非旧的执行
数据摘要（schemaVersion 缺失的 v1 结构）。存量版本按 issue 要求补齐：
  - report_snapshot 为空 且 源任务有真实报告 → 重新冻结补齐；
  - 存量 v1 快照（无 schemaVersion）且源任务报告仍在 → 升级冻结（v2）；
  - 无源任务 / 无（未删）报告 → 保持空（前端渲染"无报告"空态）；
  - v1 快照但源报告已不存在 → 保留 v1 原数据不动（历史冻结仍有价值）。

冻结逻辑直接复用 task_service 仓储 freeze_report_snapshot（与发布链路
单一事实源，保证补冻结结果与新发布完全一致）。幂等：schemaVersion=2 的
行一律 SKIP，重复执行零改动。

用法（默认 dry-run 预览，--apply 才落库）:
    python scripts/migrations/202610/backfill_report_snapshot_freeze.py           # 预览
    python scripts/migrations/202610/backfill_report_snapshot_freeze.py --apply --snapshot-out snap.json

连接串：DATABASE_URL / DATABASE_URI 环境变量（默认本地共享业务库）。
"""
import argparse
import json
import os
import sys
from datetime import datetime

import psycopg2
from psycopg2.extras import Json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

# BaseConfig 在 import 时校验环境变量，先补齐（与 tests/unit 惯例一致）
if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ.get(
        'DATABASE_URI',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test')
os.environ.setdefault('OSS_ACCESS_KEY', 'migration')
os.environ.setdefault('OSS_SECRET_KEY', 'migration')

from task_service.infrastructure.persistence.published_task_repository import (  # noqa: E402
    published_task_repository,
)
from shared.models.database import init_db  # noqa: E402

# freeze_report_snapshot 依赖共享 session 工厂，先绑定引擎
init_db()

FROZEN_SCHEMA_VERSION = 2


def _snapshot_state(snapshot):
    """行现状分类：empty（无快照）/ legacy（v1 旧结构）/ v2（已升级）。"""
    if not snapshot:
        return 'empty'
    if isinstance(snapshot, str):
        try:
            snapshot = json.loads(snapshot)
        except Exception:
            return 'legacy'
    if not isinstance(snapshot, dict) or not snapshot:
        return 'empty'
    return 'v2' if snapshot.get('schemaVersion') == FROZEN_SCHEMA_VERSION else 'legacy'


def main():
    parser = argparse.ArgumentParser(description='INT-258 存量 report_snapshot 补冻结')
    parser.add_argument('--apply', action='store_true', help='真正执行 UPDATE（默认 dry-run）')
    parser.add_argument('--snapshot-out', default=None, help='待改行原值导出 JSON 留档路径')
    args = parser.parse_args()

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SET lock_timeout = '10s'")

    cur.execute(
        "SELECT id, name, version, status, source_task_id, report_snapshot "
        "FROM published_tasks ORDER BY id"
    )
    rows = cur.fetchall()
    conn.rollback()  # 只读查询，释放事务快照

    updates = []   # (pt_id, source_task_id, prior_snapshot, frozen)
    skipped_v2 = skipped_no_report = 0
    for pt_id, name, version, status, source_task_id, snapshot in rows:
        state = _snapshot_state(snapshot)
        if state == 'v2':
            skipped_v2 += 1
            continue
        if not source_task_id:
            # 无源任务：无从冻结，空态（保持现状）
            skipped_no_report += 1
            print(f'  [NO-SOURCE] published_tasks#{pt_id} v{version} {name!r}（{status}）无 source_task_id，保持空态')
            continue
        # 复用发布链路同一冻结逻辑（无未删报告时返回 None）
        frozen = published_task_repository.freeze_report_snapshot(source_task_id)
        if frozen is None:
            skipped_no_report += 1
            action = '保留 v1 原数据' if state == 'legacy' else '保持空态'
            print(f'  [NO-REPORT] published_tasks#{pt_id} v{version} {name!r}（{status}）源任务 #{source_task_id} 无未删报告，{action}')
            continue
        updates.append((pt_id, source_task_id, snapshot, frozen))
        print(f'  [FREEZE] published_tasks#{pt_id} v{version} {name!r}（{status}）'
              f'← 源任务 #{source_task_id} 报告 #{frozen["sourceReportId"]}'
              f'（cases={len(frozen["cases"])}，schemaVersion=2）')

    print(f'\n共 {len(rows)} 行：待补冻结 {len(updates)}，已 v2 跳过 {skipped_v2}，无报告/无源任务 {skipped_no_report}')

    if not updates:
        print('无需更新。')
        return

    if not args.apply:
        print('\n[dry-run] 未落库；确认后加 --apply 执行。')
        return

    # 先快照后改（对齐 cleanup 惯例）：待改行原值导出留档后才执行
    if args.snapshot_out:
        payload = {
            'script': 'backfill_report_snapshot_freeze.py',
            'issue': 'INT-258',
            'exported_at': datetime.now().isoformat(),
            'rows': [
                {'id': pt_id, 'source_task_id': source_task_id,
                 'prior_report_snapshot': prior if not isinstance(prior, str) else None,
                 'prior_report_snapshot_raw': prior if isinstance(prior, str) else None}
                for pt_id, source_task_id, prior, _frozen in updates
            ],
        }
        with open(args.snapshot_out, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        print(f'已导出待改行原值 → {args.snapshot_out}')

    try:
        for pt_id, _source_task_id, _prior, frozen in updates:
            cur.execute(
                "UPDATE published_tasks SET report_snapshot = %s, updated_at = now() "
                "WHERE id = %s",
                (Json(frozen), pt_id),
            )
        conn.commit()
        print(f'\n[APPLY] 已补冻结 {len(updates)} 行。')
    except Exception:
        conn.rollback()
        print('\n[ABORT] 更新失败已回滚', file=sys.stderr)
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
