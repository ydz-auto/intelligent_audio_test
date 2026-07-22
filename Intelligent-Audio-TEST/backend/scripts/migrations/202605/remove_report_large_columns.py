"""
数据库迁移脚本：删除 Report 表的大 JSON 字段，添加新字段
解决历史报告页面加载慢的问题

运行方式：
python backend/scripts/migrations/202505/remove_report_large_columns.py

或直接执行 SQL：
psql -U intelligent_audio_test -d intelligent_audio_test -c "
ALTER TABLE test_reports DROP COLUMN IF EXISTS summary;
ALTER TABLE test_reports DROP COLUMN IF EXISTS comparison_data;
ALTER TABLE test_reports DROP COLUMN IF EXISTS test_reports_cases;
ALTER TABLE report_summaries ADD COLUMN IF NOT EXISTS task_ids JSONB;
ALTER TABLE report_detail_data ADD COLUMN IF NOT EXISTS comparison_matrix JSONB;
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


def migrate():
    """执行迁移"""
    config = get_db_config()
    
    print(f"连接数据库: {config['host']}:{config['port']}/{config['database']}")
    
    conn = psycopg2.connect(**config)
    conn.autocommit = True
    cursor = conn.cursor()
    
    sqls = [
        "ALTER TABLE test_reports DROP COLUMN IF EXISTS summary",
        "ALTER TABLE test_reports DROP COLUMN IF EXISTS comparison_data",
        "ALTER TABLE test_reports DROP COLUMN IF EXISTS test_reports_cases",
        "ALTER TABLE report_summaries ADD COLUMN IF NOT EXISTS task_ids JSONB",
        "ALTER TABLE report_detail_data ADD COLUMN IF NOT EXISTS comparison_matrix JSONB",
        "ALTER TABLE report_summaries ADD COLUMN IF NOT EXISTS task_ids JSON",
        "ALTER TABLE report_detail_data ADD COLUMN IF NOT EXISTS comparison_matrix JSON",
    ]
    
    for sql in sqls:
        try:
            cursor.execute(sql)
            print(f"执行成功: {sql}")
        except Exception as e:
            print(f"执行失败: {sql} - {e}")
    
    cursor.close()
    conn.close()
    
    print("\n迁移完成")


if __name__ == "__main__":
    migrate()