import sqlite3
import json
import os
import sys

def migrate_algorithm_result_to_json():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data.db')
    print(f'Database path: {db_path}')

    if not os.path.exists(db_path):
        print(f'Error: Database not found at {db_path}')
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 统计需要转换的记录
    cursor.execute("SELECT COUNT(*) FROM test_results WHERE algorithm_result IS NOT NULL AND typeof(algorithm_result) = 'text'")
    count = cursor.fetchone()[0]
    print(f'需要转换的记录数: {count}')

    if count == 0:
        print('没有需要转换的记录')
        conn.close()
        return

    # 获取需要转换的记录
    cursor.execute("SELECT id, algorithm_result FROM test_results WHERE algorithm_result IS NOT NULL AND typeof(algorithm_result) = 'text'")
    records = cursor.fetchall()

    success_count = 0
    error_count = 0
    error_ids = []

    for record_id, algorithm_result_str in records:
        try:
            # 解析 JSON 字符串
            parsed_json = json.loads(algorithm_result_str)

            # 更新数据库，将 JSON 对象序列化回字符串存储
            # SQLite 会自动将其存储为 JSON 类型
            cursor.execute(
                "UPDATE test_results SET algorithm_result = ? WHERE id = ?",
                (json.dumps(parsed_json), record_id)
            )
            success_count += 1
        except json.JSONDecodeError as e:
            error_count += 1
            error_ids.append((record_id, str(e)))
            print(f'Error parsing JSON for id={record_id}: {e}')

    conn.commit()

    # 验证转换结果
    cursor.execute("SELECT typeof(algorithm_result), COUNT(*) FROM test_results WHERE algorithm_result IS NOT NULL GROUP BY typeof(algorithm_result)")
    print('\n=== 转换后类型分布 ===')
    for row in cursor.fetchall():
        print(f'类型: {row[0]}, 数量: {row[1]}')

    print(f'\n=== 转换结果 ===')
    print(f'成功: {success_count}')
    print(f'失败: {error_count}')

    if error_ids:
        print(f'\n失败的记录ID和原因:')
        for rec_id, err in error_ids:
            print(f'  ID {rec_id}: {err}')

    conn.close()
    print('\n转换完成!')

if __name__ == '__main__':
    migrate_algorithm_result_to_json()
