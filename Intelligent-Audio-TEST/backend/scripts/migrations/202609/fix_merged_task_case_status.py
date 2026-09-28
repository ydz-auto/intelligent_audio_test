"""
修复合并任务 task_case_relations 的用例执行/评估状态

背景：
旧 merge() 创建合并任务 TaskCase 时仅设置 status='completed'，
未继承源任务的 execution_status / evaluation_status，
导致前端任务详情模态窗中所有用例都显示为"等待中"、完成数/进度为 0。

修复内容：
1. 将合并任务 TaskCase 的 status/execution_status/evaluation_status
   及时间/耗时/错误信息从源任务对应用例继承（同一用例多源时取最后一条）
2. 刷新合并任务 total_cases/completed_cases/failed_cases 与 TaskCase 自洽
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


def fix_merged_task_case_status():
    config = get_db_config()
    conn = psycopg2.connect(**config)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT t.id
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
        # 继承源任务同用例的 TaskCase 状态（同一用例多源时取 id 最大的那条）
        cur.execute("""
            UPDATE task_case_relations dst
            SET status = src.status,
                execution_status = src.execution_status,
                evaluation_status = src.evaluation_status,
                started_at = src.started_at,
                completed_at = src.completed_at,
                duration = src.duration,
                error_message = src.error_message
            FROM (
                SELECT DISTINCT ON (stc.test_case_id) stc.*
                FROM task_case_relations stc
                JOIN task_merge_relations mr ON mr.source_task_id = stc.task_id
                WHERE mr.merged_task_id = %s
                ORDER BY stc.test_case_id, stc.id DESC
            ) src
            WHERE dst.task_id = %s AND dst.test_case_id = src.test_case_id
        """, (merged_id, merged_id))

        # 刷新任务级统计与 TaskCase 自洽
        cur.execute("""
            UPDATE test_tasks t
            SET total_cases = (SELECT COUNT(*) FROM task_case_relations tc WHERE tc.task_id = t.id),
                completed_cases = (SELECT COUNT(*) FROM task_case_relations tc WHERE tc.task_id = t.id AND tc.status = 'completed'),
                failed_cases = (SELECT COUNT(*) FROM task_case_relations tc WHERE tc.task_id = t.id AND tc.status = 'failed')
            WHERE t.id = %s
        """, (merged_id,))
        print(f'合并任务 {merged_id}: TaskCase 状态已从源任务继承并刷新统计')

    cur.close()
    conn.close()
    print('完成')


if __name__ == '__main__':
    sys.exit(fix_merged_task_case_status())
