"""
数据库迁移脚本：为 Task 表添加索引
独立脚本，不依赖 backend 模块

运行方式：
python backend/scripts/migrations/202605/add_task_indexes.py

或直接执行 SQL：
psql -U intelligent_audio_test -d intelligent_audio_test -c "
CREATE INDEX IF NOT EXISTS idx_task_status ON test_tasks (status);
CREATE INDEX IF NOT EXISTS idx_task_algorithm_type ON test_tasks (algorithm_type);
CREATE INDEX IF NOT EXISTS idx_task_created_at ON test_tasks (created_at);
CREATE INDEX IF NOT EXISTS idx_task_status_deleted ON test_tasks (status, deleted);
ANALYZE test_tasks;
"
"""

import os
import psycopg2
from dotenv import load_dotenv


def get_db_config():
    """从环境变量获取数据库配置"""
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
    
    return {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'port': int(os.environ.get('DB_PORT', 5432)),
        'database': os.environ.get('DB_NAME', 'intelligent_audio_test'),
        'user': os.environ.get('DB_USER', 'intelligent_audio_test'),
        'password': os.environ.get('DB_PASSWORD', 'intelligent_audio_test666'),
    }


def add_task_indexes():
    """为 Task 表添加索引"""
    config = get_db_config()
    
    print(f"连接数据库: {config['host']}:{config['port']}/{config['database']}")
    
    conn = psycopg2.connect(**config)
    conn.autocommit = True
    cursor = conn.cursor()
    
    indexes = [
        ("idx_task_status", "status"),
        ("idx_task_algorithm_type", "algorithm_type"),
        ("idx_task_created_at", "created_at"),
        ("idx_task_status_deleted", "status, deleted"),
    ]
    
    for index_name, columns in indexes:
        sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON test_tasks ({columns})"
        try:
            cursor.execute(sql)
            print(f"成功创建索引: {index_name} ({columns})")
        except Exception as e:
            print(f"创建索引 {index_name} 失败: {e}")
    
    cursor.execute("ANALYZE test_tasks")
    print("已执行 ANALYZE test_tasks")
    
    cursor.close()
    conn.close()
    
    print("\n迁移完成")


if __name__ == "__main__":
    add_task_indexes()