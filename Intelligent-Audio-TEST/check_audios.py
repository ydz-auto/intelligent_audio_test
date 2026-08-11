import psycopg2
conn = psycopg2.connect(host='localhost',port=5432,dbname='intelligent_audio_test',user='postgres',password='postgres')
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='audios' ORDER BY ordinal_position")
print('audios:', [r[0] for r in cur.fetchall()])
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='audio_tags' ORDER BY ordinal_position")
print('audio_tags:', [r[0] for r in cur.fetchall()])
conn.close()
