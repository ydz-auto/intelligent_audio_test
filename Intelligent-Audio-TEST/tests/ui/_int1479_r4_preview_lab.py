# -*- coding: utf-8 -*-
"""INT-1479 R4：试听弹窗实验室播放补测（真实 POST /audios/{id}/preview）。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _int1479_r4_lib as L  # noqa: E402

NAME = '接线测试_INT1479R4_3.wav'
REPORT = {}


def dialog_text(c):
    return c.eval("(document.querySelector('[role=dialog],[role=alertdialog]')||{}).innerText||''") or ''


def open_preview(c):
    r = c.eval("""(function(name){
      const b=Array.from(document.querySelectorAll('button')).find(x=>(x.getAttribute('aria-label')||'').includes('音频 '+name+' 的操作'));
      if(!b) return 'NO_BTN'; b.click(); return 'OK';})(%s)""" % json.dumps(NAME))
    time.sleep(1)
    r2 = c.eval("""(function(){const nodes=Array.from(document.querySelectorAll('[role=menuitem]'));
      const el=nodes.find(n=>(n.innerText||'').trim().includes('预览'));
      if(!el) return 'NO_ITEM'; el.click(); return 'CLICKED';})()""")
    time.sleep(3)
    return r, r2


def select_mode(c, label):
    c.eval("""(function(){const t=document.querySelector('[aria-label=播放模式]');if(t)t.click();})()""")
    time.sleep(0.8)
    r = c.eval("""(function(label){const opts=Array.from(document.querySelectorAll('[role=option]'));
      const el=opts.find(o=>(o.innerText||'').trim()===label);
      if(!el) return 'NO_OPTION'; el.click(); return 'CLICKED';})(%s)""" % json.dumps(label))
    time.sleep(1.2)
    return r


def click_play(c):
    return c.eval("""(function(){const bs=Array.from(document.querySelectorAll('[role=dialog] button'));
      const b=bs.find(x=>['播放','停止播放'].includes(x.getAttribute('aria-label')));
      if(!b) return 'NO_PLAY:'+bs.map(x=>x.getAttribute('aria-label')||(x.innerText||'').trim()).join('|');
      if(b.disabled) return 'DISABLED'; b.click(); return 'CLICKED:'+b.getAttribute('aria-label');})()""")


def main():
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

    print('OPEN', open_preview(c), flush=True)
    print('MODE', select_mode(c, '实验室播放'), flush=True)
    dt = dialog_text(c)
    REPORT['dialog'] = dt
    print('DIALOG', dt[:400].replace('\n', ' | '), flush=True)
    t = len(c.events)
    print('PLAY', click_play(c), flush=True)
    end = time.time() + 40
    reqs, resps = [], []
    while time.time() < end:
        c.pump()
        reqs, resps = L.net_since(c, t)
        if any('/preview' in r['u'] for r in reqs) and any('/preview' in r['u'] for r in resps):
            break
        time.sleep(2)
    REPORT['play'] = {'reqs': reqs, 'resps': resps}
    print('PLAY_NET', json.dumps({'reqs': reqs, 'resps': resps}, ensure_ascii=False)[:1200], flush=True)
    print('AFTER_TEXT', dialog_text(c)[-260:].replace('\n', ' | '), flush=True)
    L.shot(c, 'r4-17-preview-lab-play-result')

    with open(os.path.join(L.OUT, 'r4_preview_lab_report.json'), 'w', encoding='utf-8') as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
