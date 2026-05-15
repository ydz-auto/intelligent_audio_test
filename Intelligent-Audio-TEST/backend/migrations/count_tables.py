import psycopg2
conn = psycopg2.connect('host=localhost port=5432 dbname=intelligent_audio_test user=intelligent_audio_test password=intelligent_audio_test666')
cur = conn.cursor()
cur.execute("""
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_type = 'BASE TABLE'
    ORDER BY table_name
""")
tables = [row[0] for row in cur.fetchall()]

print(f"{'表名':<35} 记录数")
print('-' * 45)
total = 0
for table in tables:
    cur.execute(f'SELECT COUNT(*) FROM {table}')
    count = cur.fetchone()[0]
    print(f'{table:<35} {count}')
    total += count

print('-' * 45)
print(f'总计: {total}')

cur.close()
conn.close()