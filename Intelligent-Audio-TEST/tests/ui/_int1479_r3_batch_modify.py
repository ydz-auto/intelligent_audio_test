# -*- coding: utf-8 -*-
"""INT-1479 R3：批量修改属性 + 批量删除（清理） + 深色截图。"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1479_r3_driver import connect, goto  # noqa: E402
from _int1479_api import API, H  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1479_audio')
MARK = '接线测试_INT1479R3_'
ALL_NAMES = ['接线测试_INT1479R3_1.wav', '接线测试_INT1479R3_2.wav', '接线测试_INT1479R3_3.wav']


def wait_rows(c, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if (c.eval("document.querySelectorAll('tbody tr').length") or 0) > 0:
            return True
        time.sleep(2)
    return False


def dump(c):
    return c.eval("""(function(){const d=document.querySelector('[role=dialog],[role=alertdialog]');if(!d)return null;
      return {text:(d.innerText||'').slice(0,900),
        items:Array.from(d.querySelectorAll('input,button,[role=combobox],[role=radio],[role=checkbox],[role=switch]'))
          .map((e,i)=>({i,tag:e.tagName.toLowerCase(),role:e.getAttribute('role')||'',aria:e.getAttribute('aria-label')||'',
            ph:e.getAttribute('placeholder')||'',text:(e.innerText||'').trim().slice(0,40),
            value:(e.value===undefined?'':String(e.value)).slice(0,60),checked:e.getAttribute('aria-checked')||e.checked||''}))};})()""")


def click_text(c, label, starts=False):
    return c.eval("""(function(l, s){const d=document.querySelector('[role=dialog],[role=alertdialog]')||document;
      const b=Array.from(d.querySelectorAll('button')).find(x=>s?(x.innerText||'').trim().startsWith(l):(x.innerText||'').trim()===l);
      if(!b)return 'NO_BTN:'+l;b.click();return 'CLICKED';})(%s, %s)""" % (json.dumps(label), 'true' if starts else 'false'))


def capture(c, t0):
    c.pump()
    req, resp = [], []
    for e in c.events[t0:]:
        if e['method'] == 'Network.requestWillBeSent':
            r = e['params']['request']
            if '/api/' in r['url'] and 'audios' in r['url']:
                req.append({'m': r['method'], 'u': r['url'].split('?')[0], 'body': (r.get('postData') or '')[:400]})
        elif e['method'] == 'Network.responseReceived':
            r = e['params']['response']
            if '/api/' in r['url'] and 'audios' in r['url']:
                resp.append({'s': r['status'], 'u': r['url'].split('?')[0]})
    return req, resp


def select_names(c, names):
    return c.eval("""(function(ns){let n=0;for(const x of ns){const el=document.querySelector('[role=checkbox][aria-label="选择音频 '+x+'"]');
      if(el){el.click();n++;}}return n;})(%s)""" % json.dumps(names))


def run(theme, c, out):
    c.eval("localStorage.setItem('iatp:theme:v1:mode', %r)" % theme)
    goto(c, '/audio-import', 6); wait_rows(c); time.sleep(2); c.pump()
    c.screenshot(os.path.join(OUT, f'r3-{theme}-00-list.png'))
    if theme != 'light':
        return
    # 批量修改属性
    print('SELECT', select_names(c, ALL_NAMES)); time.sleep(0.8)
    c.eval("""Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='更多批量操作').click(), 'ok'""")
    time.sleep(1)
    c.eval("""(function(){const m=Array.from(document.querySelectorAll('[role=menuitem]')).find(e=>(e.innerText||'').trim()==='批量修改属性');if(m)m.click();})()""")
    time.sleep(1.5)
    print('MODIFY DUMP:', json.dumps(dump(c), ensure_ascii=False, indent=1))
    c.screenshot(os.path.join(OUT, 'r3-09-batch-modify.png'))
    # 选「噪声」单选并提交
    print('PICK 噪声:', c.eval("""(function(){const d=document.querySelector('[role=dialog]');const r=Array.from(d.querySelectorAll('[role=radio],button')).find(x=>(x.innerText||'').trim()==='噪声');if(!r)return 'NO';r.click();return 'OK';})()"""))
    time.sleep(0.8)
    t0 = len(c.events)
    print('MODIFY SUBMIT:', click_text(c, '确认执行'))
    time.sleep(5)
    req, resp = capture(c, t0)
    print('MODIFY REQ:', json.dumps(req, ensure_ascii=False, indent=1))
    print('MODIFY RESP:', json.dumps(resp, ensure_ascii=False))
    print('MODIFY TOAST:', c.eval("Array.from(document.querySelectorAll('[data-sonner-toast]')).map(e=>(e.innerText||'').trim()).join(' | ')"))
    c.screenshot(os.path.join(OUT, 'r3-09-batch-modify-after.png'))
    out['modify'] = {'req': req, 'resp': resp}


if __name__ == '__main__':
    c = connect()
    out = {}
    for theme in ('light',):
        run(theme, c, out)
    s = requests.Session(); s.headers.update(H())
    r = s.post(f'{API}/audios', json={'page': 1, 'page_size': 10, 'keyword': MARK}, timeout=120)
    items = ((r.json().get('data') or {}).get('items')) or []
    print('READBACK MODIFY:', json.dumps([{'id': i.get('id'), 'name': i.get('name'), 'type': i.get('audio_type')} for i in items], ensure_ascii=False))
    with open(os.path.join(OUT, 'r3-modify-result.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
