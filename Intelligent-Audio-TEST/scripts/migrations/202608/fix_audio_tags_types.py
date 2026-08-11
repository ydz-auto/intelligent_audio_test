# -*- coding: utf-8 -*-
"""修复 audio_tags 表列类型：VARCHAR(36) -> BIGINT。

之前用临时脚本以 VARCHAR(36) 添加了 created_by_user_id / updated_by_user_id，
现需统一为迁移脚本的 BIGINT 类型。
"""
import psycopg2

conn = psycopg2.connect(
    host='localhost', port=5432, dbname='intelligent_audio_test',
    user='postgres', password='postgres'
)
cur = conn.cursor()

for col in ['created_by_user_id', 'updated_by_user_id']:
    cur.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name='audio_tags' AND column_name=%s", (col,)
    )
    row = cur.fetchone()
    if row and row[0] == 'character varying':
        cur.execute(f'ALTER TABLE audio_tags ALTER COLUMN {col} TYPE BIGINT USING NULL')
        print(f"[OK] {col}: VARCHAR -> BIGINT")
    elif row:
        print(f"[SKIP] {col} already {row[0]}")
    else:
        print(f"[SKIP] {col} does not exist")

conn.commit()
cur.close()
conn.close()
print("[DONE]")
