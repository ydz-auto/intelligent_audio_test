# -*- coding: utf-8 -*-
"""INT-1479 R3：URL 真实导入 + 文件夹导入（对话框关闭后重开）。"""
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
URL = 'http://127.0.0.1:18080/int1479_url_test.wav'


def wait_rows(c, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if (c.eval("document.querySelectorAll('tbody tr').length") or 0) > 0:
            return True
        time.sleep(2)
    return False


def open_dialog(c, label):
    return c.eval("""(function(l){const b=Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').trim()===l);
      if(!b)return 'NO_BTN';b.click();return 'CLICKED';})(%s)""" % json.dumps(label))


def dlg_btn(c, label):
    return c.eval("""(function(l){const d=document.querySelector('[role=dialog],[role=alertdialog]');if(!d)return 'NO_DLG';
      const b=Array.from(d.querySelectorAll('button')).find(x=>(x.innerText||'').trim().startsWith(l));
      if(!b)return 'NO_BTN:'+l;b.click();return 'CLICKED:'+l;})(%s)""" % json.dumps(label))


def set_textarea(c, value):
    return c.eval("""(function(v){const d=document.querySelector('[role=dialog],[role=alertdialog]');if(!d)return 'NO_DLG';
      const t=d.querySelector('textarea');if(!t)return 'NO_TA';
      Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set.call(t,v);
      t.dispatchEvent(new Event('input',{bubbles:true}));t.dispatchEvent(new Event('change',{bubbles:true}));
      return 'SET';})(%s)""" % json.dumps(value))


def dlg_text(c):
    return c.eval("(document.querySelector('[role=dialog],[role=alertdialog]')||{}).innerText||''") or ''


def capture(c, t0):
    c.pump()
    req, resp = [], []
    for e in c.events[t0:]:
        if e['method'] == 'Network.requestWillBeSent':
            r = e['params']['request']
            if '/api/' in r['url']:
                req.append({'m': r['method'], 'u': r['url'].split('?')[0], 'body': (r.get('postData') or '')[:400]})
        elif e['method'] == 'Network.responseReceived':
            r = e['params']['response']
            if '/api/' in r['url']:
                resp.append({'s': r['status'], 'u': r['url'].split('?')[0]})
    return req, resp


if __name__ == '__main__':
    c = connect(); s = requests.Session(); s.headers.update(H())
    goto(c, '/audio-import', 5); wait_rows(c); time.sleep(2); c.pump()
    out = {}

    print('OPEN URL', open_dialog(c, 'URL 导入')); time.sleep(1.2)
    print('SET', set_textarea(c, URL)); time.sleep(0.8)
    print('COUNT:', [x for x in dlg_text(c).split('\n') if '已识别' in x])
    c.screenshot(os.path.join(OUT, 'r3-03-url-filled.png'))
    t0 = len(c.events)
    print('SUBMIT', dlg_btn(c, '导入'))
    for _ in range(90):
        time.sleep(2); c.pump()
        if not c.eval("!!document.querySelector('[role=dialog],[role=alertdialog]')"):
            break
    req, resp = capture(c, t0)
    print('URL REQ:', json.dumps(req, ensure_ascii=False, indent=1)[:2000])
    print('URL RESP:', json.dumps(resp, ensure_ascii=False))
    print('URL TOAST:', c.eval("Array.from(document.querySelectorAll('[data-sonner-toast]')).map(e=>(e.innerText||'').trim()).join(' | ')"))
    c.screenshot(os.path.join(OUT, 'r3-03-url-after.png'))
    out['url'] = {'req': req, 'resp': resp}
    r = s.post(f'{API}/audios', json={'page': 1, 'page_size': 10, 'keyword': 'int1479_url_test'}, timeout=120)
    items = ((r.json().get('data') or {}).get('items')) or []
    print('URL READBACK:', json.dumps([{'id': i.get('id'), 'name': i.get('name'), 'format': i.get('format'),
                                        'size': i.get('size'), 'type': i.get('audio_type'),
                                        'dur': i.get('duration')} for i in items], ensure_ascii=False))

    # 文件夹导入
    goto(c, '/audio-import', 4); wait_rows(c); time.sleep(2); c.pump()
    print('OPEN FOLDER', open_dialog(c, '批量从文件夹导入')); time.sleep(1.5)
    files = [os.path.join(WAVDIR, f'接线测试_INT1479R3_{i}.wav') for i in (1, 2, 3)]
    doc = c.send('DOM.getDocument', {'depth': 2})
    node = c.send('DOM.querySelector', {'nodeId': doc['root']['nodeId'],
                                        'selector': '[role=dialog] input[type=file]'})
    c.send('DOM.setFileInputFiles', {'files': files, 'nodeId': node['nodeId']})
    time.sleep(3)
    print('FOLDER TEXT:', dlg_text(c)[:600].replace('\n', ' | '))
    c.screenshot(os.path.join(OUT, 'r3-02-folder-filled.png'))
    t0 = len(c.events)
    print('FOLDER SUBMIT', dlg_btn(c, '开始导入'))
    for _ in range(90):
        time.sleep(2); c.pump()
        if not c.eval("!!document.querySelector('[role=dialog],[role=alertdialog]')"):
            break
    req, resp = capture(c, t0)
    print('FOLDER REQ:', json.dumps(req, ensure_ascii=False, indent=1)[:2500])
    print('FOLDER RESP:', json.dumps(resp, ensure_ascii=False))
    print('FOLDER TOAST:', c.eval("Array.from(document.querySelectorAll('[data-sonner-toast]')).map(e=>(e.innerText||'').trim()).join(' | ')"))
    c.screenshot(os.path.join(OUT, 'r3-02-folder-after.png'))
    out['folder'] = {'req': req, 'resp': resp}
    r = s.post(f'{API}/audios', json={'page': 1, 'page_size': 10, 'keyword': '接线测试_INT1479R3'}, timeout=120)
    items = ((r.json().get('data') or {}).get('items')) or []
    print('FOLDER READBACK:', json.dumps([{'id': i.get('id'), 'name': i.get('name'), 'size': i.get('size'),
                                           'created': i.get('created_at')} for i in items], ensure_ascii=False))
    with open(os.path.join(OUT, 'r3-url-folder.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
