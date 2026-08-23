# -*- coding: utf-8 -*-
"""将所有 aux output 参数的 visible_in_report 设为 true"""
import psycopg2

conn = psycopg2.connect(
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test'
)
cur = conn.cursor()
cur.execute("""
    UPDATE evaluation_dimension_params
    SET visible_in_report = true
    WHERE param_direction = 'output'
      AND output_role = 'aux'
      AND deleted = false
""")
print(f"Updated {cur.rowcount} rows")
conn.commit()
conn.close()
