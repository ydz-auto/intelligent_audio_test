# -*- coding: utf-8 -*-
"""INT-1486 复走 N 前置探针：建一个不可达端点的 API，调 POST /apis/{id}/health 看失败态返回体形状。"""
import json, os, time, urllib.request

API = 'http://127.0.0.1:15000'
ART = 'tests/ui/artifacts/int1486'
TOKEN = open(os.path.join(ART, 'token.txt')).read().strip()
SUFFIX = str(int(time.time()))[-6:]
NAME = '接线测试_INT1486_NPROBE_' + SUFFIX


def req(method, path, body=None, timeout=240):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method,
                               headers={'Authorization': 'Bearer ' + TOKEN,
                                        'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8')
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, raw[:800]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')[:800]
    except Exception as e:
        return 'ERR', str(e)


st, body = req('POST', '/api/v1/apis', {
    'name': NAME, 'description': 'INT-1486 探针', 'algorithm_type': 'voice_llm',
    'default_max_process': 5,
    'endpoints': [{'endpoint': 'https://int1486-not-exist-host-' + SUFFIX + '.invalid.example/api/v1/health-probe',
                   'name': None, 'max_process': 1, 'max_timeout': 30, 'max_audio_duration': 60,
                   'status': 'online', 'priority': 1, 'description': None}]})
print('CREATE', st, json.dumps(body, ensure_ascii=False)[:500])
api_id = (body.get('data') or {}).get('id') if isinstance(body, dict) else None
if api_id:
    t0 = time.time()
    st2, body2 = req('POST', f'/api/v1/apis/{api_id}/health')
    print('HEALTH', st2, 'elapsed %.1fs' % (time.time() - t0))
    print(json.dumps(body2, ensure_ascii=False, indent=2)[:2500])
    print('CLEAN', req('DELETE', f'/api/v1/apis/{api_id}'))
