# -*- coding: utf-8 -*-
"""
修复 task_case_relations.execution_status 数据迁移脚本

背景：
    e2e_executor._process_results 中，_execute_extra_params 内部调用了 db.session().close()，
    导致 tc_rel 从 session 的 identity map 中被移除（变为 detached），
    后续对 tc_rel.execution_status 的修改不会被 commit 持久化。
    test_results.execution_status 是正确的（通过 db.engine.connect() 独立提交），
    但 task_case_relations.execution_status 卡在 'running' 未更新。

本脚本根据 test_results.execution_status 重新推导并修复 task_case_relations.execution_status。

使用方法：
    python fix_tc_rel_execution_status.py <task_id>

示例：
    python fix_tc_rel_execution_status.py 123
"""
import os
import sys
import psycopg2


def get_db_config():
    db_user = os.environ.get('DB_USER', 'intelligent_audio_test')
    db_password = os.environ.get('DB_PASSWORD', 'intelligent_audio_test666')
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_port = os.environ.get('DB_PORT', '5432')
    db_name = os.environ.get('DB_NAME', 'intelligent_audio_test')

    return {
        'host': db_host,
        'port': db_port,
        'database': db_name,
        'user': db_user,
        'password': db_password,
    }


def fix_execution_status(task_id):
    config = get_db_config()

    print("=" * 60)
    print("修复 task_case_relations.execution_status")
    print(f"任务ID: {task_id}")
    print(f"数据库: {config['host']}:{config['port']}/{config['database']}")
    print("=" * 60)

    conn = psycopg2.connect(**config)
    conn.autocommit = False
    cursor = conn.cursor()

    # 查询该任务下 execution_status='running' 的卡住记录
    cursor.execute("""
        SELECT id, task_id, test_case_id, execution_status, evaluation_status, status
        FROM task_case_relations
        WHERE task_id = %s
          AND execution_status = 'running'
        ORDER BY id
    """, (task_id,))

    stuck_records = cursor.fetchall()

    if not stuck_records:
        print("未发现 execution_status='running' 的记录，无需修复。")
        cursor.close()
        conn.close()
        return

    print(f"发现 {len(stuck_records)} 条卡住的记录，开始逐条修复...\n")

    fixed_count = 0
    skipped_count = 0

    for tc_id, t_id, test_case_id, exec_status, eval_status, overall_status in stuck_records:
        # 查询该用例的所有 test_results
        cursor.execute("""
            SELECT execution_status
            FROM test_results
            WHERE task_id = %s
              AND test_case_id = %s
        """, (t_id, test_case_id))

        result_statuses = [row[0] for row in cursor.fetchall()]

        if not result_statuses:
            print(f"  [跳过] tc_rel.id={tc_id}, case_id={test_case_id}: 无 test_results 记录")
            skipped_count += 1
            continue

        # 如果有 test_results 仍处于 running/pending，说明执行未完成，跳过
        in_progress = [s for s in result_statuses if s in ('running', 'pending')]
        if in_progress:
            print(f"  [跳过] tc_rel.id={tc_id}, case_id={test_case_id}: "
                  f"test_results 仍有 {len(in_progress)} 条处于 running/pending")
            skipped_count += 1
            continue

        # execution_success = 所有 test_results.execution_status 均为 'completed'
        has_failed = any(s == 'failed' for s in result_statuses)
        new_exec_status = 'failed' if has_failed else 'completed'

        if new_exec_status == exec_status:
            print(f"  [跳过] tc_rel.id={tc_id}, case_id={test_case_id}: 状态已正确 ({exec_status})")
            skipped_count += 1
            continue

        # 更新 execution_status
        cursor.execute("""
            UPDATE task_case_relations
            SET execution_status = %s
            WHERE id = %s
        """, (new_exec_status, tc_id))

        # 如果执行失败，同步修正 evaluation_status 和 status
        if new_exec_status == 'failed':
            cursor.execute("""
                UPDATE task_case_relations
                SET evaluation_status = 'failed',
                    status = 'failed'
                WHERE id = %s
                  AND evaluation_status NOT IN ('completed', 'stopped')
            """, (tc_id,))
        else:
            # 执行成功，如果无评估项则评估状态也标记完成
            # 这里只修正 execution_status，evaluation_status 交给评估流程处理
            pass

        print(f"  [修复] tc_rel.id={tc_id}, case_id={test_case_id}: "
              f"execution_status: {exec_status} -> {new_exec_status} "
              f"(test_results: {len(result_statuses)} 条, failed={sum(1 for s in result_statuses if s == 'failed')})")
        fixed_count += 1

    conn.commit()

    print(f"\n{'=' * 60}")
    print(f"修复完成! 任务ID: {task_id}")
    print(f"  修复: {fixed_count} 条")
    print(f"  跳过: {skipped_count} 条")
    print(f"  总计: {len(stuck_records)} 条")
    print("=" * 60)

    cursor.close()
    conn.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python fix_tc_rel_execution_status.py <task_id>")
        sys.exit(1)

    try:
        task_id = int(sys.argv[1])
    except ValueError:
        print(f"错误: task_id 必须是整数, 收到: {sys.argv[1]}")
        sys.exit(1)

    fix_execution_status(task_id)
