# -*- coding: utf-8 -*-
"""INT-1479 R3：文件夹导入（构造真实 File 对象喂 webkitdirectory 输入）真实提交。"""
import base64
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
FILES = [f'接线测试_INT1479R3_{i}.wav' for i in (1, 2, 3)]


def wait_rows(c, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if (c.eval("document.querySelectorAll('tbody tr').length") or 0) > 0:
            return True
        time.sleep(2)
    return False


def dlg_text(c):
    return c.eval("(document.querySelector('[role=dialog],[role=alertdialog]')||{}).innerText||''") or ''


def capture(c, t0):
    c.pump()
    req, resp = [], []
    for e in c.events[t0:]:
        if e['method'] == 'Network.requestWillBeSent':
            r = e['params']['request']
            if '/api/' in r['url']:
                req.append({'m': r['method'], 'u': r['url'].split('?')[0], 'body': (r.get('postData') or '')[:300]})
        elif e['method'] == 'Network.responseReceived':
            r = e['params']['response']
            if '/api/' in r['url']:
                resp.append({'s': r['status'], 'u': r['url'].split('?')[0]})
    return req, resp


if __name__ == '__main__':
    c = connect(); s = requests.Session(); s.headers.update(H())
    goto(c, '/audio-import', 5); wait_rows(c); time.sleep(2); c.pump()
    print('OPEN:', c.eval("""(function(){const b=Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='批量从文件夹导入');if(!b)return 'NO';b.click();return 'OK';})()"""))
    time.sleep(1.5)
    c.eval("window.__dt = new DataTransfer(); 'ok'")
    for name in FILES:
        path = os.path.join(WAVDIR, name)
        b64 = base64.b64encode(open(path, 'rb').read()).decode()
        r = c.eval("""(function(b64, name){
          const bin = atob(b64); const arr = new Uint8Array(bin.length);
          for (let i=0;i<bin.length;i++) arr[i]=bin.charCodeAt(i);
          window.__dt.items.add(new File([arr], name, {type:'audio/wav'}));
          return window.__dt.items.length;
        })(%s, %s)""" % (json.dumps(b64), json.dumps(name)))
        print('ADD', name, r)
    print('ASSIGN:', c.eval("""(function(){
      const inp = document.querySelector('[role=dialog] input[type=file]'); if(!inp) return 'NO_INPUT';
      inp.files = window.__dt.files;
      inp.dispatchEvent(new Event('change', {bubbles:true}));
      return 'FILES:' + inp.files.length;
    })()"""))
    time.sleep(3)
    print('TEXT:', dlg_text(c)[:600].replace('\n', ' | '))
    c.screenshot(os.path.join(OUT, 'r3-02-folder-filled.png'))
    t0 = len(c.events)
    print('SUBMIT:', c.eval("""(function(){const d=document.querySelector('[role=dialog]');if(!d)return 'NO_DLG';
      const b=Array.from(d.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='开始导入');
      if(!b)return 'NO_BTN';b.click();return 'CLICKED';})()"""))
    for _ in range(90):
        time.sleep(2); c.pump()
        if not c.eval("!!document.querySelector('[role=dialog],[role=alertdialog]')"):
            break
    req, resp = capture(c, t0)
    print('REQ:', json.dumps(req, ensure_ascii=False, indent=1)[:3000])
    print('RESP:', json.dumps(resp, ensure_ascii=False))
    print('TOAST:', c.eval("Array.from(document.querySelectorAll('[data-sonner-toast]')).map(e=>(e.innerText||'').trim()).join(' | ')"))
    print('TEXT AFTER:', dlg_text(c)[:300].replace('\n', ' | '))
    c.screenshot(os.path.join(OUT, 'r3-02-folder-after.png'))
    r = s.post(f'{API}/audios', json={'page': 1, 'page_size': 10, 'keyword': '接线测试_INT1479R3'}, timeout=120)
    items = ((r.json().get('data') or {}).get('items')) or []
    print('READBACK:', json.dumps([{'id': i.get('id'), 'name': i.get('name'), 'size': i.get('size'),
                                    'created': i.get('created_at')} for i in items], ensure_ascii=False))
    with open(os.path.join(OUT, 'r3-folder-result.json'), 'w', encoding='utf-8') as f:
        json.dump({'req': req, 'resp': resp}, f, ensure_ascii=False, indent=1)
