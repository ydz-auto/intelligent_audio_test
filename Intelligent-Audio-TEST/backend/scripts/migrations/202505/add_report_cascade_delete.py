"""
迁移脚本：为报告相关表添加级联删除外键约束
"""
import psycopg2
from psycopg2 import sql
import os
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'test_db')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

TABLES_TO_UPDATE = [
    ('report_summaries', 'report_id', 'test_reports', 'id'),
    ('report_summary_meta', 'report_id', 'test_reports', 'id'),
    ('report_raw_data', 'report_id', 'test_reports', 'id'),
    ('report_cases', 'report_id', 'test_reports', 'id'),
    ('report_metric_stats', 'report_id', 'test_reports', 'id'),
    ('report_comparison_matrix', 'report_id', 'test_reports', 'id'),
]

def get_fk_name(table_name, column_name):
    return f"fk_{table_name}_{column_name}"

def run_migration():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    conn.autocommit = True
    cursor = conn.cursor()
    
    for table_name, column_name, ref_table, ref_column in TABLES_TO_UPDATE:
        fk_name = get_fk_name(table_name, column_name)
        
        drop_sql = sql.SQL("""
            ALTER TABLE {} DROP CONSTRAINT IF EXISTS {}
        """).format(
            sql.Identifier(table_name),
            sql.Identifier(fk_name)
        )
        
        create_sql = sql.SQL("""
            ALTER TABLE {} 
            ADD CONSTRAINT {}
            FOREIGN KEY ({}) 
            REFERENCES {}({})
            ON DELETE CASCADE
        """).format(
            sql.Identifier(table_name),
            sql.Identifier(fk_name),
            sql.Identifier(column_name),
            sql.Identifier(ref_table),
            sql.Identifier(ref_column)
        )
        
        try:
            print(f"正在处理表 {table_name}...")
            cursor.execute(drop_sql)
            print(f"  已删除旧外键约束 {fk_name}")
            
            cursor.execute(create_sql)
            print(f"  已添加级联删除外键约束 {fk_name}")
        except Exception as e:
            print(f"  处理表 {table_name} 时出错: {e}")
            continue
    
    cursor.close()
    conn.close()
    print("\n迁移完成!")

if __name__ == '__main__':
    run_migration()