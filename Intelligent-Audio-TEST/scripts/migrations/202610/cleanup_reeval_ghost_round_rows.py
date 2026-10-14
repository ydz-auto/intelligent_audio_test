# -*- coding: utf-8 -*-
"""历史失败逐轮行（幽灵行）清理（INT-364，移植 V9.7.10 f02ba75e 同名修复脚本）

背景：
- E2E 用例每轮未配置评估维度（rounds[].evaluation.dimensions 为空，维度只配在
  顶层）时，逐轮 TRD 行只是整体评估 per_round 投影的产物。某轮无有效值（如无
  接管/打断事件）时投影不覆盖该轮，历史残留的 evaluation_status='failed' 逐轮行
  永久保留；update_task_case_status 遍历该 result 全部 TRD，只要有一行 failed 即把
  用例判为 failed。failed 重评只重整体口径时这些幽灵行永远清不掉。

修复机制（代码侧）已随 f02ba75e 移植：failed 重评提交前清空待重评维度的历史失败
逐轮行。本脚本处理**已产生幽灵行的历史数据**：

- 删除「逐轮失败（round_number 非空 + failed）+ 同 (result, dimension) 整体行已
  completed」的幽灵行——整体行 completed 说明权威判定是完成，逐轮失败行必为
  无值轮残留；无整体行或整体行非 completed 的失败行不动（真实失败不误删）；
- 将不再有失败维度行的用例 TaskCase（execution_status=completed 且
  evaluation_status=failed）恢复为 completed；
- 同步任务统计（completed_cases / failed_cases 按 status 聚合刷新）。

幂等：清理后同条件查询为空，重复执行为 no-op。

用法（默认 dry-run，--apply 执行删除/更新）：
    python scripts/migrations/202610/cleanup_reeval_ghost_round_rows.py             # dry-run 全库
    python scripts/migrations/202610/cleanup_reeval_ghost_round_rows.py --task-id 407 --apply

连接串经 DATABASE_URI / DATABASE_URL 环境变量覆盖（对齐迁移脚本惯例）。

全库模式实现注记（INT-364 审计 P3 修复）：四条核心 SQL 的任务过滤统一写成
`(%(task_id)s IS NULL OR <列> = %(task_id)s)`——psycopg2 把 Python None 绑定为
SQL NULL，若直接写 `<列> = %(task_id)s`，缺省全库模式下 `task_id = NULL` 恒为
假，脚本会静默命中 0 行、删除与状态恢复全部跳过（幂等形式掩盖真实失效）。
"""
import argparse
import os

import psycopg2

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    os.environ.get(
        'DATABASE_URL',
        'postgresql://intelligent_audio_test:intelligent_audio_test666'
        '@localhost:5432/intelligent_audio_test'))

LOCK_TIMEOUT = '10s'

# 幽灵行判定：逐轮失败行 + 同 (result, dimension) 存在 completed 整体行
# task_id 过滤统一用「IS NULL OR =」形态：None（缺省全库）不过滤，传值按任务限定
GHOST_SELECT_SQL = """
    SELECT trd.id, trd.test_result_id, tr.test_case_id, trd.dimension_id,
           trd.round_number, trd.score
    FROM test_result_dimensions trd
    JOIN test_results tr ON tr.id = trd.test_result_id
    WHERE (%(task_id)s IS NULL OR tr.task_id = %(task_id)s)
      AND trd.round_number IS NOT NULL
      AND trd.evaluation_status = 'failed'
      AND EXISTS (
          SELECT 1 FROM test_result_dimensions o
          WHERE o.test_result_id = trd.test_result_id
            AND o.dimension_id = trd.dimension_id
            AND o.round_number IS NULL
            AND o.evaluation_status = 'completed'
      )
    ORDER BY trd.test_result_id, trd.round_number, trd.dimension_id
"""

GHOST_DELETE_SQL = """
    DELETE FROM test_result_dimensions trd
    WHERE trd.test_result_id IN (
        SELECT id FROM test_results
        WHERE (%(task_id)s IS NULL OR task_id = %(task_id)s)
    )
      AND trd.round_number IS NOT NULL
      AND trd.evaluation_status = 'failed'
      AND EXISTS (
          SELECT 1 FROM test_result_dimensions o
          WHERE o.test_result_id = trd.test_result_id
            AND o.dimension_id = trd.dimension_id
            AND o.round_number IS NULL
            AND o.evaluation_status = 'completed'
      )
"""

