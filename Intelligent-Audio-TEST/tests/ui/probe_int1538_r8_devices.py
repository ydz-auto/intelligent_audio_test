# -*- coding: utf-8 -*-
"""INT-1538 R8：实验室通道四设备直连复核（POST /audios/2358/preview + stop-preview）。

设备 1/2/11/12（RME Fireface UCX II，online）逐一放音 1.5s 后停止，记录响应码与关键字段
（duration / device / 停止任务数）。只读音频 2358，不写业务数据。
"""
import json
import time
import urllib.request

API = 'http://127.0.0.1:15000/api/v1'
AUDIO_ID = 2358
OUT = {'audio_id': AUDIO_ID, 'devices': []}


def call(path, method='GET', body=None):
    data = None
    headers = {'Content-Type': 'application/json'}
    if body is not None:
        data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8', 'replace'))
        except Exception:
            return e.code, None


st, devs = call('/playback-devices')
byname = {int(x['id']): x for x in ((devs or {}).get('data') or {}).get('items') or []}
for dev in (1, 2, 11, 12):
    item = {'id': dev, 'name': (byname.get(dev) or {}).get('name'),
            'status': (byname.get(dev) or {}).get('status'),
            'unique': (byname.get(dev) or {}).get('device_unique_id')}
    st, r = call('/audios/%d/preview' % AUDIO_ID, 'POST', {'playback_device_id': dev, 'offset': 0})
    item['preview'] = {'status': st, 'message': (r or {}).get('message'),
                       'data': (r or {}).get('data')}
    time.sleep(1.5)
    st2, r2 = call('/audios/%d/stop-preview' % AUDIO_ID, 'POST', {})
    item['stop'] = {'status': st2, 'message': (r2 or {}).get('message')}
    OUT['devices'].append(item)
    time.sleep(0.5)

with open('evidence_int1538_r8_devices.json', 'w', encoding='utf-8') as f:
    json.dump(OUT, f, ensure_ascii=False, indent=1)
print(json.dumps(OUT, ensure_ascii=False, indent=1))
