# -*- coding: utf-8 -*-
"""INT-1479 R3 修正轮：批量标签真实写入 + 批量标注真匹配提交 + 回读。"""
import json
import os
import shutil
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _int1479_r3_driver import connect, goto  # noqa: E402
from _int1479_api import API, H  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1479_audio')
WAVDIR = os.path.join(os.environ['TEMP'], 'int1479_wav')
CUR = ['测试音频_01', '测试音频_02', '测试音频_03']
IDS = [2325, 2326, 2327]
TAGS = '接线测试_INT1479标签A,接线测试_INT1479标签B'


def prep_files():
    wavs, anns = [], []
    for i, base in enumerate(CUR, start=1):
        w = os.path.join(WAVDIR, base + '.wav')
        shutil.copyfile(os.path.join(WAVDIR, f'接线测试_INT1479R3_{i}.wav'), w)
        a = os.path.join(WAVDIR, base + '.json')
        with open(a, 'w', encoding='utf-8') as f:
            json.dump({'code': 'asr', 'source_language': 'zh-CN', 'segments': [
                {'speaker': 'S1', 'start': 0, 'end': 1, 'text': f'接线测试ASR_{base}第一段'},
                {'speaker': 'S1', 'start': 1, 'end': 2, 'text': f'接线测试ASR_{base}第二段'},
            ]}, f, ensure_ascii=False)
        wavs.append(w); anns.append(a)
    return wavs, anns


def wait_rows(c, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if (c.eval("document.querySelectorAll('tbody tr').length") or 0) > 0:
            return True
        time.sleep(2)
    return False


def select_rows(c):
    return c.eval("""
      (function(names){for(const n of names){const el=document.querySelector('[role=checkbox][aria-label="选择音频 '+n+'.wav"]');
        if(el) el.click();}return 'ok';})(%s)""" % json.dumps(CUR))


def click_dialog_btn(c, label):
    return c.eval("""
      (function(label){const d=document.querySelector('[role=dialog],[role=alertdialog]');if(!d)return 'NO_DIALOG';
        const b=Array.from(d.querySelectorAll('button')).find(x=>(x.innerText||'').trim().startsWith(label));
        if(!b) return 'NO_BTN:'+label; b.click(); return 'CLICKED:'+label;})(%s)""" % json.dumps(label))


def set_dialog_input(c, value, idx=0):
    return c.eval("""
      (function(v, idx){
        const d = document.querySelector('[role=dialog],[role=alertdialog]'); if(!d) return 'NO_DIALOG';
        const ins = Array.from(d.querySelectorAll('input:not([type=file]):not([type=checkbox]):not([type=radio]),textarea'));
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
                req.append({'m': r['method'], 'u': r['url'].split('?')[0], 'body': (r.get('postData') or '')[:500]})
        elif e['method'] == 'Network.responseReceived':
            r = e['params']['response']
            if '/api/' in r['url'] and 'audios' in r['url']:
                resp.append({'s': r['status'], 'u': r['url'].split('?')[0]})
    return req, resp


def readback(s, label, ids=IDS):
    out = []
    for i in ids:
        r = s.get(f'{API}/audios/{i}', timeout=30)
        d = r.json().get('data') or r.json()
        out.append({'id': i, 'status': r.status_code, 'name': d.get('name'), 'tags': d.get('tags'),
                    'annotations': d.get('annotations')})
    print(f'READBACK {label}:', json.dumps(out, ensure_ascii=False)[:2500])
    return out


def main():
    wavs, anns = prep_files()
    c = connect()
    s = requests.Session(); s.headers.update(H())
    out = {}

    # 1) 批量标签
    goto(c, '/audio-import', 5); wait_rows(c); time.sleep(2); c.pump()
    select_rows(c); time.sleep(0.8)
    print('FIRST_ROWS:', c.eval("Array.from(document.querySelectorAll('tbody tr')).slice(0,4).map(r=>r.innerText.split('\\n').slice(1,3).join('|')).join(' ;; ')"))
    print('TOOLBAR:', c.eval("Array.from(document.querySelectorAll('button')).filter(b=>/批量|更多/.test((b.innerText||'')+(b.getAttribute('aria-label')||''))).map(b=>(b.innerText||'').trim()+(b.getAttribute('aria-label')||''))"))
    t0 = len(c.events)
    c.eval("""Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='批量设置标签').click(), 'ok'""")
    time.sleep(1.5)
    print('TAGS INPUT:', set_dialog_input(c, TAGS))
    time.sleep(0.4)
    c.screenshot(os.path.join(OUT, 'r3-05-batch-tags-filled.png'))
    t0 = len(c.events)
    print('TAGS SUBMIT:', click_dialog_btn(c, '确认设置'))
    time.sleep(4)
    req, resp = capture(c, t0)
    print('TAGS REQ:', json.dumps(req, ensure_ascii=False, indent=1))
    print('TAGS RESP:', json.dumps(resp, ensure_ascii=False))
    print('TOAST:', c.eval("Array.from(document.querySelectorAll('[data-sonner-toast]')).map(e=>(e.innerText||'').trim()).join(' | ')"))
    c.screenshot(os.path.join(OUT, 'r3-05-batch-tags-after.png'))
    close_dialog(c)
    out['tags'] = readback(s, 'tags')

    # 2) 批量标注（等对话框全量列表拉完再选文件）
    goto(c, '/audio-import', 4); wait_rows(c); time.sleep(1.5); c.pump()
    select_rows(c); time.sleep(0.8)
    t0 = len(c.events)
    c.eval("""Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='批量更新标注').click(), 'ok'""")
    print('ANN WAIT LIST...')
    time.sleep(12)
    c.pump()
    print('ANN FILES:', set_files(c, wavs + anns))
    time.sleep(4)
    dt = dialog_text(c)
    print('ANN TEXT:', dt[:500].replace('\n', ' | '))
    c.screenshot(os.path.join(OUT, 'r3-04-batch-annotation-matched.png'))
    t0 = len(c.events)
    print('ANN SUBMIT:', click_dialog_btn(c, '开始更新'))
    time.sleep(6)
    print('ANN AFTER:', dialog_text(c)[:300].replace('\n', ' | '))
    req, resp = capture(c, t0)
    print('ANN REQ:', json.dumps(req, ensure_ascii=False, indent=1)[:3000])
    print('ANN RESP:', json.dumps(resp, ensure_ascii=False))
    close_dialog(c)
    out['annotations'] = readback(s, 'annotations')

    with open(os.path.join(OUT, 'r3-batch2-results.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
