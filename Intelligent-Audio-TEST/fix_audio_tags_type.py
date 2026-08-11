# -*- coding: utf-8 -*-
"""修复 audio_tags 表列类型 + 添加 deleted 列。"""
import psycopg2

conn = psycopg2.connect(
    host='localhost', port=5432, dbname='intelligent_audio_test',
    user='postgres', password='postgres'
)
cur = conn.cursor()

# 检查 audio_tags 现有列
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='audio_tags' ORDER BY ordinal_position")
print(f"audio_tags columns: {cur.fetchall()}")

# 把 VARCHAR(36) 类型的 created_by_user_id/updated_by_user_id 改为 BIGINT
for col in ['created_by_user_id', 'updated_by_user_id']:
    cur.execute(f"SELECT data_type FROM information_schema.columns WHERE table_name='audio_tags' AND column_name='{col}'")
    row = cur.fetchone()
    if row and row[0] == 'character varying':
        cur.execute(f'ALTER TABLE audio_tags ALTER COLUMN {col} TYPE BIGINT USING NULL')
        print(f"[OK] Changed {col} type to BIGINT")
    else:
        print(f"[SKIP] {col} already {row[0] if row else 'missing'}")

# 添加 deleted 列（DELETED_AT_TABLES 要求 deleted 列存在）
cur.execute("SELECT 1 FROM information_schema.columns WHERE table_name='audio_tags' AND column_name='deleted'")
if not cur.fetchone():
    cur.execute('ALTER TABLE audio_tags ADD COLUMN deleted BOOLEAN NOT NULL DEFAULT FALSE')
    print("[OK] Added column deleted")
else:
    print("[SKIP] deleted already exists")

conn.commit()
cur.close()
conn.close()
print("[DONE]")
