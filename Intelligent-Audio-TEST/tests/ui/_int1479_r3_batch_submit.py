# -*- coding: utf-8 -*-
"""INT-1479 R3：三个批量窗真实提交 + 回读（标注 / 标签 / 重命名）。"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1479_r3_driver import connect, goto, text  # noqa: E402
from _int1479_api import API, H  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1479_audio')
WAVDIR = os.path.join(os.environ['TEMP'], 'int1479_wav')
NAMES = [f'接线测试_INT1479R3_{i}.wav' for i in (1, 2, 3)]
TAGS = '接线测试_INT1479标签A,接线测试_INT1479标签B'
RENAME_PREFIX = '接线测试_INT1479R3R_'


def make_annotations():
    paths = []
    for i in (1, 2, 3):
        p = os.path.join(WAVDIR, f'接线测试_INT1479R3_{i}.json')
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({'code': 'asr', 'source_language': 'zh-CN', 'segments': [
                {'speaker': 'S1', 'start': 0, 'end': 1, 'text': f'接线测试ASR_INT1479R3_{i}第一段'},
                {'speaker': 'S1', 'start': 1, 'end': 2, 'text': f'接线测试ASR_INT1479R3_{i}第二段'},
            ]}, f, ensure_ascii=False)
        paths.append(p)
    return paths


def wait_rows(c, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if (c.eval("document.querySelectorAll('tbody tr').length") or 0) > 0:
            return True
        time.sleep(2)
    return False


def select_rows(c):
    return c.eval("""
      (function(names){for(const n of names){const el=document.querySelector('[role=checkbox][aria-label="选择音频 '+n+'"]');
        if(el) el.click();}return 'ok';})(%s)""" % json.dumps(NAMES))


def click_dialog_btn(c, label):
    return c.eval("""
      (function(label){
        const d = document.querySelector('[role=dialog],[role=alertdialog]');
        if(!d) return 'NO_DIALOG';
        const b = Array.from(d.querySelectorAll('button')).find(x => (x.innerText||'').trim().startsWith(label));
        if(!b) return 'NO_BTN:'+label;
        b.click(); return 'CLICKED:'+label;
      })(%s)""" % json.dumps(label))


def set_dialog_input(c, value, idx=0):
    return c.eval("""
      (function(v, idx){
        const d = document.querySelector('[role=dialog],[role=alertdialog]');
        const ins = Array.from(d.querySelectorAll('input[type=text],textarea'));
        const el = ins[idx]; if(!el) return 'NO_INPUT';
        const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
        el.dispatchEvent(new Event('input', {bubbles:true}));
        el.dispatchEvent(new Event('change', {bubbles:true}));
        return 'SET:'+el.value;
      })(%s, %s)""" % (json.dumps(value), idx))


def set_files(c, paths):
    doc = c.send('DOM.getDocument', {'depth': 2})
    node = c.send('DOM.querySelector', {'nodeId': doc['root']['nodeId'],
                                        'selector': '[role=dialog] input[type=file]'})
    if not node.get('nodeId'):
        return 'NO_FILE_INPUT'
    c.send('DOM.setFileInputFiles', {'files': paths, 'nodeId': node['nodeId']})
    return 'SET_FILES:%d' % len(paths)


def dialog_text(c):
    return c.eval("(document.querySelector('[role=dialog],[role=alertdialog]')||{}).innerText||''") or ''


def close_dialog(c):
    c.eval("""(function(){const d=document.querySelector('[role=dialog],[role=alertdialog]');if(!d)return;
      const b=Array.from(d.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='取消'||(x.getAttribute('aria-label')||'')==='Close');
      if(b)b.click();})()""")
    time.sleep(0.8)


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


def readback(s, ids, label):
    out = []
    for i in ids:
        r = s.get(f'{API}/audios/{i}', timeout=30)
        j = r.json()
        d = j.get('data') or j
        out.append({'id': i, 'status': r.status_code, 'name': d.get('name') or d.get('filename'),
                    'tags': d.get('tags'), 'annotations': d.get('annotations')})
    print(f'READBACK {label}:', json.dumps(out, ensure_ascii=False)[:2000])
    return out


def main():
    ann = make_annotations()
    wavs = [os.path.join(WAVDIR, n) for n in NAMES]
    c = connect()
    goto(c, '/audio-import', 5)
    wait_rows(c)
    time.sleep(2)
    c.pump()
    s = requests.Session(); s.headers.update(H())
    result = {}

    # --- 1. 批量设置标签 ---
    select_rows(c); time.sleep(0.8)
    t0 = len(c.events)
    print('TAGS OPEN:', c.eval("""Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='批量设置标签').click(), 'ok'"""))
    time.sleep(1.2)
    c.screenshot(os.path.join(OUT, 'r3-05-batch-tags.png'))
    print('TAGS INPUT:', set_dialog_input(c, TAGS))
    print('TAGS SUBMIT:', click_dialog_btn(c, '确认设置'))
    time.sleep(3)
    req, resp = capture(c, t0)
    print('TAGS REQ:', json.dumps(req, ensure_ascii=False, indent=1))
    print('TAGS RESP:', json.dumps(resp, ensure_ascii=False))
    print('TOAST:', c.eval("Array.from(document.querySelectorAll('[data-sonner-toast],[role=status]')).map(e=>(e.innerText||'').trim()).join(' | ')"))
    close_dialog(c)
    result['tags'] = readback(s, [2325, 2326, 2327], 'tags')
    c.screenshot(os.path.join(OUT, 'r3-05-batch-tags-after.png'))

    # --- 2. 批量更新标注 ---
    goto(c, '/audio-import', 4); wait_rows(c); time.sleep(1.5)
    select_rows(c); time.sleep(0.8)
    t0 = len(c.events)
    print('ANN OPEN:', c.eval("""Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='批量更新标注').click(), 'ok'"""))
    time.sleep(1.5)
    print('ANN FILES:', set_files(c, wavs + ann))
    time.sleep(3)
    dt = dialog_text(c)
    print('ANN TEXT:', dt[:400].replace('\n', ' | '))
    c.screenshot(os.path.join(OUT, 'r3-04-batch-annotation-matched.png'))
    print('ANN SUBMIT:', click_dialog_btn(c, '开始更新'))
    time.sleep(4)
    print('ANN AFTER:', dialog_text(c)[:300].replace('\n', ' | '))
    req, resp = capture(c, t0)
    print('ANN REQ:', json.dumps(req, ensure_ascii=False, indent=1)[:2500])
    print('ANN RESP:', json.dumps(resp, ensure_ascii=False))
    close_dialog(c)
    result['annotations'] = readback(s, [2325, 2326, 2327], 'annotations')

    # --- 3. 批量重命名 ---
    goto(c, '/audio-import', 4); wait_rows(c); time.sleep(1.5)
    select_rows(c); time.sleep(0.8)
    t0 = len(c.events)
    c.eval("""Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='更多批量操作').click(), 'ok'""")
    time.sleep(1)
    c.eval("""(function(){const m=Array.from(document.querySelectorAll('[role=menuitem]')).find(e=>(e.innerText||'').trim()==='批量重命名');if(m)m.click();})()""")
    time.sleep(1.2)
    print('RENAME INPUT:', set_dialog_input(c, RENAME_PREFIX))
    c.screenshot(os.path.join(OUT, 'r3-08-batch-rename.png'))
    print('RENAME SUBMIT:', click_dialog_btn(c, '确认执行'))
    time.sleep(3)
    req, resp = capture(c, t0)
    print('RENAME REQ:', json.dumps(req, ensure_ascii=False, indent=1))
    print('RENAME RESP:', json.dumps(resp, ensure_ascii=False))
    close_dialog(c)
    result['rename'] = readback(s, [2325, 2326, 2327], 'rename')

    with open(os.path.join(OUT, 'r3-batch-results.json'), 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
