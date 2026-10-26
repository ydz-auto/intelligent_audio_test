# -*- coding: utf-8 -*-
"""INT-1538 R8 探针：网关 lab 播放链路（testcases/{id}/preview backend + stop_preview）。

只读探测为主：自建临时组/用例（2 轮, audio 2358, 设备 1/2），调用 lab preview → 2s → stop，
最后 DELETE + purge 清理。
"""
import json
import time
import urllib.request

API = 'http://127.0.0.1:15000/api/v1'
TAG = time.strftime('%m%d%H%M%S')
GROUP = '接线测试_INT1538_R8探针组_' + TAG
NAME = '接线测试_INT1538_R8探针用例_' + TAG
AUDIO_ID = 2358
AUDIO_NAME = 'url_src_A.wav'
OUT = {}


def call(path, method='GET', body=None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json; charset=utf-8'
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = r.read().decode('utf-8', 'replace')
            return r.status, txt
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


def jcall(path, method='GET', body=None):
    st, txt = call(path, method, body)
    try:
        return st, json.loads(txt), txt
    except Exception:
        return st, None, txt


GID = CID = ''
try:
    st, p, raw = jcall('/groups', 'POST', {'name': GROUP, 'description': 'R8 probe', 'algorithm_type': ''})
    OUT['create_group'] = {'status': st, 'body': raw[:200]}
    GID = str(((p or {}).get('data') or {}).get('id') or '')

    st, p, raw = jcall('/testcases?page=1&page_size=100&keyword=' + 'HJ049')
    items = ((p or {}).get('data') or {}).get('items') or []
    base = next((x for x in items if len((x.get('config') or {}).get('rounds') or []) >= 2), None)
    OUT['base_case'] = (base or {}).get('id')
    cfg = json.loads(json.dumps((base or {}).get('config') or {}))
    for rd in cfg.get('rounds') or []:
        for a in rd.get('audios') or []:
            a['audio_id'] = AUDIO_ID
            a['audio_name'] = AUDIO_NAME
            a['playback_device_id'] = 1 if rd.get('round_number') == 1 else 2
            a['playback_device_name'] = 'dev%d' % a['playback_device_id']
    st, p, raw = jcall('/testcases', 'POST', {'name': NAME, 'description': 'R8 probe',
                                              'group_id': GID, 'config': cfg})
    OUT['create_case'] = {'status': st, 'body': raw[:200]}
    CID = str(((p or {}).get('data') or {}).get('id') or '')
    OUT['cid'] = CID

    st, p, raw = jcall('/testcases/%s/preview' % CID, 'POST',
                       {'offset': 0, 'preview_type': 'backend', 'playback_mode': 'backend'})
    OUT['preview_backend'] = {'status': st, 'body': raw[:1500]}
    OUT['t_preview'] = time.strftime('%H:%M:%S')
    time.sleep(2.0)
    st, p, raw = jcall('/testcases/%s/stop_preview' % CID, 'POST', {})
    OUT['stop_preview'] = {'status': st, 'body': raw[:800], 't': time.strftime('%H:%M:%S')}
finally:
    if CID:
        st, p, raw = jcall('/testcases/' + CID, 'DELETE')
        OUT['cleanup_case_delete'] = st
        st, p, raw = jcall('/testcases/' + CID + '/purge', 'DELETE')
        OUT['cleanup_case_purge'] = {'status': st, 'body': raw[:100]}
    if GID:
        st, p, raw = jcall('/groups/' + GID, 'DELETE')
        OUT['cleanup_group'] = st
    with open('probe_r8_labapi.json', 'w', encoding='utf-8') as f:
        json.dump(OUT, f, ensure_ascii=False, indent=1)
    print(json.dumps(OUT, ensure_ascii=False, indent=1)[:2500])
