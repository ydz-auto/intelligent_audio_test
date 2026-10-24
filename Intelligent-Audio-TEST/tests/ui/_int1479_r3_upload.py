# -*- coding: utf-8 -*-
"""INT-1479 R3：真实上传 3 个自建 WAV（含生成用例链路），抓请求与回读。"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1479_r3_driver import connect, goto, text  # noqa: E402
from _int1479_api import API, H  # noqa: E402

WAVS = [os.path.join(os.environ['TEMP'], 'int1479_wav', f'接线测试_INT1479R3_{i}.wav') for i in (1, 2, 3)]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1479_audio')


def ensure_dialog(c):
    if c.eval("!!document.querySelector('[role=dialog]')"):
        return 'ALREADY'
    c.eval("Array.from(document.querySelectorAll('button')).find(x => (x.innerText||'').trim() === '上传音频').click()")
    time.sleep(1.5)
    return 'OPENED'


def main():
    c = connect()
    goto(c, '/audio-import', 5)
    for _ in range(30):
        if '音频管理' in (text(c) or ''):
            break
        time.sleep(2)
    print('DIALOG:', ensure_dialog(c))

    doc = c.send('DOM.getDocument', {'depth': 2})
    node = c.send('DOM.querySelector', {'nodeId': doc['root']['nodeId'],
                                        'selector': '[role=dialog] input[type=file]'})
    print('FILE_NODE:', node)
    c.send('DOM.setFileInputFiles', {'files': WAVS, 'nodeId': node['nodeId']})
    time.sleep(1.5)
    print('AFTER_SELECT:', (c.eval("(document.querySelector('[role=dialog]')||{}).innerText||''") or '')[:600].replace('\n', ' | '))

    # 勾选「生成测试用例」(第一个未勾选的 checkbox，位于算法类型之后)
    print('CHECK_CASE:', c.eval("""
      (function(){
        const d = document.querySelector('[role=dialog]');
        const boxes = Array.from(d.querySelectorAll('input[type=checkbox]'));
        const target = boxes.find(b => !b.checked);
        if (!target) return 'NO_UNCHECKED';
        target.click();
        return 'CLICKED:' + boxes.map(b => b.checked).join(',');
      })()
    """))
    time.sleep(0.6)

    t0 = len(c.events)
    print('SUBMIT:', c.eval("""
      (function(){
        const d = document.querySelector('[role=dialog]');
        const b = Array.from(d.querySelectorAll('button')).find(x => (x.innerText||'').trim() === '开始上传');
        if (!b) return 'NO_BTN';
        b.click(); return 'CLICKED';
      })()
    """))

    # 等待上传完成（对话框关闭或出现成功文案）
    for i in range(90):
        time.sleep(2)
        c.pump()
        dt = c.eval("(document.querySelector('[role=dialog]')||{}).innerText||''") or ''
        if not dt:
            break
        if i % 5 == 0:
            print('WAIT', i * 2, dt[:160].replace('\n', ' | '))

    c.pump()
    reqs, resp = [], []
    for e in c.events[t0:]:
        if e['method'] == 'Network.requestWillBeSent':
            r = e['params']['request']
            if '/api/' in r['url']:
                reqs.append(f"{r['method']} {r['url'].split('?')[0]} {(r.get('postData') or '')[:200]}")
        elif e['method'] == 'Network.responseReceived':
            r = e['params']['response']
            if '/api/' in r['url']:
                resp.append(f"{r['status']} {r['url'].split('?')[0]}")
    print('REQ:', json.dumps(reqs, ensure_ascii=False, indent=1))
    print('RESP:', json.dumps(resp[:40], ensure_ascii=False, indent=1))

    os.makedirs(OUT, exist_ok=True)
    c.screenshot(os.path.join(OUT, 'r3-upload-after.png'))

    # 回读
    s = requests.Session(); s.headers.update(H())
    r = s.post(f'{API}/audios', json={'page': 1, 'page_size': 20, 'keyword': '接线测试_INT1479R3'}, timeout=60)
    j = r.json()
    items = (j.get('data') or {}).get('items') or j.get('items') or []
    print('READBACK', r.status_code, json.dumps(
        [{'id': i.get('id'), 'name': i.get('name') or i.get('filename'), 'dur': i.get('duration'),
          'size': i.get('size'), 'type': i.get('audio_type'), 'tags': i.get('tags')} for i in items],
        ensure_ascii=False))
    with open(os.path.join(OUT, 'r3-upload-readback.json'), 'w', encoding='utf-8') as f:
        json.dump({'req': reqs, 'resp': resp, 'items': items}, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
