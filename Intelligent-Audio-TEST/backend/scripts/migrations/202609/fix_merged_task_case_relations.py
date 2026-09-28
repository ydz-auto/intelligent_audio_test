"""
修复合并任务的 task_case_relations 与 total_cases 不一致问题

背景：
merge() 旧逻辑从 test_results.test_case_id 提取合并任务的用例集合，
导致已删除用例的执行记录（孤儿用例）也被写入 task_case_relations，
而 total_cases 却是 SUM(源任务.total_cases)，两者口径不一致，
进而造成报告页设备卡片用例数（按结果行数统计）与任务总用例数矛盾。

修复内容：
1. 删除合并任务 task_case_relations 中「不在源任务用例集合」且「用例已从库中删除」的孤儿记录
2. 将合并任务 total_cases 校正为清理后的 TaskCase 数量
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


def fix_merged_task_case_relations():
    config = get_db_config()
    conn = psycopg2.connect(**config)
    conn.autocommit = True
    cur = conn.cursor()

    # 找出所有合并任务及其源任务
    cur.execute("""
        SELECT DISTINCT t.id AS merged_task_id
        FROM test_tasks t
        JOIN task_merge_relations mr ON mr.merged_task_id = t.id
        WHERE t.type = 'merged' AND t.deleted = false
        ORDER BY t.id
    """)
    merged_ids = [row[0] for row in cur.fetchall()]
    if not merged_ids:
        print('没有需要修复的合并任务')
        cur.close()
        conn.close()
        return

    for merged_id in merged_ids:
        # 源任务用例集合（去重）
        cur.execute("""
            SELECT DISTINCT tc.test_case_id
            FROM task_case_relations tc
            JOIN task_merge_relations mr ON mr.source_task_id = tc.task_id
            WHERE mr.merged_task_id = %s
        """, (merged_id,))
        source_case_ids = {row[0] for row in cur.fetchall()}

        # 合并任务中「不在源任务用例集合」且「用例已从用例库删除」的孤儿记录
        cur.execute("""
            SELECT id, test_case_id
            FROM task_case_relations
            WHERE task_id = %s
              AND test_case_id NOT IN (SELECT id FROM test_cases)
        """, (merged_id,))
        orphan_rows = cur.fetchall()

        # 仅删除孤儿记录（用例已删除，源任务也确认无此用例时才删除）
        to_delete = [row_id for row_id, case_id in orphan_rows if case_id not in source_case_ids]
        if to_delete:
            cur.execute(
                "DELETE FROM task_case_relations WHERE id = ANY(%s)",
                (to_delete,),
            )
            print(f'合并任务 {merged_id}: 删除孤儿 TaskCase 记录 {len(to_delete)} 条')

        # 校正 total_cases 与清理后的 TaskCase 数量一致
        cur.execute(
            "SELECT COUNT(*) FROM task_case_relations WHERE task_id = %s",
            (merged_id,),
        )
        taskcase_cnt = cur.fetchone()[0]
        cur.execute(
            "UPDATE test_tasks SET total_cases = %s WHERE id = %s",
            (taskcase_cnt, merged_id),
        )
        print(f'合并任务 {merged_id}: total_cases 校正为 {taskcase_cnt}')

    cur.close()
    conn.close()
    print('完成')


if __name__ == '__main__':
    sys.exit(fix_merged_task_case_relations())
