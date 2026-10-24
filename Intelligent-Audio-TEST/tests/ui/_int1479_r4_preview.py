# -*- coding: utf-8 -*-
"""INT-1479 R4：试听弹窗复走（INT-1512 修复后）——双模式、真实设备、真实流/预览请求。"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _int1479_r4_lib as L  # noqa: E402
from _int1479_api import API, H  # noqa: E402

NAME = '接线测试_INT1479R4_3.wav'
REPORT = {}


def dialog_text(c):
    return c.eval("(document.querySelector('[role=dialog],[role=alertdialog]')||{}).innerText||''") or ''


def open_menu(c, name):
    return c.eval("""(function(name){
      const b=Array.from(document.querySelectorAll('button')).find(x=>(x.getAttribute('aria-label')||'').includes('音频 '+name+' 的操作'));
      if(!b) return 'NO_BTN'; b.click(); return 'OK';})(%s)""" % json.dumps(name))


def menu_item(c, label):
    return c.eval("""(function(label){const nodes=Array.from(document.querySelectorAll('[role=menuitem]'));
      const el=nodes.find(n=>(n.innerText||'').trim().includes(label));
      if(!el) return 'NOT_FOUND:'+label; el.click(); return 'CLICKED:'+label;})(%s)""" % json.dumps(label))


def close(c):
    c.eval("""(function(){const d=document.querySelector('[role=dialog],[role=alertdialog]');if(!d)return;
      const b=d.querySelector('button[aria-label=Close]')||Array.from(d.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='取消');
      if(b)b.click();})()""")
    time.sleep(1)


def select_mode(c, label):
    r1 = c.eval("""(function(){const t=document.querySelector('[aria-label=播放模式]');
      if(!t) return 'NO_TRIGGER'; t.click(); return 'TRIGGER';})()""")
    time.sleep(0.8)
    r2 = c.eval("""(function(label){const opts=Array.from(document.querySelectorAll('[role=option]'));
      const el=opts.find(o=>(o.innerText||'').trim()===label);
      if(!el) return 'NO_OPTION:'+opts.map(o=>o.innerText.trim()).join('|'); el.click(); return 'CLICKED';})(%s)""" % json.dumps(label))
    time.sleep(1)
    return r1, r2


def device_options(c):
    c.eval("""(function(){const t=document.querySelector('#preview-playback-device');if(t){t.click();return 'OPEN';}return 'NO';})()""")
    time.sleep(1)
    opts = c.eval("Array.from(document.querySelectorAll('[role=option]')).map(o=>(o.innerText||'').trim())")
    c.eval("document.body.click()")
    time.sleep(0.5)
    return opts or []


def click_play(c):
    return c.eval("""(function(){const b=document.querySelector('[role=dialog] button[aria-label=播放]');
      if(!b) return 'NO_PLAY'; if(b.disabled) return 'DISABLED'; b.click(); return 'CLICKED';})()""")


def api_devices():
    s = requests.Session(); s.headers.update(H())
    r = s.get(f'{API}/playback-devices', timeout=90)
    j = r.json()
    d = j.get('data') or j
    items = d.get('items') if isinstance(d, dict) else d
    return r.status_code, items or []


def main():
    st, devices = api_devices()
    REPORT['api_devices'] = {'status': st, 'count': len(devices),
                             'names': [d.get('name') for d in devices][:15]}
    print('API_DEVICES', json.dumps(REPORT['api_devices'], ensure_ascii=False), flush=True)

    c = L.connect()
    L.nav(c, '/audio-import', 8)
    ok = L.wait_ready(c, 240)
    print('READY', ok, flush=True)
    if not ok:
        c.send('Page.reload'); time.sleep(10); ok = L.wait_ready(c, 240)
        print('READY2', ok, flush=True)
    if not ok:
        print('ABORT', flush=True); return
    L.set_theme(c, 'light')

    t = len(c.events)
    print('MENU', open_menu(c, NAME), flush=True)
    time.sleep(1)
    print('ITEM', menu_item(c, '预览'), flush=True)
    time.sleep(3)
    c.pump()
    dt = dialog_text(c)
    REPORT['dialog_light'] = dt
    print('DIALOG', dt[:600].replace('\n', ' | '), flush=True)
    L.shot(c, 'r4-10-preview-light-frontend')
    reqs, resps = L.net_since(c, t)
    REPORT['open_net'] = {'reqs': reqs, 'resps': resps}
    print('OPEN_NET', json.dumps({'reqs': reqs, 'resps': resps}, ensure_ascii=False)[:1200], flush=True)

    # 浏览器播放
    t = len(c.events)
    print('PLAY', click_play(c), flush=True)
    time.sleep(8)
    c.pump()
    reqs, resps = L.net_since(c, t)
    REPORT['frontend_play'] = {'reqs': reqs, 'resps': resps}
    print('PLAY_NET', json.dumps({'reqs': reqs, 'resps': resps}, ensure_ascii=False)[:1200], flush=True)
    print('AUDIO', c.eval("""(function(){const a=document.querySelector('[role=dialog] audio');
      if(!a) return 'NO_AUDIO'; return {src:(a.src||'').slice(0,120), readyState:a.readyState,
        error:a.error?a.error.code:null, paused:a.paused, duration:a.duration};})()"""), flush=True)
    L.shot(c, 'r4-11-preview-light-playing')

    # 实验室模式
    print('MODE', select_mode(c, '实验室播放'), flush=True)
    time.sleep(2)
    dt = dialog_text(c)
    REPORT['dialog_lab'] = dt
    print('DIALOG_LAB', dt[:600].replace('\n', ' | '), flush=True)
    L.shot(c, 'r4-12-preview-light-lab')
    opts = device_options(c)
    REPORT['device_options'] = opts
    print('DEVICE_OPTIONS', json.dumps(opts, ensure_ascii=False)[:800], flush=True)

    t = len(c.events)
    print('PLAY_LAB', click_play(c), flush=True)
    time.sleep(10)
    c.pump()
    reqs, resps = L.net_since(c, t)
    REPORT['lab_play'] = {'reqs': reqs, 'resps': resps}
    print('LAB_NET', json.dumps({'reqs': reqs, 'resps': resps}, ensure_ascii=False)[:1500], flush=True)
    print('LAB_TEXT', dialog_text(c)[-300:].replace('\n', ' | '), flush=True)
    L.shot(c, 'r4-13-preview-light-lab-playing')

    # 关闭重开是否复位
    close(c)
    time.sleep(1)
    print('REOPEN', open_menu(c, NAME), flush=True)
    time.sleep(1)
    menu_item(c, '预览')
    time.sleep(3)
    print('REOPEN_DIALOG', dialog_text(c)[:400].replace('\n', ' | '), flush=True)
    REPORT['reopen'] = dialog_text(c)
    L.shot(c, 'r4-14-preview-light-reopen')

    # 深色
    L.set_theme(c, 'dark')
    time.sleep(1)
    L.shot(c, 'r4-15-preview-dark-frontend')
    select_mode(c, '实验室播放')
    time.sleep(1.2)
    L.shot(c, 'r4-16-preview-dark-lab')
    close(c)
    L.set_theme(c, 'light')

    with open(os.path.join(L.OUT, 'r4_preview_report.json'), 'w', encoding='utf-8') as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
