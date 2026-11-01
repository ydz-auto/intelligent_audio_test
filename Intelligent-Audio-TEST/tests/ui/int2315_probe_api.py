# -*- coding: utf-8 -*-
"""INT-2315 接口探针：登录 docker 栈 :15000 → 异步导出作业 3 端点契约核对。

只读业务数据（导出不写库）；用来确认前端要消费的字段名与状态流转。
用法：python tests/ui/int2315_probe_api.py
"""
import base64
import json
import sys
import time

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes

BASE = 'http://localhost:15000/api/v1'
USER = 'dev_user'
PASSWORD = 'dev_password'

s = requests.Session()


def login():
    key = s.get(f'{BASE}/auth/login/encryption-key').json()
    d = key.get('data', key)
    pem = d['public_key']
    pub = serialization.load_pem_public_key(pem.encode())
    enc = pub.encrypt(
        PASSWORD.encode(),
        padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    body = {
        'username': USER,
        'password_encrypted': base64.b64encode(enc).decode(),
        'encryption_key_id': d['kid'],
    }
    r = s.post(f'{BASE}/auth/login', data=body)
    r.raise_for_status()
    tok = r.json().get('access_token') or r.json().get('data', {}).get('access_token')
    s.headers['Authorization'] = f'Bearer {tok}'
    return tok


def dump(label, r):
    print(f'--- {label}: {r.status_code}')
    try:
        print(json.dumps(r.json(), ensure_ascii=False)[:1500])
    except Exception:
        print(repr(r.content[:400]))
    print()


def main():
    login()

    # 取前 5 个用例 id（只读）
    r = s.get(f'{BASE}/testcases', params={'page': 1, 'page_size': 5})
    dump('GET /testcases', r)
    data = r.json().get('data', r.json())
    items = data.get('items') or data.get('test_cases') or []
    ids = [it['id'] for it in items[:3]]
    print('ids =', ids)

    # 1. 提交
    payload = {'ids': ids, 'format': 'zip', 'include_reference_params': True, 'include_audios': False}
    r = s.post(f'{BASE}/testcases/export/jobs', json=payload)
    dump('POST /testcases/export/jobs', r)
    job = r.json()
    job = job.get('data', job)
    task_id = job.get('task_id')

    # 2. 在办期间再提交 → 429 体结构
    r2 = s.post(f'{BASE}/testcases/export/jobs', json={'ids': ids, 'format': 'xlsx'})
    dump('POST 第二次（期望 429）', r2)

    # 3. 轮询
    for _ in range(60):
        r = s.get(f'{BASE}/testcases/export/jobs/{task_id}')
        st = r.json().get('data', r.json())
        print('poll:', st.get('status'), st.get('phase'), st.get('progress'), 'result=',
              json.dumps(st.get('result'), ensure_ascii=False)[:200])
        if st.get('status') in ('done', 'failed', 'expired'):
            dump('GET final', r)
            break
        time.sleep(1)

    # 4. 下载
    r = s.get(f'{BASE}/testcases/export/jobs/{task_id}/download')
    print('download:', r.status_code, r.headers.get('Content-Disposition'), len(r.content))
    # 5. 过期/不存在
    dump('GET 不存在任务', s.get(f'{BASE}/testcases/export/jobs/00000000-0000-0000-0000-000000000000'))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