# 恢复用例状态：执行已完成 + 评估 failed、且该用例已无任何失败维度行
CASE_RESTORE_SQL = """
    UPDATE task_case_relations tc
    SET evaluation_status = 'completed',
        status = 'completed'
    WHERE (%(task_id)s IS NULL OR tc.task_id = %(task_id)s)
      AND tc.execution_status = 'completed'
      AND tc.evaluation_status = 'failed'
      AND NOT EXISTS (
          SELECT 1 FROM test_results tr
          JOIN test_result_dimensions trd ON trd.test_result_id = tr.id
          WHERE tr.task_id = tc.task_id
            AND tr.test_case_id = tc.test_case_id
            AND trd.evaluation_status = 'failed'
      )
"""

REMAINING_CHECK_SQL = """
    SELECT count(*) FROM test_result_dimensions trd
    JOIN test_results tr ON tr.id = trd.test_result_id
    WHERE (%(task_id)s IS NULL OR tr.task_id = %(task_id)s)
      AND trd.evaluation_status = 'failed'
"""

CASE_COUNTS_SQL = """
    SELECT
        count(*) AS total,
        count(*) FILTER (WHERE status = 'completed' AND execution_status = 'completed') AS completed,
        count(*) FILTER (WHERE status = 'failed') AS failed
    FROM task_case_relations WHERE task_id = %(task_id)s
"""

TASK_STATS_UPDATE_SQL = """
    UPDATE test_tasks
    SET completed_cases = %(completed)s, failed_cases = %(failed)s
    WHERE id = %(task_id)s
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description='failed 重评幽灵逐轮行清理（INT-364）')
    parser.add_argument('--task-id', type=int, default=None,
                        help='限定任务 ID（缺省 = 全库扫描所有任务）')
    parser.add_argument('--apply', action='store_true',
                        help='执行删除/更新（缺省 dry-run，只打印不影响数据）')
    args = parser.parse_args(argv)
    task_id = args.task_id

    conn = psycopg2.connect(POSTGRES_URI)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")

            # ── 1. 清理前核对：列出幽灵行 ─────────────────────────────
            scope = f'任务 {task_id}' if task_id else '全库'
            print(f"=== 清理前核对：{scope} 幽灵逐轮失败行 ===")
            cur.execute(GHOST_SELECT_SQL, {'task_id': task_id})
            rows = cur.fetchall()
            for r in rows:
                print(f"  TRD id={r[0]}, result={r[1]}, case={r[2]}, "
                      f"dim={r[3]}, round={r[4]}, score={r[5]}")
            print(f"  共 {len(rows)} 条")

            if not rows:
                print("无幽灵行，跳过删除与状态恢复")
            elif not args.apply:
                print("[DRY-RUN] 不执行删除；加 --apply 执行")
            else:
                # ── 2. 删除幽灵行 ─────────────────────────────────────
                cur.execute(GHOST_DELETE_SQL, {'task_id': task_id})
                print(f"删除幽灵逐轮失败行: {cur.rowcount} 条")

                # ── 3. 恢复不再有失败维度的用例状态 ───────────────────
                # （全库模式同样恢复：恢复条件自带「已无任何失败维度行」守卫）
                cur.execute(CASE_RESTORE_SQL, {'task_id': task_id})
                print(f"恢复 TaskCase 状态为 completed: {cur.rowcount} 条")

                # ── 4. 同步任务统计（仅限定了任务时；全库扫描由用例事件侧
                #    refresh_task_counts_atomic 与调度刷新兜底）─────────
                if task_id:
                    cur.execute(CASE_COUNTS_SQL, {'task_id': task_id})
                    total, completed, failed = cur.fetchone()
                    cur.execute(TASK_STATS_UPDATE_SQL,
                                {'task_id': task_id, 'completed': completed, 'failed': failed})
                    print(f"同步任务统计: total_cases={total}, completed_cases={completed}, "
                          f"failed_cases={failed}")

            conn.commit()

            # ── 5. 清理后核对 ─────────────────────────────────────────
            cur.execute(REMAINING_CHECK_SQL, {'task_id': task_id})
            remaining = cur.fetchone()[0]
            print(f"=== 清理后核对：{scope} 剩余 failed 维度记录: {remaining} 条 ===")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
