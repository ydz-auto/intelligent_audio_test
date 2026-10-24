# -*- coding: utf-8 -*-
"""INT-1479 R4：批量移动 / 批量复制 真实提交 + 回读（docker 15173/15000）。"""
import json
import math
import os
import struct
import sys
import time
import wave

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1479_r4_lib import (BASE, OUT, click, connect, nav, net_since, set_theme,
                             shot, text, wait_ready)  # noqa: E402
from _int1479_api import API, H  # noqa: E402

WAVDIR = os.path.join(os.environ.get('TEMP', '.'), 'int1479_r4_wav')
NAMES = [f'接线测试_INT1479R4_{i}.wav' for i in (1, 2, 3)]
REPORT = {}


def make_wavs():
    os.makedirs(WAVDIR, exist_ok=True)
    paths = []
    for i, freq in enumerate((520, 740, 980), start=1):
        p = os.path.join(WAVDIR, f'接线测试_INT1479R4_{i}.wav')
        with wave.open(p, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b''.join(
                struct.pack('<h', int(11000 * math.sin(2 * math.pi * freq * t / 16000)))
                for t in range(16000 * 2)))
        paths.append(p)
    return paths


def dialog_text(c):
    return c.eval("(document.querySelector('[role=dialog],[role=alertdialog]')||{}).innerText||''") or ''


def close_dialog(c):
    c.eval("""(function(){const d=document.querySelector('[role=dialog],[role=alertdialog]');if(!d)return;
      const b=Array.from(d.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='取消');
      if(b)b.click();})()""")
    time.sleep(0.8)


def open_upload(c):
    return click(c, '上传音频')


def set_files(c, paths):
    doc = c.send('DOM.getDocument', {'depth': 2})
    node = c.send('DOM.querySelector', {'nodeId': doc['root']['nodeId'],
                                        'selector': '[role=dialog] input[type=file]'})
    if not node.get('nodeId'):
        return 'NO_FILE_INPUT'
    c.send('DOM.setFileInputFiles', {'files': paths, 'nodeId': node['nodeId']})
    return 'SET_FILES:%d' % len(paths)


def click_dialog(c, label):
    return c.eval("""(function(label){const d=document.querySelector('[role=dialog],[role=alertdialog]');if(!d)return 'NO_DIALOG';
      const b=Array.from(d.querySelectorAll('button')).find(x=>(x.innerText||'').trim().startsWith(label));
      if(!b) return 'NO_BTN:'+label; b.click(); return 'CLICKED:'+label;})(%s)""" % json.dumps(label))


def api_list(keyword):
    s = requests.Session(); s.headers.update(H())
    for _ in range(5):
        r = s.post(f'{API}/audios', json={'page': 1, 'page_size': 20, 'keyword': keyword}, timeout=120)
        if r.status_code == 200 and isinstance(r.json().get('data'), dict):
            return r.json()['data']['items']
        time.sleep(3)
    return []


def api_get(aid):
    s = requests.Session(); s.headers.update(H())
    r = s.get(f'{API}/audios/{aid}', timeout=60)
    j = r.json()
    return r.status_code, (j.get('data') or j)


def select_rows(c, names):
    return c.eval("""
      (function(names){const hit=[];for(const n of names){
        const el=document.querySelector('[role=checkbox][aria-label="选择音频 '+n+'"]');
        if(el){el.click(); hit.push(n);}}return hit;})(%s)""" % json.dumps(names))


def open_bulk(c, item_label):
    r1 = click(c, '更多批量操作')
    time.sleep(0.8)
    r2 = c.eval("""(function(label){
      const nodes=Array.from(document.querySelectorAll('[role=menuitem]'));
      const el=nodes.find(n=>(n.innerText||'').trim()===label);
      if(!el) return 'NOT_FOUND:'+label; el.click(); return 'CLICKED:'+label;})(%s)""" % json.dumps(item_label))
    time.sleep(1.2)
    return r1, r2


def choose_folder(c, value):
    r = c.eval("""(function(){
      const d=document.querySelector('[role=dialog],[role=alertdialog]'); if(!d) return 'NO_DIALOG';
      const t=d.querySelector('#batch-folder-target') || d.querySelector('[role=combobox]');
      if(!t) return 'NO_TRIGGER'; t.click(); return 'TRIGGER_CLICKED';})()""")
    time.sleep(0.8)
    r2 = c.eval("""(function(v){
      const opts=Array.from(document.querySelectorAll('[role=option]'));
      const el=opts.find(o=>(o.innerText||'').trim()===v);
      if(!el) return 'NO_OPTION:'+opts.map(o=>o.innerText.trim()).join('|');
      el.click(); return 'OPTION_CLICKED:'+v;})(%s)""" % json.dumps(value))
    time.sleep(0.6)
    return r, r2


