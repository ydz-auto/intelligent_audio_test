# -*- coding: utf-8 -*-
import psycopg2

c = psycopg2.connect(
    "postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:15435/intelligent_audio_test")
cur = c.cursor()
cur.execute("select algorithm_type, count(*) from test_reports group by 1")
print('reports:', cur.fetchall())
cur.execute("select distinct algorithm_type from report_summaries" if False else "select 1")
