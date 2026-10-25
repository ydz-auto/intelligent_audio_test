# -*- coding: utf-8 -*-
"""造等价性取证库：主库 apis 副本 + 3 行「legacy websocket_api」存量行。

存量主库里 websocket_api 为 0 行（B0 §2.2），等价性要覆盖流式道必须补造
与迁移前同形态的行：device_type='websocket_api' 且端点 ws://（老口径按端点为
WEBSOCKET），meta.protocol 分别留空 / 'wss'（交叉校验路径）。

用法：python _int1799_probe/make_equiv_db.py <目标库名>
"""
import json
import os
import sys

import psycopg2

SRC = os.environ.get(
    'SRC_DATABASE_URL',
    'postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:15432/intelligent_audio_test')
DST_DB = sys.argv[1] if len(sys.argv) > 1 else 'int1799_equiv'
HOST = 'localhost'


def _conn(dbname):
    return psycopg2.connect(host=HOST, port=15432, dbname=dbname,
                            user='intelligent_audio_test',
                            password='intelligent_audio_test666')


def main():
    src = _conn('intelligent_audio_test')
    src.autocommit = True
    cur = src.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_name='apis' ORDER BY ordinal_position")
    cols = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT %s FROM apis ORDER BY id LIMIT 1" % ','.join(cols))
    row = dict(zip(cols, cur.fetchone()))
    src.close()

    dst = _conn(DST_DB)
    dst.autocommit = False
    dc = dst.cursor()
    # 目标库已由 pg_dump 克隆好结构；取最大 id 递增插入三行 legacy websocket
    dc.execute('SELECT max(id) FROM apis')
    base = dc.fetchone()[0] or 0
    for offset, (meta_protocol, endpoint) in enumerate(
            [(None, 'ws://legacy.example/realtime'),
             ('wss', 'wss://legacy.example/realtime'),
             ('websocket', 'ws://legacy.example/rt2')], start=1):
        new = dict(row)
        new['id'] = base + offset
        new['name'] = 'int1799-legacy-ws-%d' % offset
        new['device_type'] = 'websocket_api'
        new['deleted'] = True
        new['api_endpoints'] = json.dumps([{'endpoint': endpoint, 'max_process': 1,
                                            'max_timeout': 30,
                                            'max_audio_duration': 60}])
        meta = json.loads(row['meta']) if isinstance(row['meta'], str) else (row['meta'] or {})
        meta = dict(meta)
        meta.pop('protocol', None)
        if meta_protocol:
            meta['protocol'] = meta_protocol
        new['meta'] = json.dumps(meta)
        keys = list(new.keys())
        dc.execute(
            'INSERT INTO apis (%s) VALUES (%s)' % (
                ','.join(keys), ','.join(['%s'] * len(keys))),
            [new[k] for k in keys])
    dst.commit()
    dc.execute("SELECT id, device_type, meta::jsonb->>'protocol' FROM apis "
               "WHERE device_type='websocket_api' ORDER BY id")
    print('插入 legacy websocket 行:', dc.fetchall())
    dst.close()


if __name__ == '__main__':
    main()
