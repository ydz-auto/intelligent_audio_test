#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""迁移校验：迁移包自身完整性 + （可选）还原后库内引用 vs 桶目录。

用法：
    python 05_verify.py                     # 只校验包内文件与清单
    DATABASE_URL=... python 05_verify.py --db  # 额外校验库内音频引用
"""
import csv
import os
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(PKG, 'bucket', 'test', 'intelligent_audio_test')
MANIFEST = os.path.join(PKG, 'bucket', 'upload_manifest.csv')

rows = list(csv.DictReader(open(MANIFEST, encoding='utf-8')))
bad = []
for r in rows:
    p = os.path.join(ROOT, r['object_key'].replace('/', os.sep))
    if not os.path.exists(p):
        bad.append(('缺失', r['object_key']))
    elif int(r['size'] or 0) and os.path.getsize(p) != int(r['size']):
        bad.append(('大小', r['object_key']))
print(f'清单 {len(rows)} 条，问题 {len(bad)} 条')
for b in bad[:10]:
    print(' ', b)

if '--db' in sys.argv:
    import psycopg2
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    cur.execute("select id,file_path from audios where deleted=false")
    miss = [f for _, f in cur.fetchall()
            if f.startswith('oss://') and not os.path.exists(
                os.path.join(ROOT, f[len('oss://'):].replace('/', os.sep)))]
    cur.execute("select count(*) from audios where file_path like 'D:%'")
    local_left = cur.fetchone()[0]
    print(f'库内引用缺失 {len(miss)} 条，仍为本地路径 {local_left} 条')
    conn.close()
