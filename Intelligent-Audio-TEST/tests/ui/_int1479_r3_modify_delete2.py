# -*- coding: utf-8 -*-
"""INT-1479 R3：修改属性（正确输入框）+ 批量删除清理。"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1479_r3_driver import connect, goto  # noqa: E402
from _int1479_api import API, H  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1479_audio')
TEST_NAMES = ['测试音频_01.wav', '测试音频_02.wav', '测试音频_03.wav',
              '接线测试_INT1479R3_1.wav', '接线测试_INT1479R3_2.wav', '接线测试_INT1479R3_3.wav',
              'url_int1479_url_test.wav']
DESC = '接线测试INT1479批量修改属性'


def wait_rows(c, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if (c.eval("document.querySelectorAll('tbody tr').length") or 0) > 0:
            return True
        time.sleep(2)
    return False


def dlg_click(c, label):
    return c.eval("""(function(l){const d=document.querySelector('[role=dialog],[role=alertdialog]');if(!d)return 'NO_DLG';
      const b=Array.from(d.querySelectorAll('button')).find(x=>(x.innerText||'').trim()===l);
      if(!b)return 'NO_BTN:'+l;b.click();return 'CLICKED';})(%s)""" % json.dumps(label))


def set_value_input(c, value):
    return c.eval("""(function(v){const d=document.querySelector('[role=dialog],[role=alertdialog]');if(!d)return 'NO_DLG';
      const el=Array.from(d.querySelectorAll('input,textarea')).find(x=>(x.getAttribute('placeholder')||'').includes('批量设置到选中音频'));
      if(!el)return 'NO_INPUT';
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(el,v);
      el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));
      return 'SET:'+el.value;})(%s)""" % json.dumps(value))


def select_names(c, names):
    return c.eval("""(function(ns){let n=0;for(const x of ns){const el=document.querySelector('[role=checkbox][aria-label="选择音频 '+x+'"]');
      if(el){el.click();n++;}}return n;})(%s)""" % json.dumps(names))


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

    # 修改属性
    print('SELECT', select_names(c, TEST_NAMES[:3])); time.sleep(0.8)
    c.eval("""Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='更多批量操作').click(), 'ok'""")
    time.sleep(1)
    c.eval("""(function(){const m=Array.from(document.querySelectorAll('[role=menuitem]')).find(e=>(e.innerText||'').trim()==='批量修改属性');if(m)m.click();})()""")
    time.sleep(1.5)
    print('INPUT:', set_value_input(c, DESC)); time.sleep(0.5)
    c.screenshot(os.path.join(OUT, 'r3-09-batch-modify-filled.png'))
    t0 = len(c.events)
    print('SUBMIT:', dlg_click(c, '确认执行'))
    time.sleep(6)
    req, resp = capture(c, t0)
    print('REQ:', json.dumps(req, ensure_ascii=False, indent=1))
    print('RESP:', json.dumps(resp, ensure_ascii=False))
    print('TOAST:', c.eval("Array.from(document.querySelectorAll('[data-sonner-toast]')).map(e=>(e.innerText||'').trim()).join(' | ')"))
    out['modify'] = {'req': req, 'resp': resp}
    r = s.post(f'{API}/audios', json={'page': 1, 'page_size': 10, 'keyword': 'INT1479'}, timeout=120)
    items = ((r.json().get('data') or {}).get('items')) or []
    print('READBACK MODIFY:', json.dumps([{'id': i.get('id'), 'name': i.get('name'), 'desc': i.get('description'),
                                           'tags': i.get('tags')} for i in items], ensure_ascii=False))

    # 批量删除
    goto(c, '/audio-import', 4); wait_rows(c); time.sleep(2); c.pump()
    print('SELECT ALL', select_names(c, TEST_NAMES)); time.sleep(0.8)
    t0 = len(c.events)
    print('DELETE CLICK:', c.eval("""(function(){const b=Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='批量删除');if(!b)return 'NO';b.click();return 'CLICKED';})()"""))
    time.sleep(1.5)
    print('CONFIRM DIALOG:', (c.eval("(document.querySelector('[role=dialog],[role=alertdialog]')||{}).innerText||''") or '')[:300].replace('\n', ' | '))
    c.screenshot(os.path.join(OUT, 'r3-r3-batch-delete-confirm.png'))
    print('CONFIRM:', dlg_click(c, '批量删除'))
    time.sleep(8)
    req, resp = capture(c, t0)
    print('DELETE REQ:', json.dumps(req, ensure_ascii=False, indent=1))
    print('DELETE RESP:', json.dumps(resp, ensure_ascii=False))
    print('DELETE TOAST:', c.eval("Array.from(document.querySelectorAll('[data-sonner-toast]')).map(e=>(e.innerText||'').trim()).join(' | ')"))
    c.screenshot(os.path.join(OUT, 'r3-r3-batch-delete-after.png'))
    out['delete'] = {'req': req, 'resp': resp}

    r = s.post(f'{API}/audios', json={'page': 1, 'page_size': 20, 'keyword': 'INT1479'}, timeout=120)
    j = r.json()
    items = ((j.get('data') or {}).get('items')) or []
    print('READBACK AFTER DELETE:', r.status_code, 'total=', (j.get('data') or {}).get('total'),
          json.dumps([{'id': i.get('id'), 'name': i.get('name')} for i in items], ensure_ascii=False))
    with open(os.path.join(OUT, 'r3-modify-delete.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
