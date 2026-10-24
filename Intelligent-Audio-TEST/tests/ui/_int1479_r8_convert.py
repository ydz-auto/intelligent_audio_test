# -*- coding: utf-8 -*-
"""INT-1479 R8 · A：格式转换（INT-1581 修复复走）。

浅色：弹窗新注记 → 目标 MP3 / 48 kHz / 单声道 / 320 kbps → 提交 → 请求体 + GET 回读；
深色：同弹窗 + WAV 无损分支（24 bit）截图；浅/深各一图。
"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _int1479_r4_lib as L  # noqa: E402
import _int1479_api as A  # noqa: E402

OUT = L.OUT
NAME = '接线测试_INT1479_转换_A.wav'


def rows(c):
    return c.eval("document.querySelectorAll('tbody tr').length") or 0


def wait_rows(c, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        if rows(c):
            return True
        time.sleep(2)
    return False


def search(c, kw):
    return c.eval("""(function(k){
      const i=document.querySelector("input[aria-label='搜索音频']");
      if(!i) return 'NO_INPUT';
      const setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
      setter.call(i,k); i.dispatchEvent(new Event('input',{bubbles:true}));
      return 'SET';})(%s)""" % json.dumps(kw))


def open_menu(c, name):
    return c.eval("""(function(n){const b=Array.from(document.querySelectorAll('button'))
      .find(x=>(x.getAttribute('aria-label')||'')==='音频 '+n+' 的操作');
      if(!b)return 'NO_BTN';b.click();return 'OK';})(%s)""" % json.dumps(name))


def menu(c, label):
    return c.eval("""(function(l){const m=Array.from(document.querySelectorAll('[role=menuitem]'))
      .find(e=>(e.innerText||'').trim()===l);if(!m)return 'NO_ITEM';m.click();return 'CLICKED';})(%s)"""
                  % json.dumps(label))


def dialog_text(c):
    return c.eval("(function(){const d=Array.from(document.querySelectorAll('[role=dialog]')).pop();"
                  "return d?(d.innerText||''):'';})()") or ''


def combo(c, aria):
    return c.eval("""(function(a){const d=Array.from(document.querySelectorAll('[role=dialog]')).pop();
      const b=Array.from(d.querySelectorAll('[role=combobox],[aria-label]')).find(x=>(x.getAttribute('aria-label')||'')===a);
      if(!b)return 'NO_COMBO';b.click();return 'CLICKED';})(%s)""" % json.dumps(aria))


def options(c):
    return c.eval("Array.from(document.querySelectorAll('[role=option]')).map(e=>(e.innerText||'').trim())")


def pick(c, aria, label):
    combo(c, aria)
    time.sleep(0.6)
    r = c.eval("""(function(l){const o=Array.from(document.querySelectorAll('[role=option]'))
      .find(e=>(e.innerText||'').trim()===l);if(!o)return 'NO_OPT:'+l;o.click();return 'PICKED';})(%s)"""
               % json.dumps(label))
    time.sleep(0.5)
    return r


def submit(c):
    return c.eval("""(function(){const d=Array.from(document.querySelectorAll('[role=dialog]')).pop();
      if(!d)return 'NO_DLG';
      const b=Array.from(d.querySelectorAll('button')).find(x=>(x.innerText||'').trim().startsWith('开始转换'));
      if(!b)return 'NO_BTN';b.click();return 'CLICKED';})()""")


def net_since(c, i):
    reqs, resps = [], []
    for e in c.events[i:]:
        if e['method'] == 'Network.requestWillBeSent':
            r = e['params']['request']
            if '/api/' in r['url']:
                reqs.append({'m': r['method'], 'u': r['url'].split('?')[0],
                             'body': (r.get('postData') or '')[:600]})
        elif e['method'] == 'Network.responseReceived':
            r = e['params']['response']
            if '/api/' in r['url']:
                resps.append({'status': r['status'], 'u': r['url'].split('?')[0]})
    return reqs, resps


def api_get(aid):
    t = A.token()
    r = requests.get('%s/audios/%s' % (A.API, aid), headers={'Authorization': 'Bearer %s' % t}, timeout=120)
    return r.status_code, ((r.json() or {}).get('data') or {})


def open_page(c, theme):
    L.nav(c, '/audio-import', 6)
    L.set_theme(c, theme)
    L.nav(c, '/audio-import', 8)   # 同源重载，主题才落到 html 上
    ok = L.wait_ready(c, 240)
    time.sleep(1.5)
    search(c, '接线测试_INT1479')
    time.sleep(2.5)
    return ok


def main():
    os.makedirs(OUT, exist_ok=True)
    aid = int(sys.argv[1]) if len(sys.argv) > 1 else 2485
    c = L.connect()
    out = {}

    # ---------- 浅色：MP3 / 48 kHz / 单声道 / 320 kbps ----------
    print('READY', open_page(c, 'light'), flush=True)
    print('ROWS', rows(c), flush=True)
    print('MENU', open_menu(c, NAME)); time.sleep(1.2)
    print('CONVERT', menu(c, '转换格式')); time.sleep(2)
    txt = dialog_text(c)
    out['dialog_text'] = txt.replace('\n', ' | ')[:900]
    out['new_note_present'] = '采样率与声道数对所有目标格式生效' in txt
    out['old_note_absent'] = '仅接收' not in txt
    print('NOTE new=%s old_absent=%s' % (out['new_note_present'], out['old_note_absent']), flush=True)
    errs = []
    for aria, label in (('目标格式', 'MP3'), ('目标采样率', '48 kHz'), ('声道数', '单声道'),
                        ('转换参数', '320 kbps')):
        r = pick(c, aria, label)
        print('PICK', aria, label, r, flush=True)
        if r != 'PICKED':
            errs.append('%s=%s' % (aria, r))
    print('PARAM OPTS', json.dumps(options(c), ensure_ascii=False), flush=True)
    time.sleep(0.5)
    out['l shot'] = L.shot(c, 'r8-a1-convert-mp3-light')
    t0 = len(c.events)
    print('SUBMIT', submit(c), flush=True)
    end = time.time() + 180
    while time.time() < end:
        time.sleep(2)
        c.pump()
        if not dialog_text(c):
            break
    time.sleep(2)
    c.pump()
    reqs, resps = net_since(c, t0)
    conv_req = [r for r in reqs if r['u'].endswith('/convert')]
    conv_resp = [r for r in resps if r['u'].endswith('/convert')]
    out['convert_requests'] = conv_req
    out['convert_responses'] = conv_resp
    out['toast'] = c.eval("Array.from(document.querySelectorAll('[data-sonner-toast]')).map(e=>(e.innerText||'').trim())") or []
    print('CONVERT REQ', json.dumps(conv_req, ensure_ascii=False), flush=True)
    print('CONVERT RESP', json.dumps(conv_resp, ensure_ascii=False), flush=True)
    print('TOAST', json.dumps(out['toast'], ensure_ascii=False), flush=True)
    st, info = api_get(aid)
    out['readback'] = {k: info.get(k) for k in
                       ('id', 'name', 'format', 'size', 'sample_rate', 'channels', 'bitrate')}
    out['readback_status'] = st
    print('READBACK', json.dumps(out['readback'], ensure_ascii=False), flush=True)
    out['after shot'] = L.shot(c, 'r8-a2-convert-mp3-after-light')

    # ---------- 深色：无损分支（WAV / 24 bit）弹窗 ----------
    print('DARK READY', open_page(c, 'dark'), flush=True)
    print('DARK THEME', c.eval("document.documentElement.classList.contains('dark')"), flush=True)
    print('MENU', open_menu(c, NAME)); time.sleep(1.2)
    print('CONVERT', menu(c, '转换格式')); time.sleep(2)
    for aria, label in (('目标格式', 'WAV'), ('目标采样率', '44.1 kHz'), ('声道数', '双声道'),
                        ('转换参数', '24 bit')):
        print('PICK', aria, label, pick(c, aria, label), flush=True)
    time.sleep(0.5)
    out['dialog_text_dark'] = dialog_text(c).replace('\n', ' | ')[:900]
    out['dark shot'] = L.shot(c, 'r8-a3-convert-wav24-dark')
    print('CANCEL', c.eval("""(function(){const d=Array.from(document.querySelectorAll('[role=dialog]')).pop();
      const b=Array.from(d.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='取消');
      if(!b)return 'NO';b.click();return 'CLICKED';})()"""), flush=True)

    out['pick_errors'] = errs
    with open(os.path.join(OUT, 'r8_convert.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
