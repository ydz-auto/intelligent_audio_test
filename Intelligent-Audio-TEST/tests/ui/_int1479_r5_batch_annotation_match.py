# -*- coding: utf-8 -*-
"""INT-1479 R5 · B3：批量更新标注的匹配口径取证。

对照 V9.7.10（按音频内容 md5 全库匹配，POST /api/v1/audios/by-md5）与 React 现状
（按文件名只在已加载列表内匹配）。做法：准备两份标注 txt ——
一份对应第 1 页已加载音频，一份对应第 2 页未加载音频 —— 同时拖入弹窗，
看匹配结果是否只认已加载列表。
"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _int1479_r4_lib as L  # noqa: E402
import _int1479_api as A  # noqa: E402

TMP = os.path.join(os.environ.get('TEMP', '.'), 'int1479_r5_ann')


def base(n):
    return n.rsplit('.', 1)[0]


def list_page(page, per_page=20):
    r = requests.post(A.API + '/audios', headers=A.H(),
                      json={'page': page, 'per_page': per_page}, timeout=90)
    d = r.json().get('data') or {}
    return d.get('items') or []


def mk(name, text):
    os.makedirs(TMP, exist_ok=True)
    p = os.path.join(TMP, name)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text)
    return p


def main():
    os.makedirs(L.OUT, exist_ok=True)
    p1 = list_page(1)
    p2 = list_page(2)
    loaded = p1[0]
    unloaded = p2[len(p2) // 2]
    f_loaded = mk(base(loaded['name']) + '.txt', '加载页音频的标注文本\n')
    f_unloaded = mk(base(unloaded['name']) + '.txt', '未加载页音频的标注文本\n')

    c = L.connect()
    L.set_theme(c, 'light')
    L.nav(c, '/audio-import', 10)
    end = time.time() + 240
    ready = False
    while time.time() < end:
        n = c.eval("document.querySelectorAll('tbody tr').length") or 0
        if n > 0:
            ready = True
            break
        time.sleep(3)
    print('READY', ready, flush=True)

    opened = c.eval("""(function(){
      const b = Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='批量更新标注');
      if(!b) return 'NOT_FOUND'; b.click(); return 'CLICKED';})()""")
    time.sleep(3)
    doc = c.send('DOM.getDocument', {'depth': 2})
    node = c.send('DOM.querySelector', {
        'nodeId': doc['root']['nodeId'],
        'selector': '[role=dialog] input[type=file]'})
    setres = c.send('DOM.setFileInputFiles', {'files': [f_loaded, f_unloaded],
                                              'nodeId': node['nodeId']})
    time.sleep(4)
    text = c.eval("""(function(){
      const d = Array.from(document.querySelectorAll('[role=dialog]')).pop();
      return d ? (d.innerText||'') : '';})()""") or ''
    shot = L.shot(c, 'r5_b3-batch-annotation-match')
    info = {
        'opened': opened,
        'loaded_audio': {'name': loaded['name'], 'id': loaded['id']},
        'unloaded_audio': {'name': unloaded['name'], 'id': unloaded['id']},
        'files': [os.path.basename(f_loaded), os.path.basename(f_unloaded)],
        'dialog_text': text.replace('\n', ' | ')[:1800],
        'screenshot': shot,
    }
    print(json.dumps(info, ensure_ascii=False, indent=1), flush=True)
    with open(os.path.join(L.OUT, 'r5_b3_report.json'), 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
