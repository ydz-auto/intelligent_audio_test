# -*- coding: utf-8 -*-
"""INT-303 存量已发布任务 taskSnapshot 补冻结（任务详情真冻结）

背景：发布链路快照语义修正（INT-303）——published_tasks.snapshot_config
此前只存 caseIds 引用列表，源用例被编辑/删除后已发布版本的"任务详情"
随之失真/失效。与 INT-258（report_snapshot 冻结真实报告）同一裁定：
任务详情也要真冻结——发布/新版本时内联冻结任务详情全量数据
（snapshot_config.taskSnapshot，schemaVersion=2）。

存量版本按 issue 要求补齐：
  - 快照无 taskSnapshot 且源任务仍在（未删、task_case_relations 可读）
    → 按当前源任务数据补冻结（发布时未冻结，冻结值以补冻结时点为准）；
  - 源任务已删除 / 无可读用例 → 保持原样（前端已按 has_task_snapshot=false
    标注"历史版本（发布时未冻结任务详情）"）；
  - 快照已有 taskSnapshot（新链路产物）→ SKIP，重复执行零改动。

冻结逻辑复用 task_service 仓储 freeze_task_snapshot（与新发布链路单一
事实源，保证补冻结结果与新发布完全一致）。幂等：taskSnapshot 已存在的
行一律 SKIP。默认 dry-run 预览，--apply 才落库。

用法：
    python scripts/migrations/202610/backfill_task_snapshot_freeze.py           # 预览
    python scripts/migrations/202610/backfill_task_snapshot_freeze.py --apply --snapshot-out snap.json

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

# BaseConfig 在 import 时校验环境变量，先补齐（与 backfill_report_snapshot_freeze.py 一致）
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
from task_service.infrastructure.persistence.models import Task  # noqa: E402
from shared.models.database import init_db, get_db_session  # noqa: E402

# freeze_task_snapshot 依赖共享 session 工厂，先绑定引擎
init_db()


def _load_snapshot(raw):
    """snapshot_config JSON 列 → dict（None/非法串兜底为 {}）。"""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            loaded = json.loads(raw)
            return loaded if isinstance(loaded, dict) else {}
        except Exception:
            return {}
    return {}


def main():
    parser = argparse.ArgumentParser(description='INT-303 存量 taskSnapshot 补冻结')
    parser.add_argument('--apply', action='store_true', help='真正执行 UPDATE（默认 dry-run）')
    parser.add_argument('--snapshot-out', default=None, help='待改行原值导出 JSON 留档路径')
    args = parser.parse_args()

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SET lock_timeout = '10s'")

    cur.execute(
        "SELECT id, name, version, status, source_task_id, snapshot_config "
        "FROM published_tasks ORDER BY id"
    )
    rows = cur.fetchall()
    conn.rollback()  # 只读查询，释放事务快照

    updates = []       # (pt_id, source_task_id, prior_snapshot, frozen)
    skipped_frozen = skipped_no_source = 0
    for pt_id, name, version, status, source_task_id, raw_snapshot in rows:
        snapshot = _load_snapshot(raw_snapshot)
        if snapshot.get('taskSnapshot'):
            skipped_frozen += 1
            continue
        if not source_task_id:
            skipped_no_source += 1
            print(f'  [NO-SOURCE] published_tasks#{pt_id} v{version} {name!r}（{status}）无 source_task_id，保持原样')
            continue
        # 源任务必须未删除且可读（软删的历史版本不补，标注历史版本即可）
        session = get_db_session()
        try:
            task = session.get(Task, source_task_id)
            task_alive = task is not None and not task.deleted
        finally:
            session.close()
        if not task_alive:
            skipped_no_source += 1
            print(f'  [SOURCE-GONE] published_tasks#{pt_id} v{version} {name!r}（{status}）'
                  f'源任务 #{source_task_id} 已删除/不存在，保持原样（历史版本标注）')
            continue
        # 复用发布链路同一冻结逻辑（无用例等冻结失败场景返回空 cases，仍补任务级冻结体）
        frozen = published_task_repository.freeze_task_snapshot(task)
        if not frozen or not frozen.get('cases'):
            skipped_no_source += 1
            print(f'  [NO-CASES] published_tasks#{pt_id} v{version} {name!r}（{status}）'
                  f'源任务 #{source_task_id} 无可读用例关联，保持原样（历史版本标注）')
            continue
        updates.append((pt_id, source_task_id, snapshot, frozen))
        print(f'  [FREEZE] published_tasks#{pt_id} v{version} {name!r}（{status}）'
              f'← 源任务 #{source_task_id}（cases={len(frozen["cases"])}，taskSnapshot schemaVersion=2）')

    print(f'\n共 {len(rows)} 行：待补冻结 {len(updates)}，已有 taskSnapshot 跳过 {skipped_frozen}，'
          f'无源任务/无用例 {skipped_no_source}')

    if not updates:
        print('无需更新。')
        return

    if not args.apply:
        print('\n[dry-run] 未落库；确认后加 --apply 执行。')
        return

    # 先快照后改（对齐 backfill_report_snapshot_freeze 惯例）：待改行原值导出留档后才执行
    if args.snapshot_out:
        payload = {
            'script': 'backfill_task_snapshot_freeze.py',
            'issue': 'INT-303',
            'exported_at': datetime.now().isoformat(),
            'rows': [
                {'id': pt_id, 'source_task_id': source_task_id,
                 'prior_snapshot_config': prior}
                for pt_id, source_task_id, prior, _frozen in updates
            ],
        }
        with open(args.snapshot_out, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        print(f'已导出待改行原值 → {args.snapshot_out}')

    try:
        for pt_id, _source_task_id, prior, frozen in updates:
            prior['taskSnapshot'] = frozen
            cur.execute(
                "UPDATE published_tasks SET snapshot_config = %s, updated_at = now() "
                "WHERE id = %s",
                (Json(prior), pt_id),
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
