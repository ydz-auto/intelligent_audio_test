# -*- coding: utf-8 -*-
"""INT-1479 R4：批量复制 真实提交 + 回读 + 深色截图（移动窗一并补拍）。"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1479_r4_lib import (OUT, click, connect, nav, net_since, set_theme, shot,
                             text, wait_ready)  # noqa: E402
from _int1479_api import API, H  # noqa: E402

NAMES = ['接线测试_INT1479R4_2.wav', '接线测试_INT1479R4_3.wav']
REPORT = {}


def api_list(keyword):
    s = requests.Session(); s.headers.update(H())
    for _ in range(5):
        try:
            r = s.post(f'{API}/audios', json={'page': 1, 'page_size': 30, 'keyword': keyword}, timeout=120)
            if r.status_code == 200 and isinstance(r.json().get('data'), dict):
                return r.json()['data']['items']
        except Exception:
            pass
        time.sleep(3)
    return []


def dialog_text(c):
    return c.eval("(document.querySelector('[role=dialog],[role=alertdialog]')||{}).innerText||''") or ''


def close_dialog(c):
    c.eval("""(function(){const d=document.querySelector('[role=dialog],[role=alertdialog]');if(!d)return;
      const b=Array.from(d.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='取消');
      if(b)b.click();})()""")
    time.sleep(0.8)


def select_rows(c, names):
    return c.eval("""
      (function(names){const hit=[];for(const n of names){
        const el=document.querySelector('[role=checkbox][aria-label="选择音频 '+n+'"]');
        if(el){el.click(); hit.push(n);}}return hit;})(%s)""" % json.dumps(names))


def open_bulk(c, item_label):
    r1 = click(c, '更多批量操作')
    time.sleep(0.9)
    r2 = c.eval("""(function(label){
      const nodes=Array.from(document.querySelectorAll('[role=menuitem]'));
      const el=nodes.find(n=>(n.innerText||'').trim()===label);
      if(!el) return 'NOT_FOUND:'+label; el.click(); return 'CLICKED:'+label;})(%s)""" % json.dumps(item_label))
    time.sleep(1.2)
    return r1, r2


def choose_folder(c, value):
    r = c.eval("""(function(){const d=document.querySelector('[role=dialog],[role=alertdialog]');if(!d)return 'NO_DIALOG';
      const t=d.querySelector('#batch-folder-target')||d.querySelector('[role=combobox]');
      if(!t) return 'NO_TRIGGER'; t.click(); return 'TRIGGER_CLICKED';})()""")
    time.sleep(0.9)
    r2 = c.eval("""(function(v){const opts=Array.from(document.querySelectorAll('[role=option]'));
      const el=opts.find(o=>(o.innerText||'').trim()===v);
      if(!el) return 'NO_OPTION:'+opts.map(o=>o.innerText.trim()).join('|');
      el.click(); return 'OPTION_CLICKED:'+v;})(%s)""" % json.dumps(value))
    time.sleep(0.6)
    return r, r2


def confirm(c):
    return c.eval("""(function(){const d=document.querySelector('[role=dialog],[role=alertdialog]');if(!d)return 'NO_DIALOG';
      const b=Array.from(d.querySelectorAll('button')).find(x=>(x.innerText||'').trim().startsWith('确认执行'));
      if(!b) return 'NO_BTN'; if(b.disabled) return 'DISABLED'; b.click(); return 'CLICKED';})()""")


def main():
    before = api_list('接线测试_INT1479R4')
    print('BEFORE', json.dumps([{'id': i['id'], 'name': i['name'], 'file_path': i.get('file_path')}
                                for i in before], ensure_ascii=False), flush=True)

    c = connect()
    nav(c, '/audio-import', 8)
    ok = wait_ready(c, 240)
    print('READY', ok, flush=True)
    if not ok:
        c.send('Page.reload'); time.sleep(10); ok = wait_ready(c, 240)
        print('READY2', ok, flush=True)
    if not ok:
        print('ABORT', flush=True); return
    set_theme(c, 'light')

    for attempt in range(4):
        print('SELECT', select_rows(c, NAMES), flush=True)
        time.sleep(2)
        tail = text(c)
        if '已选' in tail and '批量设置标签' in tail:
            print('SELECT_OK', flush=True)
            break
        print('SELECT_RETRY', attempt, tail[-160:].replace('\n', ' | '), flush=True)
    print('OPEN_BULK', open_bulk(c, '批量复制'), flush=True)
    print('COPY_DLG', dialog_text(c)[:300].replace('\n', ' | '), flush=True)
    shot(c, 'r4-05-batch-copy-light')
    print('FOLDER', choose_folder(c, 'test_data/prompt'), flush=True)
    print('COPY_DLG2', dialog_text(c)[:300].replace('\n', ' | '), flush=True)
    shot(c, 'r4-06-batch-copy-folder-selected')
    t = len(c.events)
    print('CONFIRM', confirm(c), flush=True)
    end = time.time() + 60
    reqs, resps = [], []
    while time.time() < end:
        c.pump()
        reqs, resps = net_since(c, t)
        if any(r['u'].endswith('/audios/batch-action') for r in resps):
            break
        time.sleep(2)
    REPORT['copy'] = {'reqs': reqs, 'resps': resps}
    print('COPY_REQ', json.dumps(reqs, ensure_ascii=False), flush=True)
    print('COPY_RESP', json.dumps(resps, ensure_ascii=False), flush=True)
    print('PAGE_TAIL', text(c)[-260:].replace('\n', ' | '), flush=True)
    shot(c, 'r4-07-batch-copy-done')

    time.sleep(3)
    after = api_list('接线测试_INT1479R4')
    REPORT['after'] = [{'id': i['id'], 'name': i['name'], 'file_path': i.get('file_path'),
                        'size': i.get('size')} for i in after]
    print('AFTER', json.dumps(REPORT['after'], ensure_ascii=False), flush=True)

    # 深色：复制窗 + 移动窗
    set_theme(c, 'dark')
    c.send('Page.reload'); time.sleep(10)
    wait_ready(c, 240)
    select_rows(c, NAMES); time.sleep(0.8)
    open_bulk(c, '批量复制'); time.sleep(1.2)
    shot(c, 'r4-08-batch-copy-dark')
    close_dialog(c)
    time.sleep(0.8)
    select_rows(c, NAMES); time.sleep(0.8)
    open_bulk(c, '批量移动'); time.sleep(1.2)
    shot(c, 'r4-09-batch-move-dark')
    close_dialog(c)
    set_theme(c, 'light')

    with open(os.path.join(OUT, 'r4_copy_report.json'), 'w', encoding='utf-8') as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
