# -*- coding: utf-8 -*-
"""INT-2173 通知/SSE 直连探测：网关 /sse/events 是否推送 task_progress / task_log。

用 API 建一个「接线测试_」任务并启动，SSE 直连取事件；结束按 id 软删+purge。
"""
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault('API_BASE', 'http://127.0.0.1:15000')
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import capture_int1485_system_settings as B  # noqa: E402

NAME = '接线测试_INT2173_SSE_%s' % time.strftime('%m%d%H%M%S')
EVENTS = []
RAW = []


def sse_reader(token, stop):
    req = urllib.request.Request(B.API + '/api/v1/sse/events',
                                 headers={'Authorization': 'Bearer ' + token, 'Accept': 'text/event-stream'})
    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except Exception as e:
        EVENTS.append({'error': 'connect: %s' % e})
        return
    buf = b''
    while not stop.is_set():
        try:
            chunk = resp.read(1)
        except Exception as e:
            EVENTS.append({'error': 'read: %s' % e})
            break
        if not chunk:
            break
        buf += chunk
        while b'\n\n' in buf:
            frame, buf = buf.split(b'\n\n', 1)
            RAW.append(frame.decode('utf-8', 'replace')[:500])
            ev = {}
            for line in frame.decode('utf-8', 'replace').split('\n'):
                if line.startswith('event:'):
                    ev['event'] = line[6:].strip()
                elif line.startswith('data:'):
                    ev['data'] = line[5:].strip()[:300]
            if ev:
                EVENTS.append(ev)


def main():
    token, _ = B.rsa_login_token('接线测试_admin', 'JieXianTest@2026')
    stop = threading.Event()
    th = threading.Thread(target=sse_reader, args=(token, stop), daemon=True)
    th.start()
    time.sleep(3)
    body = {
        'name': NAME,
        'algorithm_type': 'voice_llm',
        'case_ids': ['7e775d1b-ca86-455e-bf4d-8509014359e9'],
        'device_ids': [],
        'api_ids': [410],
        'target_modes': [{'target_type': 'api', 'target_id': 410, 'mode': 'parallel'}],
        'case_devices': [{'case_id': '7e775d1b-ca86-455e-bf4d-8509014359e9', 'device_type': 'http_api', 'device_id': '410'}],
        'config': {'rounds': 1, 'timeout': 60, 'retries': 0, 'concurrent_tasks': 4},
    }
    st, d = B.api('/api/v1/tasks', token, method='POST', body=body)
    tid = (d.get('data') or {}).get('id') if isinstance(d, dict) else None
    print('create', st, d if tid is None else tid)
    if tid:
        print('start', B.api('/api/v1/tasks/%d/start' % tid, token, method='POST')[0])
    time.sleep(25)
    stop.set()
    time.sleep(1)
    from collections import Counter
    types = Counter(e.get('event') for e in EVENTS if e.get('event'))
    print('EVENT TYPES', dict(types))
    for e in EVENTS[:25]:
        print('EV', json.dumps(e, ensure_ascii=False)[:260])
    print('ERRORS', [e for e in EVENTS if e.get('error')][:3])
    if tid:
        print('cleanup', B.api('/api/v1/tasks/%d' % tid, token, method='DELETE')[0],
              B.api('/api/v1/tasks/%d/purge' % tid, token, method='DELETE')[0])
    with open(os.path.join(HERE, 'artifacts', 'int2173', 'sse_probe.json'), 'w', encoding='utf-8') as f:
        json.dump({'events': EVENTS, 'types': dict(types), 'raw_tail': RAW[-10:]}, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    os.makedirs(os.path.join(HERE, 'artifacts', 'int2173'), exist_ok=True)
    main()
