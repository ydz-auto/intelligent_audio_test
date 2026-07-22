from sqlalchemy import create_engine, text

engine = create_engine('postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/intelligent_audio_test')

result = engine.connect().execute(text("""
    SELECT sequence_name,
           regexp_replace(sequence_name, '_id_seq', '') as table_name
    FROM information_schema.sequences
    WHERE sequence_schema = 'public'
"""))

sequences = result.fetchall()
result.close()

for seq_name, table_name in sequences:
    conn = engine.connect()
    conn.execute(text("COMMIT"))
    try:
        max_result = conn.execute(text(f'SELECT MAX(id) FROM {table_name}'))
        max_id = max_result.scalar() or 0

        seq_result = conn.execute(text(f'SELECT last_value FROM {seq_name}'))
        last_val = seq_result.scalar()

        if last_val != max_id:
            print(f'{table_name}: last_value={last_val}, MAX(id)={max_id} - 修复')
            if max_id == 0:
                conn.execute(text(f"SELECT setval('{seq_name}', 1, false)"))
                print(f'  已修复为 1 (空表，下一个ID将是1)')
            else:
                conn.execute(text(f"SELECT setval('{seq_name}', {max_id}, true)"))
                print(f'  已修复为 {max_id}')
        else:
            print(f'{table_name}: OK ({last_val})')
    except Exception as e:
        print(f'{table_name}: 错误 - {str(e)[:60]}')
    finally:
        conn.close()

engine.dispose()
print('\n完成!')
