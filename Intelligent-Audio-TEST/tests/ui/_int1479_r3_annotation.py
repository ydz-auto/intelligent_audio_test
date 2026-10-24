# -*- coding: utf-8 -*-
"""INT-1479 R3：批量标注（按原始文件名匹配）真实提交 + 回读。"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1479_r3_driver import connect, goto  # noqa: E402
from _int1479_api import API, H  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1479_audio')
WAVDIR = os.path.join(os.environ['TEMP'], 'int1479_wav')
ORIG = [f'接线测试_INT1479R3_{i}' for i in (1, 2, 3)]
IDS = [2325, 2326, 2327]


def wait_rows(c, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if (c.eval("document.querySelectorAll('tbody tr').length") or 0) > 0:
            return True
        time.sleep(2)
    return False


def select_rows(c):
    # 当前显示名 测试音频_0x.wav
    return c.eval("""
      (function(){for(let i=1;i<=3;i++){const el=document.querySelector('[role=checkbox][aria-label="选择音频 测试音频_0'+i+'.wav"]');
        if(el) el.click();}return 'ok';})()""")


if __name__ == '__main__':
    anns = [os.path.join(WAVDIR, b + '.json') for b in ORIG]
    wavs = [os.path.join(WAVDIR, b + '.wav') for b in ORIG]
    c = connect()
    goto(c, '/audio-import', 5); wait_rows(c); time.sleep(2); c.pump()
    select_rows(c); time.sleep(0.8)
    c.eval("""Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='批量更新标注').click(), 'ok'""")
    print('WAIT dialog list fetch...')
    time.sleep(15); c.pump()
    doc = c.send('DOM.getDocument', {'depth': 2})
    node = c.send('DOM.querySelector', {'nodeId': doc['root']['nodeId'], 'selector': '[role=dialog] input[type=file]'})
    c.send('DOM.setFileInputFiles', {'files': wavs + anns, 'nodeId': node['nodeId']})
    time.sleep(5)
    dt = c.eval("(document.querySelector('[role=dialog]')||{}).innerText||''") or ''
    print('DIALOG:', dt[:600].replace('\n', ' | '))
    c.screenshot(os.path.join(OUT, 'r3-04-batch-annotation-matched.png'))
    t0 = len(c.events)
    print('SUBMIT:', c.eval("""(function(){const d=document.querySelector('[role=dialog]');const b=Array.from(d.querySelectorAll('button')).find(x=>(x.innerText||'').trim().startsWith('开始更新'));if(!b)return 'NO';b.click();return 'CLICKED:'+b.innerText.trim();})()"""))
    time.sleep(8); c.pump()
    print('AFTER:', (c.eval("(document.querySelector('[role=dialog]')||{}).innerText||''") or '')[:300].replace('\n', ' | '))
    req, resp = [], []
    for e in c.events[t0:]:
        if e['method'] == 'Network.requestWillBeSent':
            r = e['params']['request']
            if '/api/' in r['url']:
                req.append({'m': r['method'], 'u': r['url'].split('?')[0], 'body': (r.get('postData') or '')[:600]})
        elif e['method'] == 'Network.responseReceived':
            r = e['params']['response']
            if '/api/' in r['url']:
                resp.append({'s': r['status'], 'u': r['url'].split('?')[0]})
    print('REQ:', json.dumps(req, ensure_ascii=False, indent=1)[:3000])
    print('RESP:', json.dumps(resp, ensure_ascii=False))
    # 回读（列表端点更稳）
    s = requests.Session(); s.headers.update(H())
    r = s.post(f'{API}/audios', json={'page': 1, 'page_size': 5, 'keyword': '测试音频_0'}, timeout=120)
    items = ((r.json().get('data') or {}).get('items')) or []
    print('READBACK:', json.dumps([{'id': i.get('id'), 'name': i.get('name'), 'annotations': i.get('annotations'),
                                    'tags': i.get('tags')} for i in items], ensure_ascii=False)[:2500])
    with open(os.path.join(OUT, 'r3-annotation-result.json'), 'w', encoding='utf-8') as f:
        json.dump({'req': req, 'resp': resp, 'items': [i for i in items if i.get('id') in IDS]}, f,
                  ensure_ascii=False, indent=1)
