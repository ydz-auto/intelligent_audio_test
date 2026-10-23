# -*- coding: utf-8 -*-
"""INT-1479 R3：格式转换真实提交 + 试听双模式真实请求。"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1479_r3_driver import connect, goto  # noqa: E402
from _int1479_api import API, H  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1479_audio')
NAME = '测试音频_01.wav'


def wait_rows(c, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if (c.eval("document.querySelectorAll('tbody tr').length") or 0) > 0:
            return True
        time.sleep(2)
    return False


def open_row_menu(c, name):
    return c.eval("""(function(n){const b=Array.from(document.querySelectorAll('button')).find(x=>(x.getAttribute('aria-label')||'')==='音频 '+n+' 的操作');
      if(!b)return 'NO_BTN';b.click();return 'OK';})(%s)""" % json.dumps(name))


def menu_click(c, label):
    return c.eval("""(function(l){const m=Array.from(document.querySelectorAll('[role=menuitem]')).find(e=>(e.innerText||'').trim()===l);
      if(!m)return 'NO_ITEM';m.click();return 'CLICKED';})(%s)""" % json.dumps(label))


def dlg_btn(c, label):
    return c.eval("""(function(l){const d=document.querySelector('[role=dialog],[role=alertdialog]');if(!d)return 'NO_DLG';
      const b=Array.from(d.querySelectorAll('button')).find(x=>(x.innerText||'').trim().startsWith(l));
      if(!b)return 'NO_BTN:'+l;b.click();return 'CLICKED:'+l;})(%s)""" % json.dumps(label))


def dlg_combo(c, aria):
    return c.eval("""(function(a){const d=document.querySelector('[role=dialog],[role=alertdialog]');
      const b=Array.from(d.querySelectorAll('[role=combobox]')).find(x=>(x.getAttribute('aria-label')||'')===a);
      if(!b)return 'NO_COMBO';b.click();return 'CLICKED';})(%s)""" % json.dumps(aria))


def options(c):
    return c.eval("Array.from(document.querySelectorAll('[role=option]')).map(e=>(e.innerText||'').trim())")


def pick_option(c, label):
    return c.eval("""(function(l){const o=Array.from(document.querySelectorAll('[role=option]')).find(e=>(e.innerText||'').trim()===l);
      if(!o)return 'NO_OPT';o.click();return 'PICKED';})(%s)""" % json.dumps(label))


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

    # ---------- 格式转换 ----------
    print('ROW', open_row_menu(c, NAME)); time.sleep(1)
    print('CONVERT', menu_click(c, '转换格式')); time.sleep(1.5)
    print('COMBO', dlg_combo(c, '目标格式')); time.sleep(1)
    print('FORMAT OPTIONS:', json.dumps(options(c), ensure_ascii=False))
    target = next((o for o in (options(c) or []) if 'MP3' in o.upper() or 'mp3' in o.lower()), None)
    print('PICK', target, pick_option(c, target) if target else 'NONE'); time.sleep(0.8)
    c.screenshot(os.path.join(OUT, 'r3-12-convert-mp3.png'))
    t0 = len(c.events)
    print('CONVERT SUBMIT', dlg_btn(c, '开始转换'))
    for _ in range(40):
        time.sleep(2); c.pump()
        dt = c.eval("(document.querySelector('[role=dialog]')||{}).innerText||''") or ''
        if not dt:
            break
    req, resp = capture(c, t0)
    print('CONVERT REQ:', json.dumps(req, ensure_ascii=False, indent=1)[:2000])
    print('CONVERT RESP:', json.dumps(resp, ensure_ascii=False))
    print('TOAST:', c.eval("Array.from(document.querySelectorAll('[data-sonner-toast]')).map(e=>(e.innerText||'').trim()).join(' | ')"))
    out['convert'] = {'req': req, 'resp': resp}
    c.screenshot(os.path.join(OUT, 'r3-12-convert-after.png'))
    time.sleep(1)
    r = s.post(f'{API}/audios', json={'page': 1, 'page_size': 10, 'keyword': '测试音频_01'}, timeout=120)
    items = ((r.json().get('data') or {}).get('items')) or []
    print('CONVERT READBACK:', json.dumps([{'id': i.get('id'), 'name': i.get('name'), 'format': i.get('format'),
                                           'size': i.get('size'), 'sample_rate': i.get('sample_rate'),
                                           'channels': i.get('channels')} for i in items], ensure_ascii=False))

    # ---------- 试听（浏览器 → 实验室） ----------
    goto(c, '/audio-import', 4); wait_rows(c); time.sleep(2); c.pump()
    print('ROW', open_row_menu(c, NAME)); time.sleep(1)
    print('PREVIEW', menu_click(c, '预览')); time.sleep(1.5)
    t0 = len(c.events)
    print('PLAY(frontend)', c.eval("""(function(){const b=document.querySelector('[role=dialog] [aria-label=播放]');if(!b)return 'NO';b.click();return 'CLICKED';})()"""))
    time.sleep(8); c.pump()
    req, resp = capture(c, t0)
    print('FRONTEND REQ:', json.dumps(req, ensure_ascii=False, indent=1)[:1500])
    print('FRONTEND RESP:', json.dumps(resp, ensure_ascii=False))
    print('AUDIO EL:', c.eval("""(function(){const a=document.querySelector('[role=dialog] audio');return a?{src:(a.src||'').slice(0,140),paused:a.paused,err:a.error?a.error.code:null,ready:a.readyState}:null;})()"""))
    c.screenshot(os.path.join(OUT, 'r3-10-preview-frontend.png'))
    # 停止
    c.eval("""(function(){const b=document.querySelector('[role=dialog] [aria-label=停止播放]');if(b)b.click();})()""")
    time.sleep(1)
    # 切换模式
    print('MODE COMBO', dlg_combo(c, '播放模式')); time.sleep(1)
    print('MODE OPTIONS:', json.dumps(options(c), ensure_ascii=False))
    print('PICK LAB:', pick_option(c, '实验室播放')); time.sleep(1.2)
    c.screenshot(os.path.join(OUT, 'r3-10-preview-lab-config.png'))
    t0 = len(c.events)
    print('PLAY(lab)', c.eval("""(function(){const b=document.querySelector('[role=dialog] [aria-label=播放]');if(!b)return 'NO';b.click();return 'CLICKED';})()"""))
    time.sleep(10); c.pump()
    req, resp = capture(c, t0)
    print('LAB REQ:', json.dumps(req, ensure_ascii=False, indent=1)[:2000])
    print('LAB RESP:', json.dumps(resp, ensure_ascii=False))
    print('LAB TOAST:', c.eval("Array.from(document.querySelectorAll('[data-sonner-toast]')).map(e=>(e.innerText||'').trim()).join(' | ')"))
    c.screenshot(os.path.join(OUT, 'r3-10-preview-lab.png'))
    out['preview'] = {'req': req, 'resp': resp}
    with open(os.path.join(OUT, 'r3-convert-preview.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
