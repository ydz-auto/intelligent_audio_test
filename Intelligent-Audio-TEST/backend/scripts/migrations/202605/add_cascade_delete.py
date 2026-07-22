"""添加外键级联删除"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv('.env')

conn = psycopg2.connect(
    host=os.environ.get('DB_HOST', 'localhost'),
    port=int(os.environ.get('DB_PORT', 5432)),
    database=os.environ.get('DB_NAME', 'intelligent_audio_test'),
    user=os.environ.get('DB_USER', 'intelligent_audio_test'),
    password=os.environ.get('DB_PASSWORD', 'intelligent_audio_test666')
)
conn.autocommit = True
cursor = conn.cursor()

tables = [
    'report_summaries',
    'report_summary_meta',
    'report_raw_data',
    'report_cases',
    'report_metric_stats',
    'report_comparison_matrix'
]

for table in tables:
    try:
        cursor.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_report_id_fkey")
        cursor.execute(f"ALTER TABLE {table} ADD CONSTRAINT {table}_report_id_fkey FOREIGN KEY (report_id) REFERENCES test_reports(id) ON DELETE CASCADE")
        print(f"OK: {table}")
    except Exception as e:
        print(f"Error: {table} - {e}")

cursor.close()
conn.close()
print("Done")