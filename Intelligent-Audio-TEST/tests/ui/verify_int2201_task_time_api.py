# -*- coding: utf-8 -*-
"""INT-2201 验收：任务域时间按本地时区展示 + 已用时长按起止推算（API 数据侧）。"""
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

API = os.environ.get('BACKEND_BASE', 'http://localhost:15000').rstrip('/')
USERNAME = os.environ.get('REACT_USER', '接线测试_admin')
PASSWORD = os.environ.get('REACT_PWD', 'JieXianTest@2026')
LOCAL = timezone(timedelta(hours=8))


def get_token():
    with urllib.request.urlopen(API + '/api/v1/auth/login/encryption-key', timeout=60) as r:
        key_data = json.loads(r.read().decode('utf-8'))
    pub = serialization.load_pem_public_key(key_data['public_key'].encode())
    enc = pub.encrypt(
        PASSWORD.encode('utf-8'),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    body = urllib.parse.urlencode({
        'username': USERNAME,
        'password_encrypted': base64.b64encode(enc).decode(),
        'encryption_key_id': key_data['kid'],
    }).encode()
    req = urllib.request.Request(
        API + '/api/v1/auth/login', data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))['access_token']


def api_get(token, path):
    req = urllib.request.Request(API + path, headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode('utf-8'))


def local_of(value):
    """后端裸 UTC 串 → 本地 (Asia/Shanghai) 'YYYY-MM-DD HH:mm'"""
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if len(s) >= 19:
        dt = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    elif len(s) >= 16:
        dt = datetime.fromisoformat(s + ':00').replace(tzinfo=timezone.utc)
    else:
        dt = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL).strftime('%Y-%m-%d %H:%M')


def elapsed_local(task):
    if not task.get('started_at'):
        return '—'
    fmt = '%Y-%m-%dT%H:%M:%S'
    def parse(v):
        if not v:
            return None
        dt = datetime.fromisoformat(str(v)).replace(tzinfo=timezone.utc)
        return dt
    start = parse(task['started_at'])
    end = parse(task.get('completed_at'))
    if end is None:
        return '(进行中,需页面实时推算)'
    sec = int((end - start).total_seconds())
    return sec


def main():
    token = get_token()
    out = {}
    lst = api_get(token, '/api/v1/tasks?page=1&per_page=10')
    items = lst.get('data', {}).get('items') or lst.get('items') or []
    print('== tasks list (%d) ==' % len(items))
    rows = []
    for t in items:
        row = {
            'id': t.get('id'),
            'name': t.get('name'),
            'created_at': t.get('created_at'),
            'created_local': local_of(t.get('created_at')),
            'execution_status': t.get('execution_status'),
            'started_at': t.get('started_at'),
            'completed_at': t.get('completed_at'),
            'used_time': t.get('used_time'),
        }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))
    out['list'] = rows

    d = api_get(token, '/api/v1/tasks/526')
    detail = d.get('data') or d
    print('== detail 526 ==')
    for k in ('id', 'name', 'created_at', 'expected_complete_time', 'expected_total_time',
              'used_time', 'started_at', 'completed_at', 'execution_status'):
        v = detail.get(k)
        print('  %s = %r  -> local %s' % (k, v, local_of(v) if isinstance(v, str) and 'T' in v else '-'))
    out['detail526'] = {
        k: detail.get(k) for k in ('id', 'name', 'created_at', 'expected_complete_time',
                                   'expected_total_time', 'used_time', 'started_at',
                                   'completed_at', 'execution_status')
    }
    out['detail526']['created_local'] = local_of(detail.get('created_at'))
    out['detail526']['expected_complete_local'] = local_of(detail.get('expected_complete_time'))

    # 找一个有 started_at + completed_at 的真实任务，验证已用时长
    cand = []
    for page in (1, 2, 3):
        pg = api_get(token, '/api/v1/tasks?page=%d&per_page=20' % page)
        its = pg.get('data', {}).get('items') or pg.get('items') or []
        for t in its:
            if t.get('started_at') and t.get('completed_at'):
                cand.append(t)
        if len(cand) >= 3:
            break
    print('== candidates with start+complete: %d ==' % len(cand))
    out['used'] = []
    for t in cand[:3]:
        dt = api_get(token, '/api/v1/tasks/%s' % t['id'])
        dd = dt.get('data') or dt
        sec = elapsed_local(dd)
        print(json.dumps({
            'id': dd.get('id'), 'name': dd.get('name'),
            'started_at': dd.get('started_at'), 'completed_at': dd.get('completed_at'),
            'used_time': dd.get('used_time'), 'elapsed_seconds': sec,
        }, ensure_ascii=False))
        out['used'].append({
            'id': dd.get('id'), 'name': dd.get('name'),
            'started_at': dd.get('started_at'), 'completed_at': dd.get('completed_at'),
            'used_time': dd.get('used_time'), 'elapsed_seconds': sec,
        })

    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'int2201', 'api_dump.json'),
              'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'int2201'), exist_ok=True)
    main()
