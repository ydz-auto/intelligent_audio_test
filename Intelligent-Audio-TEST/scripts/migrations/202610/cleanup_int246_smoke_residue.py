# -*- coding: utf-8 -*-
"""INT-246 共享业务库冒烟/验收残留清理（软删 = 回收站语义，不物理删）

背景：INT-246 整改发现共享业务库 intelligent_audio_test 混入流水线冒烟与
逐轮验收产生的任务/用例/结果/发布残留（test_tasks 24 行中 14 行为 agent
残留、test_cases 于 10-12/13 期间产生 17 行 agent 用例、test_results 2 行、
published_tasks 4 行 INT-95 系列发布）。本脚本按 issue 要求先评论清单、
负责人确认后执行软删。

原则（对齐 cleanup_int185_test_residue.py 惯例）：
  - 先快照后删除：--snapshot-out 导出全部待改行为 JSON 留档后才执行；
  - 内容圈选：任务/用例按 (id, name) 二元组精确匹配（id 与 name 任一不符
    即中止），绝不按 ID 盲删、绝不碰 audios / devices / 负责人业务用例；
  - 拿不准不删：名称无法判定归属的行（合并任务_*、豆包拒识发布）不在本
    脚本选集内，待负责人逐条定夺后再追加；
  - 回收站语义：test_tasks / test_cases / test_results 仅置
    deleted=TRUE + deleted_at（恢复走既有回收站 /trash 接口，60 天保留期
    由 SoftDeleteCleaner 兜底）；published_tasks 走归档语义
    status='archived' + archived_at；
  - 幂等安全：UPDATE 全部带 deleted = FALSE / status='published' 前置条件，
    重复执行不会二次改动。

用法：
    python cleanup_int246_smoke_residue.py --dry-run            # 预览选集
    python cleanup_int246_smoke_residue.py --dry-run --snapshot-out snap.json
    python cleanup_int246_smoke_residue.py --execute --snapshot-out snap.json

连接串经 DATABASE_URI / DATABASE_URL 环境变量覆盖（对齐 seed_rbac 惯例），
但目标库名必须是共享业务库 intelligent_audio_test，否则拒绝执行。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from shared.constants.database import (  # noqa: E402
    ISOLATED_TEST_DB_NAME, SHARED_BUSINESS_DB_NAME, database_name_of,
)

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    os.environ.get(
        'DATABASE_URL',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test'))

LOCK_TIMEOUT = '10s'

# ---------------------------------------------------------------------------
# 待软删任务（(id, name) 精确圈选，全部为 agent 验收/冒烟产生的行）
# ---------------------------------------------------------------------------
DELETE_TASKS = [
    (514, 'int79-status'),                      # INT-79 验收状态标记任务
    (515, 't-running'),                         # INT-79 验收夹具任务
    (516, 't-completed'),                       # INT-79 验收夹具任务
    (529, 'INT-174重评验证任务'),                # INT-174 重评链路验证
    (533, 'INT158R2_采集端修复验收_物理执行'),    # INT-158 R2 物理链验收
    (534, 'INT95R9_API_多轮session执行'),        # INT-95 R9 验收（关联发布 P4）
    (535, 'INT95R9_E2E_物理链执行'),             # INT-95 R9 验收重试 ×6
    (536, 'INT95R9_E2E_物理链执行'),
    (537, 'INT95R9_E2E_物理链执行'),
    (538, 'INT95R9_E2E_物理链执行'),
    (539, 'INT95R9_E2E_物理链执行'),
    (553, 'INT161RE_API失败聚合复现'),           # INT-161 打回复现
    (557, 'INT95R9_E2E_物理链执行'),
    (558, 'INT224-smoke-1013012956'),           # INT-224 冒烟
]

# 待软删用例：10-12/13 期间 agent 产生的用例（未删部分；已删 9 行不再动）
DELETE_CASES = [
    ('c1_7c34f640', '登录功能用例_7c34f640'),    # auth 验收夹具（运行标记后缀）
    ('c2_7c34f640', '播放用例_7c34f640'),
    ('c3_7c34f640', '维度用例_7c34f640'),
    ('c174_reeval', 'INT-174重评验证用例'),      # 任务 529 的执行用例
    ('8d756206-1a8f-456c-a61b-d4e6017f9faf', 'INT95R9_E2E_话轮接管_2轮'),
    ('177f173b-8107-414c-93b9-9cb033dd7cfa', 'INT95R9_API_话轮接管_2轮session'),
]

# 待软删执行结果：按任务 ID 圈选（仅上述任务的结果行）
DELETE_RESULTS_TASK_IDS = (529, 534)

# 待归档发布（(id, name) 精确圈选）：INT-95 系列验收发布
ARCHIVE_PUBLISHED = [
    (2, 'INT95R7-主链API验收'),
    (3, 'INT95R8_API_多轮session'),
    (4, 'INT95R9_API_多轮session执行'),
]


def _die(msg):
    print(f'[ABORT] {msg}')
    sys.exit(1)


def _rows(cur, sql, params=None):
    cur.execute(sql, params or ())
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _utcnow():
    return datetime.now(timezone.utc)


def verify_selection(cur):
    """(id, name) 全量精确核对：任一行缺失/更名/已删即中止。"""
    problems = []
    for tid, name in DELETE_TASKS:
        got = _rows(cur, 'SELECT name, deleted FROM test_tasks WHERE id = %s', (tid,))
        if not got:
            problems.append(f'test_tasks id={tid} 不存在（预期 {name!r}）')
        elif got[0]['name'] != name:
            problems.append(f'test_tasks id={tid} 名称漂移：现 {got[0]["name"]!r} 预期 {name!r}')
        elif got[0]['deleted']:
            problems.append(f'test_tasks id={tid} 已是软删态（预期未删）')
    for cid, name in DELETE_CASES:
        got = _rows(cur, 'SELECT name, deleted FROM test_cases WHERE id = %s', (cid,))
        if not got:
            problems.append(f'test_cases id={cid} 不存在（预期 {name!r}）')
        elif got[0]['name'] != name:
            problems.append(f'test_cases id={cid} 名称漂移：现 {got[0]["name"]!r} 预期 {name!r}')
        elif got[0]['deleted']:
            problems.append(f'test_cases id={cid} 已是软删态（预期未删）')
    for pid, name in ARCHIVE_PUBLISHED:
        got = _rows(cur, 'SELECT name, status FROM published_tasks WHERE id = %s', (pid,))
        if not got:
            problems.append(f'published_tasks id={pid} 不存在（预期 {name!r}）')
        elif got[0]['name'] != name:
            problems.append(f'published_tasks id={pid} 名称漂移：现 {got[0]["name"]!r} 预期 {name!r}')
        elif got[0]['status'] != 'published':
            problems.append(f'published_tasks id={pid} 状态 {got[0]["status"]!r}（预期 published）')
    if problems:
        _die('选集与库态不符（防止误删，逐条处置后再跑）：\n  ' + '\n  '.join(problems))


def collect_snapshot(cur):
    """导出全部将被改动的行的当前完整内容（JSON 留档）。"""
    task_ids = [t[0] for t in DELETE_TASKS]
    case_ids = [c[0] for c in DELETE_CASES]
    pub_ids = [p[0] for p in ARCHIVE_PUBLISHED]
    return {
        'generated_at': _utcnow().isoformat(),
        'test_tasks': _rows(cur, 'SELECT * FROM test_tasks WHERE id = ANY(%s)', (task_ids,)),
        'test_cases': _rows(cur, 'SELECT * FROM test_cases WHERE id = ANY(%s)', (case_ids,)),
        'test_results': _rows(cur, 'SELECT * FROM test_results WHERE task_id = ANY(%s)',
                              (list(DELETE_RESULTS_TASK_IDS),)),
        'published_tasks': _rows(cur, 'SELECT * FROM published_tasks WHERE id = ANY(%s)', (pub_ids,)),
    }


def execute(cur):
    now = _utcnow()
    task_ids = [t[0] for t in DELETE_TASKS]
    case_ids = [c[0] for c in DELETE_CASES]
    pub_ids = [p[0] for p in ARCHIVE_PUBLISHED]

    cur.execute(
        'UPDATE test_tasks SET deleted = TRUE, deleted_at = %s '
        'WHERE id = ANY(%s) AND deleted = FALSE', (now, task_ids))
    n_tasks = cur.rowcount
    cur.execute(
        'UPDATE test_cases SET deleted = TRUE, deleted_at = %s, updated_at = %s '
        'WHERE id = ANY(%s) AND deleted = FALSE', (now, now, case_ids))
    n_cases = cur.rowcount
    cur.execute(
        'UPDATE test_results SET deleted = TRUE '
        'WHERE task_id = ANY(%s) AND deleted = FALSE',
        (list(DELETE_RESULTS_TASK_IDS),))
    n_results = cur.rowcount
    cur.execute(
        "UPDATE published_tasks SET status = 'archived', archived_at = %s "
        'WHERE id = ANY(%s) AND status = %s', (now, pub_ids, 'published'))
    n_pubs = cur.rowcount
    return n_tasks, n_cases, n_results, n_pubs


def main():
    parser = argparse.ArgumentParser(description='INT-246 共享业务库冒烟残留清理')
    parser.add_argument('--dry-run', action='store_true', help='仅核对选集并预览，不改动（默认）')
    parser.add_argument('--execute', action='store_true', help='执行软删（须配合 --snapshot-out）')
    parser.add_argument('--snapshot-out', help='删除前行级快照 JSON 输出路径')
    args = parser.parse_args()

    target = database_name_of(POSTGRES_URI)
    if target != SHARED_BUSINESS_DB_NAME:
        _die(f'连接串库名 {target!r} 不是共享业务库 {SHARED_BUSINESS_DB_NAME!r}；'
             f'本脚本仅用于清理共享库（隔离测试库 {ISOLATED_TEST_DB_NAME!r} 走 '
             'scripts/reset_test_db.py 清库）。')
    if args.execute and args.dry_run:
        _die('--execute 与 --dry-run 互斥。')
    if args.execute and not args.snapshot_out:
        _die('执行删除前必须 --snapshot-out 导出快照留档。')

    conn = psycopg2.connect(POSTGRES_URI, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute(f'SET lock_timeout = %s', (LOCK_TIMEOUT,))
            verify_selection(cur)
            snapshot = collect_snapshot(cur)
            print(f"[SELECT] 任务 {len(snapshot['test_tasks'])} | 用例 "
                  f"{len(snapshot['test_cases'])} | 结果 {len(snapshot['test_results'])} | "
                  f"发布 {len(snapshot['published_tasks'])}")
            if args.snapshot_out:
                with open(args.snapshot_out, 'w', encoding='utf-8') as f:
                    json.dump(snapshot, f, ensure_ascii=False, default=str, indent=2)
                print(f"[SNAPSHOT] 已导出 {args.snapshot_out}")
            if not args.execute:
                print('[DRY-RUN] 未做任何改动。确认清单后加 --execute --snapshot-out <path> 执行。')
                return 0
            counts = execute(cur)
            conn.commit()
            print(f"[DONE] 软删任务 {counts[0]} | 用例 {counts[1]} | 结果 "
                  f"{counts[2]} | 归档发布 {counts[3]}（全部可经回收站/归档恢复）")
            return 0
    except Exception as e:
        conn.rollback()
        _die(f'执行失败已回滚：{e}')
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
