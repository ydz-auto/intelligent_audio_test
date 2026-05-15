import psycopg2
conn = psycopg2.connect('host=localhost port=5432 dbname=intelligent_audio_test user=intelligent_audio_test password=intelligent_audio_test666')
conn.autocommit = True
cur = conn.cursor()
cur.execute('DROP SCHEMA public CASCADE')
cur.execute('CREATE SCHEMA public')
cur.execute('GRANT ALL ON SCHEMA public TO intelligent_audio_test')
cur.execute('GRANT ALL ON SCHEMA public TO PUBLIC')
cur.close()
conn.close()
print('数据库已清空')