def readback_rows(ids):
    out = []
    for i in ids:
        st, d = api_get(i)
        out.append({'id': i, 'status': st, 'name': d.get('name'),
                    'file_path': d.get('file_path'), 'audio_type': d.get('audio_type'),
                    'size': d.get('size'), 'duration': d.get('duration')})
    return out


def main():
    wavs = make_wavs()
    print('WAVS', json.dumps(wavs, ensure_ascii=False), flush=True)

    c = connect()
    nav(c, '/audio-import', 8)
    print('READY', wait_ready(c, 240), flush=True)
    set_theme(c, 'light')

    # ---------- 上传 3 条自建音频 ----------
    t0 = len(c.events)
    print('OPEN_UPLOAD', open_upload(c), flush=True)
    time.sleep(2)
    print('SET_FILES', set_files(c, wavs), flush=True)
    time.sleep(2)
    print('DLG_AFTER', dialog_text(c)[:300].replace('\n', ' | '), flush=True)
    print('SUBMIT', click_dialog(c, '开始上传'), flush=True)
    for i in range(90):
        time.sleep(2)
        c.pump()
        if not c.eval("!!document.querySelector('[role=dialog]')"):
            break
    c.pump()
    reqs, resps = net_since(c, t0)
    REPORT['upload'] = {'reqs': reqs, 'resps': resps}
    print('UPLOAD_REQ', json.dumps(reqs, ensure_ascii=False)[:1500], flush=True)
    print('UPLOAD_RESP', json.dumps(resps, ensure_ascii=False)[:1200], flush=True)
    shot(c, 'r4-01-upload-done')

    items = api_list('接线测试_INT1479R4')
    ids = [it['id'] for it in items if it.get('name') in NAMES]
    REPORT['created'] = [{'id': it['id'], 'name': it.get('name'), 'file_path': it.get('file_path'),
                          'size': it.get('size'), 'duration': it.get('duration'),
                          'audio_type': it.get('audio_type')} for it in items]
    print('CREATED', json.dumps(REPORT['created'], ensure_ascii=False), flush=True)
    if len(ids) < 3:
        print('ABORT: 上传回读不足 3 条', flush=True)
        return

    # ---------- 批量移动 ----------
    nav(c, '/audio-import', 8)
    print('READY2', wait_ready(c, 240), flush=True)
    print('SELECT', select_rows(c, NAMES), flush=True)
    time.sleep(1)
    t0 = len(c.events)
    print('OPEN_BULK', open_bulk(c, '批量移动'), flush=True)
    print('MOVE_DLG', dialog_text(c)[:400].replace('\n', ' | '), flush=True)
    shot(c, 'r4-02-batch-move-light')
    print('FOLDER', choose_folder(c, 'test_data/noise'), flush=True)
    print('MOVE_DLG2', dialog_text(c)[:400].replace('\n', ' | '), flush=True)
    t0 = len(c.events)
    print('CONFIRM_MOVE', click_dialog(c, '确认执行'), flush=True)
    time.sleep(6)
    c.pump()
    reqs, resps = net_since(c, t0)
    REPORT['move'] = {'reqs': reqs, 'resps': resps, 'toast': text(c)[-500:]}
    print('MOVE_REQ', json.dumps(reqs, ensure_ascii=False), flush=True)
    print('MOVE_RESP', json.dumps(resps, ensure_ascii=False), flush=True)
    print('TOAST', text(c)[-300:].replace('\n', ' | '), flush=True)
    shot(c, 'r4-03-batch-move-done')

    # 深色再截一次移动窗
    set_theme(c, 'dark')
    c.send('Page.reload'); time.sleep(8); wait_ready(c, 180)
    select_rows(c, NAMES); time.sleep(0.8)
    open_bulk(c, '批量移动')
    time.sleep(1)
    shot(c, 'r4-04-batch-move-dark')
    close_dialog(c)
    set_theme(c, 'light')

    REPORT['after_move'] = readback_rows(ids)
    print('AFTER_MOVE', json.dumps(REPORT['after_move'], ensure_ascii=False), flush=True)

    sid = 0
    with open(os.path.join(OUT, 'r4_move_report.json'), 'w', encoding='utf-8') as f:
        json.dump({'ids': ids, **REPORT}, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
