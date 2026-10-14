# -*- coding: utf-8 -*-
"""
清理任务 407 下"残留失败逐轮记录"（幽灵行）

背景：
- 部分 E2E 用例（如 444fe803/28aa8fd9/556e95c0/5ee1289d）的 config 每轮 evaluation.dimensions
  为空，维度只配置在顶层；但历史评估在 test_result_dimensions 留下了 round_number 非空的
  失败记录。重评走整体评估后，整体行(round_number NULL)已 completed，这些旧逐轮失败行
  不会被覆盖/清理，导致 update_task_case_status 统计到"失败维度"把用例永久判为 failed。
- 本脚本删除这些幽灵行（仅删"逐轮失败 + 同 result 同维度整体行已完成"的记录），
  并把不再有失败维度的用例 TaskCase 状态恢复为 completed。

执行：python -m backend.scripts.cleanup_reeval_ghost_round_rows
"""
import os
from sqlalchemy import create_engine, text

POSTGRES_URI = os.environ.get(
    'DATABASE_URI',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)

TASK_ID = 407


def main():
    engine = create_engine(POSTGRES_URI)
    with engine.connect() as conn:
        print(f"=== 清理前：任务 {TASK_ID} 幽灵逐轮失败行 ===")
        rows = conn.execute(text("""
            SELECT trd.id, trd.test_result_id, tr.test_case_id, trd.dimension_id,
                   trd.round_number, trd.score
            FROM test_result_dimensions trd
            JOIN test_results tr ON tr.id = trd.test_result_id
            WHERE tr.task_id = :task_id
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
        """), {'task_id': TASK_ID}).fetchall()
        for r in rows:
            print(f"  TRD id={r.id}, result={r.test_result_id}, case={r.test_case_id}, "
                  f"dim={r.dimension_id}, round={r.round_number}, score={r.score}")
        print(f"  共 {len(rows)} 条")

        if not rows:
            print("无幽灵行，跳过删除")
        else:
            del_count = conn.execute(text("""
                DELETE FROM test_result_dimensions trd
                WHERE trd.test_result_id IN (
                    SELECT id FROM test_results WHERE task_id = :task_id
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
            """), {'task_id': TASK_ID})
            print(f"删除幽灵逐轮失败行: {del_count.rowcount} 条")

            # 恢复不再有失败维度的用例状态
            upd = conn.execute(text("""
                UPDATE task_case_relations tc
                SET evaluation_status = 'completed',
                    status = 'completed'
                WHERE tc.task_id = :task_id
                  AND tc.execution_status = 'completed'
                  AND tc.evaluation_status = 'failed'
                  AND NOT EXISTS (
                      SELECT 1 FROM test_results tr
                      JOIN test_result_dimensions trd ON trd.test_result_id = tr.id
                      WHERE tr.task_id = tc.task_id
                        AND tr.test_case_id = tc.test_case_id
                        AND trd.evaluation_status = 'failed'
                  )
            """), {'task_id': TASK_ID})
            print(f"恢复 TaskCase 状态为 completed: {upd.rowcount} 条")

        conn.commit()

        print("=== 清理后核对 ===")
        remaining = conn.execute(text("""
            SELECT count(*) FROM test_result_dimensions trd
            JOIN test_results tr ON tr.id = trd.test_result_id
            WHERE tr.task_id = :task_id AND trd.evaluation_status = 'failed'
        """), {'task_id': TASK_ID}).scalar()
        print(f"任务 {TASK_ID} 剩余 failed 维度记录: {remaining} 条")

        # 同步任务统计（completed_cases 按当前 status='completed' 的用例数刷新）
        total = conn.execute(text(
            "SELECT count(*) FROM task_case_relations WHERE task_id = :task_id AND deleted = false"
        ), {'task_id': TASK_ID}).scalar()
        completed = conn.execute(text(
            "SELECT count(*) FROM task_case_relations WHERE task_id = :task_id AND status = 'completed' AND deleted = false"
        ), {'task_id': TASK_ID}).scalar()
        conn.execute(text("""
            UPDATE test_tasks
            SET completed_cases = :completed, failed_cases = 0
            WHERE id = :task_id
        """), {'task_id': TASK_ID, 'completed': completed})
        print(f"同步任务统计: total_cases={total}, completed_cases={completed}, failed_cases=0")


if __name__ == '__main__':
    main()
